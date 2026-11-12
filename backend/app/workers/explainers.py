"""
Pipeline steps for the signals that explain and forecast momentum:

- spikes:  find days a repo's stars jumped and look for the cause (a Hacker
           News, Lobsters or Bluesky post, or a release that day)
- odds:    fit the breakout-call model on 90 days of history, with a backtest
- hype:    each hyped repo's peak week, where it is now, and when it halved

Each is best-effort and independent; refresh.py runs them after enrichment.
The odds and hype steps do real work only once a day.
"""

import json
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import hn_service, social_service
from app.services.forecast_service import (
    BLUESKY_MIN_LIKES,
    HN_MIN_POINTS,
    HYPE_MIN_PEAK,
    LOBSTERS_MIN_POINTS,
    find_spikes,
    homepage_key,
    hype_curve,
    matches_repo,
    post_matches_repo,
    train_and_backtest,
    within,
)
from app.services.trend_service import (
    CALL_MAX_AGE_DAYS,
    CALL_MAX_STARS,
    CALL_MIN_ACCEL,
    CALL_MIN_GAIN7,
)

logger = logging.getLogger(__name__)

# Bump when the way causes are matched changes, so stored spikes are looked up again.
# 2: homepage matched by host and path, shared sites ignored, HN_MIN_POINTS.
# 3: Lobsters and Bluesky added as sources.
MATCH_RULE = 3


# ---------------------------------------------------------------- spikes

