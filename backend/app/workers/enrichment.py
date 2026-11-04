"""
Pipeline steps that run after scoring: lifecycle stages, breakout calls,
releases, stargazer sampling and retention. Each step is independent and
best-effort; refresh.py runs them in order and logs failures without stopping.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.forecast_service import call_features, predict
from app.services.github_service import github_service
from app.services.trend_service import (
    acceleration,
    classify_lifecycle,
    is_breakout_candidate,
    summarize_stargazers,
)
from app.workers.explainers import load_call_model

logger = logging.getLogger(__name__)


async def _growth_rows(session: AsyncSession, today: date) -> list[dict]:
    """
    Per repo: stars gained in the last 7 days and the weekly average over the
    3 weeks before. prior_avg is None with under a week of earlier history.
    """
    result = await session.execute(
        text(
            """
            SELECT r.id, r.latest_stars, r.github_created_at,
                   COALESCE(SUM(d.stars_gained) FILTER (
                       WHERE d.date > CAST(:today AS DATE) - 7), 0) AS gain7,
                   COALESCE(SUM(d.stars_gained) FILTER (
                       WHERE d.date <= CAST(:today AS DATE) - 7), 0) AS gain_prior,
                   COUNT(*) FILTER (WHERE d.date <= CAST(:today AS DATE) - 7) AS prior_days
            FROM repositories r
            JOIN daily_metrics d
              ON d.repository_id = r.id AND d.date > CAST(:today AS DATE) - 28
            WHERE r.is_archived = FALSE
            GROUP BY r.id
            """
        ),
        {"today": today},
    )
    now = datetime.now(timezone.utc)
    rows = []
    for r in result.fetchall():
        created = r.github_created_at
        rows.append({
            "id": r.id,
            "stars": int(r.latest_stars or 0),
            "age_days": (now - created).days if created else 365,
            "gain7": int(r.gain7),
            "prior_avg": int(r.gain_prior) / 3 if r.prior_days >= 7 else None,
        })
    return rows


async def update_lifecycles_and_calls(session: AsyncSession, today: date) -> None:
    rows = await _growth_rows(session, today)
    if not rows:
        return

    stages = [
        classify_lifecycle(r["gain7"], r["prior_avg"], r["age_days"], r["stars"]) for r in rows
    ]
    await session.execute(
        text(
            "UPDATE repositories r SET lifecycle = t.lc "
            "FROM unnest(CAST(:ids AS bigint[]), CAST(:lcs AS text[])) AS t(id, lc) "
            "WHERE r.id = t.id"
        ),
        {"ids": [r["id"] for r in rows], "lcs": stages},
    )
    await session.commit()
    logger.info("Lifecycle stages set for %d repos", len(rows))

    # Score open calls first so a repo that just hit the list is counted.
    top = (
        await session.execute(
            text(
                """
                SELECT id, rk FROM (
                    SELECT id, RANK() OVER (ORDER BY stars_gained_week DESC) AS rk
                    FROM repositories WHERE is_archived = FALSE
                ) t WHERE rk <= :n
                """
            ),
            {"n": settings.CALL_HIT_RANK},
        )
    ).fetchall()
    top_rank = {r.id: int(r.rk) for r in top}
    if top_rank:
        await session.execute(
            text(
                """
                UPDATE breakout_calls c
                SET hit_on = COALESCE(c.hit_on, CAST(:today AS DATE)),
                    best_rank = LEAST(COALESCE(c.best_rank, t.rk), t.rk)
                FROM unnest(CAST(:ids AS bigint[]), CAST(:rks AS int[])) AS t(id, rk)
                WHERE c.repository_id = t.id
                  AND (c.hit_on IS NOT NULL
                       OR c.called_on > CAST(:today AS DATE) - CAST(:window AS INTEGER))
                """
            ),
            {
                "today": today,
                "ids": list(top_rank),
                "rks": list(top_rank.values()),
                "window": settings.CALL_WINDOW_DAYS,
            },
        )

    # New calls, capped per Monday-Sunday week.
    week_start = today - timedelta(days=today.weekday())
    made = (
        await session.execute(
            text("SELECT COUNT(*) FROM breakout_calls WHERE called_on >= :ws"),
            {"ws": week_start},
        )
    ).scalar() or 0
    room = settings.CALLS_PER_WEEK - made
    if room > 0:
        called = {
            r[0] for r in (await session.execute(text("SELECT repository_id FROM breakout_calls"))).fetchall()
        }
        # A jump made of brand-new, empty accounts isn't a breakout worth calling.
        bought = {
            r[0] for r in (
                await session.execute(text("SELECT repository_id FROM star_quality WHERE verdict = 'suspicious'"))
            ).fetchall()
        }
        model = await load_call_model(session)

        def odds(r) -> float | None:
            if not model:
                return None
            accel = acceleration(r["gain7"], r["prior_avg"])
            return predict(model, call_features(accel, r["gain7"], r["stars"], r["age_days"]))

        pool = [
            r for r in rows
            if r["id"] not in called
            and r["id"] not in top_rank
            and r["id"] not in bought
            and is_breakout_candidate(r["gain7"], r["prior_avg"], r["age_days"], r["stars"])
        ]
        for r in pool:
            r["prob"] = odds(r)
        # With a model, call the likeliest; without one, the sharpest acceleration.
        candidates = sorted(
            pool,
            key=lambda r: r["prob"] if r["prob"] is not None else acceleration(r["gain7"], r["prior_avg"]),
            reverse=True,
        )[:room]
        for r in candidates:
            await session.execute(
                text(
                    """
                    INSERT INTO breakout_calls
                        (repository_id, called_on, stars_at_call, gain7_at_call, accel, prob)
                    VALUES (:id, :today, :stars, :gain7, :accel, :prob)
                    ON CONFLICT (repository_id) DO NOTHING
                    """
                ),
                {
                    "id": r["id"], "today": today, "stars": r["stars"], "gain7": r["gain7"],
                    "accel": round(min(acceleration(r["gain7"], r["prior_avg"]), 9999), 2),
                    "prob": round(r["prob"], 3) if r["prob"] is not None else None,
                },
            )
        logger.info("Breakout calls: %d new this run (%d already this week)", len(candidates), made)
    await session.commit()


async def fetch_releases(session: AsyncSession) -> None:
    """Releases for the top repos by momentum plus every repo someone watches."""
    targets = (
        await session.execute(
            text(
                """
                (SELECT id, owner, name FROM repositories
                 WHERE is_archived = FALSE ORDER BY momentum_score DESC LIMIT :top)
                UNION
                (SELECT r.id, r.owner, r.name FROM repositories r
                 WHERE r.id IN (SELECT DISTINCT unnest(repo_ids) FROM push_subscriptions))
                LIMIT :cap
                """
            ),
            {"top": settings.RELEASES_TOP_N, "cap": settings.RELEASES_MAX_REPOS},
        )
    ).fetchall()
    sem = asyncio.Semaphore(settings.SIGNALS_CONCURRENCY)

    async def _one(t):
        async with sem:
            return t.id, await github_service.get_recent_releases(t.owner, t.name)

    rows = []
    for rid, releases in await asyncio.gather(*[_one(t) for t in targets]):
        rows.extend({"rid": rid, **rel} for rel in releases)
    if rows:
        await session.execute(
            text(
                """
                INSERT INTO repo_releases
                    (repository_id, tag, name, published_at, url, prerelease, snippet)
                VALUES (:rid, :tag, :name, :published_at, :url, :prerelease, :snippet)
                ON CONFLICT (repository_id, tag) DO UPDATE
                SET name = EXCLUDED.name, published_at = EXCLUDED.published_at,
                    url = EXCLUDED.url, prerelease = EXCLUDED.prerelease,
                    snippet = EXCLUDED.snippet
                """
            ),
            rows,
        )
    await session.commit()
    logger.info("Releases: %d rows from %d repos", len(rows), len(targets))


async def sample_star_quality(session: AsyncSession) -> None:
    """Sample recent stargazers of the fastest-starred repos not checked lately."""
    targets = (
        await session.execute(
            text(
                """
                SELECT r.id, r.owner, r.name FROM repositories r
                LEFT JOIN star_quality q ON q.repository_id = r.id
                WHERE r.is_archived = FALSE
                  AND r.stars_gained_week >= :min_week
                  AND (q.sampled_at IS NULL OR q.sampled_at < NOW() - (:every * INTERVAL '1 day'))
                ORDER BY r.stars_gained_week DESC
                LIMIT :n
                """
            ),
            {
                "min_week": settings.STAR_SAMPLE_MIN_WEEK,
                "every": settings.STAR_SAMPLE_EVERY_DAYS,
                "n": settings.STAR_SAMPLE_TOP_N,
            },
        )
    ).fetchall()
    done = 0
    for t in targets:
        summary = summarize_stargazers(await github_service.sample_stargazers(t.owner, t.name))
        if not summary:
            continue
        await session.execute(
            text(
                """
                INSERT INTO star_quality (repository_id, sampled_at, sample_size, pct_new, pct_empty, verdict)
                VALUES (:rid, NOW(), :sample_size, :pct_new, :pct_empty, :verdict)
                ON CONFLICT (repository_id) DO UPDATE
                SET sampled_at = NOW(), sample_size = EXCLUDED.sample_size,
                    pct_new = EXCLUDED.pct_new, pct_empty = EXCLUDED.pct_empty,
                    verdict = EXCLUDED.verdict
                """
            ),
            {"rid": t.id, **summary},
        )
        done += 1
    await session.commit()
    logger.info("Star quality sampled for %d of %d repos", done, len(targets))


async def prune(session: AsyncSession, today: date) -> None:
    """Retention for tables that otherwise grow without bound."""
    await session.execute(
        text("DELETE FROM repo_releases WHERE published_at < :cutoff"),
        {"cutoff": today - timedelta(days=settings.RELEASE_RETENTION_DAYS)},
    )
    # Keep each repo's newest insight however old; drop superseded ones past the window.
    await session.execute(
        text(
            """
            DELETE FROM insight_reports ir
            WHERE ir.report_type = 'repository'
              AND ir.generated_at < :cutoff
              AND EXISTS (
                  SELECT 1 FROM insight_reports newer
                  WHERE newer.subject_id = ir.subject_id
                    AND newer.report_type = 'repository'
                    AND newer.generated_at > ir.generated_at
              )
            """
        ),
        {"cutoff": today - timedelta(days=settings.INSIGHT_RETENTION_DAYS)},
    )
    await session.commit()