async def detect_spikes(session: AsyncSession, today: date) -> None:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.repository_id AS rid, d.date, d.stars_gained
                FROM daily_metrics d
                WHERE d.date > CAST(:today AS DATE) - 28
                  AND d.repository_id IN (
                      SELECT id FROM repositories WHERE is_archived = FALSE
                      ORDER BY stars_gained_week DESC LIMIT :n)
                """
            ),
            {"today": today, "n": settings.SPIKE_TOP_N},
        )
    ).fetchall()
    series: dict[int, list] = {}
    for r in rows:
        series.setdefault(r.rid, []).append((r.date, int(r.stars_gained or 0)))
    found = [{"rid": rid, **s} for rid, days in series.items() for s in find_spikes(days, today)]
    if found:
        await session.execute(
            text(
                """
                INSERT INTO star_spikes (repository_id, spike_date, gain, baseline)
                VALUES (:rid, :date, :gain, :baseline)
                ON CONFLICT (repository_id, spike_date) DO UPDATE
                SET gain = EXCLUDED.gain, baseline = EXCLUDED.baseline
                """
            ),
            found,
        )
    await session.commit()
    logger.info("Spikes: %d found across %d repos", len(found), len(series))


async def explain_spikes(session: AsyncSession, today: date) -> None:
    """
    Look up spikes not yet explained. A spike with nothing found is retried once
    a day for a week, since a story can be indexed after the stars arrive. Spikes
    explained under an older MATCH_RULE are looked up again.
    """
    todo = (
        await session.execute(
            text(
                """
                SELECT s.id, s.spike_date, r.id AS rid, r.owner, r.name, r.homepage_url
                FROM star_spikes s JOIN repositories r ON r.id = s.repository_id
                WHERE s.checked_at IS NULL
                   OR s.rule < :rule
                   OR (s.causes = '[]'::jsonb AND s.checked_at < NOW() - INTERVAL '1 day'
                       AND s.spike_date > CAST(:today AS DATE) - 7)
                ORDER BY s.spike_date DESC, s.gain DESC
                LIMIT :n
                """
            ),
            {"today": today, "n": settings.SPIKE_EXPLAIN_MAX, "rule": MATCH_RULE},
        )
    ).fetchall()
    if not todo:
        return

    async def _one(client: httpx.AsyncClient, s, lobsters_gh: list[dict]) -> tuple[int, list[dict]]:
        start = datetime.combine(s.spike_date - timedelta(days=3), time.min, tzinfo=timezone.utc)
        end = datetime.combine(s.spike_date + timedelta(days=1), time.max, tzinfo=timezone.utc)
        home = homepage_key(s.homepage_url)
        queries = [f"{s.owner}/{s.name}"] + ([home] if home else [])
        stories: dict[str, dict] = {}
        for q in queries:
            for h in await hn_service.stories_between(client, q, start, end):
                if h["points"] >= HN_MIN_POINTS and matches_repo(h, s.owner, s.name, home):
                    stories[h["id"]] = h
        causes = [
            {"kind": "hn", "title": h["title"], "points": h["points"], "comments": h["comments"],
             "at": h["at"], "url": f"https://news.ycombinator.com/item?id={h['id']}"}
            for h in sorted(stories.values(), key=lambda h: -h["points"])[:2]
        ]

        lob = list(lobsters_gh)
        if home:
            lob += await social_service.lobsters_domain(client, home.split("/")[0])
        lob = [
            x for x in lob
            if x["points"] >= LOBSTERS_MIN_POINTS and within(x["at"], start, end)
            and matches_repo(x, s.owner, s.name, home)
        ]
        if lob:
            top = max(lob, key=lambda x: x["points"])
            causes.append({"kind": "lobsters", "title": top["title"], "points": top["points"],
                           "comments": top["comments"], "at": top["at"], "url": top["link"]})

        posts = [
            p for p in await social_service.bluesky_posts(client, s.name, start, end)
            if p["points"] >= BLUESKY_MIN_LIKES and post_matches_repo(p, s.owner, s.name, home)
        ]
        if posts:
            top = max(posts, key=lambda p: p["points"])
            causes.append({"kind": "bluesky", "title": top["title"], "points": top["points"],
                           "comments": top["comments"], "at": top["at"], "url": top["link"]})
        release = (
            await session.execute(
                text(
                    """
                    SELECT tag, url, published_at FROM repo_releases
                    WHERE repository_id = :rid
                      AND published_at BETWEEN :start AND :end
                    ORDER BY published_at DESC LIMIT 1
                    """
                ),
                {"rid": s.rid, "start": start + timedelta(days=1), "end": end},
            )
        ).first()
        if release:
            causes.append({"kind": "release", "title": release.tag, "url": release.url,
                           "at": release.published_at.isoformat()})
        return s.id, causes

    async with httpx.AsyncClient(headers={"User-Agent": "FirstLight/1.0 (spike explanations)"}) as client:
        # One Lobsters feed of github.com links (~6 weeks) serves every spike in the run.
        lobsters_gh = await social_service.lobsters_domain(client, "github.com", pages=2)
        # Releases are read from the shared session, so look up one spike at a time.
        results = [await _one(client, s, lobsters_gh) for s in todo]
    await session.execute(
        text(
            "UPDATE star_spikes SET causes = CAST(:causes AS jsonb), checked_at = NOW(), rule = :rule "
            "WHERE id = :id"
        ),
        [{"id": sid, "causes": json.dumps(c), "rule": MATCH_RULE} for sid, c in results],
    )
    await session.execute(
        text("DELETE FROM star_spikes WHERE spike_date < CAST(:today AS DATE) - CAST(:keep AS INTEGER)"),
        {"today": today, "keep": settings.SPIKE_RETENTION_DAYS},
    )
    await session.commit()
    explained = sum(1 for _, c in results if c)
    kinds = Counter(c["kind"] for _, cs in results for c in cs)
    logger.info("Spikes explained: %d of %d checked (%s)", explained, len(results),
                ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) or "no causes found")


# ---------------------------------------------------------------- odds

BACKTEST_SQL = """
WITH d AS (
    SELECT dm.repository_id AS rid, dm.date, dm.stars_total,
           SUM(dm.stars_gained) OVER (
               PARTITION BY dm.repository_id ORDER BY dm.date
               RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW) AS gain7,
           SUM(dm.stars_gained) OVER (
               PARTITION BY dm.repository_id ORDER BY dm.date
               RANGE BETWEEN INTERVAL '27 days' PRECEDING AND INTERVAL '7 days' PRECEDING) AS gain_prior,
           COUNT(*) OVER (
               PARTITION BY dm.repository_id ORDER BY dm.date
               RANGE BETWEEN INTERVAL '27 days' PRECEDING AND INTERVAL '7 days' PRECEDING) AS prior_days
    FROM daily_metrics dm
),
ranked AS (
    SELECT d.*, RANK() OVER (PARTITION BY d.date ORDER BY d.gain7 DESC) AS rk FROM d
),
cand AS (
    SELECT DISTINCT ON (k.rid)
           k.rid, k.date, k.gain7, k.stars_total,
           k.gain7 / GREATEST(k.gain_prior / 3.0, 10) AS accel,
           k.date - CAST(r.github_created_at AS DATE) AS age
    FROM ranked k JOIN repositories r ON r.id = k.rid
    WHERE k.prior_days >= 7
      AND k.rk > CAST(:hit_rank AS INTEGER)
      AND k.stars_total < CAST(:max_stars AS INTEGER)
      AND k.gain7 >= CAST(:min_gain AS INTEGER)
      AND k.gain7 / GREATEST(k.gain_prior / 3.0, 10) >= CAST(:min_accel AS NUMERIC)
      AND r.github_created_at IS NOT NULL
      AND k.date - CAST(r.github_created_at AS DATE) <= CAST(:max_age AS INTEGER)
      AND k.date <= (SELECT MAX(date) FROM daily_metrics) - CAST(:window AS INTEGER)
    ORDER BY k.rid, k.date
)
SELECT c.rid, c.date, c.gain7, c.stars_total, c.accel, c.age, MIN(l.rk) AS best_rank
FROM cand c
LEFT JOIN ranked l
  ON l.rid = c.rid AND l.date > c.date AND l.date <= c.date + CAST(:window AS INTEGER)
GROUP BY c.rid, c.date, c.gain7, c.stars_total, c.accel, c.age
"""


async def train_call_model(session: AsyncSession, today: date) -> None:
    """Refit the odds model from a backtest over all stored history, once a day."""
    # Retrain anyway if today's model predates the trust check (no "usable" flag).
    last = (
        await session.execute(text("SELECT trained_on, model->'usable' IS NOT NULL AS checked FROM call_model WHERE id = 1"))
    ).first()
    if last and last.trained_on == today and last.checked:
        return
    await session.execute(text("SET LOCAL statement_timeout = '120s'"))
    rows = (
        await session.execute(
            text(BACKTEST_SQL),
            {
                "hit_rank": settings.CALL_HIT_RANK,
                "max_stars": CALL_MAX_STARS,
                "min_gain": CALL_MIN_GAIN7,
                "min_accel": CALL_MIN_ACCEL,
                "max_age": CALL_MAX_AGE_DAYS,
                "window": settings.CALL_WINDOW_DAYS,
            },
        )
    ).fetchall()
    # Bank this backtest's breakouts (first sighting wins), then train on everything banked,
    # including breakouts whose daily metrics have since been pruned.
    if rows:
        await session.execute(
            text(
                """
                INSERT INTO call_samples (repository_id, sample_date, accel, gain7, stars, age, best_rank)
                VALUES (:rid, :d, :accel, :gain7, :stars, :age, :best_rank)
                ON CONFLICT (repository_id) DO UPDATE
                SET best_rank = EXCLUDED.best_rank
                WHERE call_samples.sample_date = EXCLUDED.sample_date
                """
            ),
            [{"rid": r.rid, "d": r.date, "accel": round(min(float(r.accel), 99_999_999), 2), "gain7": int(r.gain7),
              "stars": int(r.stars_total), "age": int(r.age), "best_rank": r.best_rank} for r in rows],
        )
    banked = (
        await session.execute(text("SELECT sample_date, accel, gain7, stars, age, best_rank FROM call_samples"))
    ).fetchall()
    samples = [
        {"date": b.sample_date, "accel": float(b.accel), "gain7": int(b.gain7), "stars": int(b.stars),
         "age": int(b.age), "hit": b.best_rank is not None and b.best_rank <= settings.CALL_HIT_RANK}
        for b in banked
    ]
    if samples:
        rates = ", ".join(
            f"top {n}: {sum(1 for b in banked if b.best_rank is not None and b.best_rank <= n)}"
            for n in (25, 50, 100, 200)
        )
        logger.info("Call odds: %d banked breakouts reached %s (hit bar is top %d)",
                    len(samples), rates, settings.CALL_HIT_RANK)
    result = train_and_backtest(samples)
    if result is None:
        logger.info(
            "Call odds: not enough history yet (%d banked breakouts, %d reached the top %d; need 40 and 5)",
            len(samples), sum(x["hit"] for x in samples), settings.CALL_HIT_RANK,
        )
        return
    await session.execute(
        text(
            """
            INSERT INTO call_model (id, trained_on, samples, positives, base_rate, model, backtest)
            VALUES (1, :today, :samples, :positives, :base_rate, CAST(:model AS jsonb), CAST(:backtest AS jsonb))
            ON CONFLICT (id) DO UPDATE
            SET trained_on = EXCLUDED.trained_on, samples = EXCLUDED.samples,
                positives = EXCLUDED.positives, base_rate = EXCLUDED.base_rate,
                model = EXCLUDED.model, backtest = EXCLUDED.backtest
            """
        ),
        {
            "today": today,
            "samples": result["samples"],
            "positives": result["positives"],
            "base_rate": result["base_rate"],
            "model": json.dumps(result["model"]),
            "backtest": json.dumps(result["backtest"]) if result["backtest"] else None,
        },
    )
    await session.commit()
    bt = result["backtest"] or {}
    logger.info(
        "Call odds: model fitted on %d samples (%d hits); backtest skill %s on %s held-out hits, %s",
        result["samples"], result["positives"], bt.get("skill"), bt.get("test_hits"),
        "in use" if result["model"]["usable"] else "not better than the average yet, using the average",
    )


async def load_call_model(session: AsyncSession) -> dict | None:
    try:
        row = (await session.execute(text("SELECT model FROM call_model WHERE id = 1"))).first()
    except Exception:  # noqa: BLE001 -- table not created yet
        await session.rollback()
        return None
    if not row:
        return None
    return row.model if isinstance(row.model, dict) else json.loads(row.model)


# ---------------------------------------------------------------- hype

HYPE_SQL = """
WITH d AS (
    SELECT repository_id AS rid, date, COALESCE(commit_count_week, 0) AS commits,
           SUM(stars_gained) OVER (
               PARTITION BY repository_id ORDER BY date
               RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW) AS gain7
    FROM daily_metrics
),
hot AS (SELECT rid FROM d GROUP BY rid HAVING MAX(gain7) >= CAST(:min_peak AS INTEGER))
SELECT d.rid, d.date, d.gain7, d.commits FROM d JOIN hot USING (rid) ORDER BY d.rid, d.date
"""


async def update_hype_curves(session: AsyncSession, today: date) -> None:
    """Rebuild hype_curves once a day (it only changes with a new day of data)."""
    done = (await session.execute(text("SELECT 1 FROM hype_curves WHERE as_of >= :today LIMIT 1"), {"today": today})).first()
    if done:
        return
    await session.execute(text("SET LOCAL statement_timeout = '120s'"))
    rows = (await session.execute(text(HYPE_SQL), {"min_peak": HYPE_MIN_PEAK})).fetchall()
    series: dict[int, list] = {}
    for r in rows:
        series.setdefault(r.rid, []).append((r.date, int(r.gain7 or 0), int(r.commits or 0)))
    curves = []
    for rid, pts in series.items():
        c = hype_curve(pts)
        if c:
            curves.append({"rid": rid, **c})
    await session.execute(text("DELETE FROM hype_curves"))
    if curves:
        await session.execute(
            text(
                """
                INSERT INTO hype_curves
                    (repository_id, peak_on, peak_gain7, now_gain7, half_on, commits_peak, commits_now, as_of)
                VALUES (:rid, :peak_on, :peak_gain7, :now_gain7, :half_on, :commits_peak, :commits_now, :as_of)
                """
            ),
            curves,
        )
    await session.commit()
    logger.info("Hype curves: %d repos", len(curves))
