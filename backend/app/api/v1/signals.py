"""
Endpoints built on the enrichment pipeline: breakout calls and their odds,
releases, explained spikes, hype half-life, star checks, the weekly digest,
natural-language questions and the GitHub-stars radar.
"""

import re
import time
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_incr, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.services.ask_service import describe, filter_sql, parse_question
from app.services.digest_service import call_record, fetch_digest, signal
from app.services.forecast_service import closest_starred, hype_summary, radar_score, star_profile
from app.services.github_service import github_service

router = APIRouter()

_CARD_COLS = """
    r.id, r.full_name, r.owner, r.name, r.description, r.language,
    r.latest_stars, r.stars_gained_today, r.stars_gained_week,
    r.latest_forks, r.momentum_score, r.topics,
    r.github_created_at, r.first_seen_at, r.lifecycle
"""


def _card(row) -> dict:
    d = dict(row._mapping)
    d["momentum_score"] = float(d.get("momentum_score") or 0)
    d["topics"] = d.get("topics") or []
    d["categories"] = []
    for k in ("latest_stars", "stars_gained_today", "stars_gained_week", "latest_forks"):
        d[k] = int(d.get(k) or 0)
    return d


@router.get("/calls")
async def get_calls(db: AsyncSession = Depends(get_db)):
    cached = await cache_get("calls:v2")
    if cached:
        return cached
    try:
        data = await call_record(db)
        data["model"] = await _call_model(db)
    except Exception:  # noqa: BLE001 -- table not created yet
        await db.rollback()
        data = {"calls": [], "record": {"total": 0, "hits": 0, "misses": 0, "open": 0,
                                        "hit_rate": None, "avg_lead_days": None,
                                        "hit_rank": settings.CALL_HIT_RANK,
                                        "window_days": settings.CALL_WINDOW_DAYS},
                "live_calibration": {"n": 0, "bins": [], "brier": None}, "model": None}
    await cache_set("calls:v2", data, settings.CACHE_TTL_DASHBOARD)
    return data


async def _call_model(db: AsyncSession) -> dict | None:
    """The odds model's size and backtest (not its coefficients)."""
    try:
        row = (
            await db.execute(
                text("SELECT trained_on, samples, positives, base_rate, backtest FROM call_model WHERE id = 1")
            )
        ).first()
    except Exception:  # noqa: BLE001 -- table not created yet
        await db.rollback()
        return None
    return dict(row._mapping) if row else None


@router.get("/spikes")
async def get_spikes(days: int = Query(7, ge=1, le=30), db: AsyncSession = Depends(get_db)):
    """Recent star spikes that have a known cause, biggest first."""
    key = f"spikes:v1:{days}"
    cached = await cache_get(key)
    if cached:
        return cached
    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT s.repository_id AS id, r.full_name, r.name, r.language,
                           s.spike_date AS date, s.gain, s.baseline, s.causes
                    FROM star_spikes s JOIN repositories r ON r.id = s.repository_id
                    WHERE s.spike_date >= CURRENT_DATE - CAST(:days AS INTEGER)
                      AND s.causes <> '[]'::jsonb
                    ORDER BY s.gain DESC
                    LIMIT 12
                    """
                ),
                {"days": days},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        rows = []
    data = {"spikes": [dict(r._mapping) for r in rows]}
    await cache_set(key, data, settings.CACHE_TTL_DASHBOARD)
    return data


@router.get("/hype")
async def get_hype(db: AsyncSession = Depends(get_db)):
    """How fast hype fades, overall and per category (from hype_curves, rebuilt daily)."""
    cached = await cache_get("hype:v1")
    if cached:
        return cached
    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT h.repository_id AS id, h.peak_on, h.peak_gain7, h.now_gain7, h.half_on,
                           h.commits_peak, h.commits_now, h.as_of,
                           tc.slug, tc.name AS category
                    FROM hype_curves h
                    LEFT JOIN repository_categories rc ON rc.repository_id = h.repository_id
                    LEFT JOIN technology_categories tc ON tc.id = rc.category_id
                    """
                )
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        rows = []
    today = max((r.as_of for r in rows), default=None)
    curves: dict[int, dict] = {}
    by_cat: dict[str, list[dict]] = {}
    names: dict[str, str] = {}
    for r in rows:
        c = {k: getattr(r, k) for k in ("peak_on", "peak_gain7", "now_gain7", "half_on", "commits_peak", "commits_now")}
        curves[r.id] = c
        if r.slug:
            by_cat.setdefault(r.slug, []).append(c)
            names[r.slug] = r.category
    overall = hype_summary(list(curves.values()), today) if today else None
    cats = []
    for slug, cs in by_cat.items():
        summary = hype_summary(cs, today)
        if summary and summary["n"] >= 5:
            cats.append({"slug": slug, "name": names[slug], **summary})
    cats.sort(key=lambda c: (c["fade_days"] is None, c["fade_days"] or 0))
    data = {"as_of": today, "overall": overall, "categories": cats}
    await cache_set("hype:v1", data, 6 * 3600)
    return data


@router.get("/star-checks")
async def get_star_checks(ids: str = Query(..., max_length=2000), db: AsyncSession = Depends(get_db)):
    """Stargazer-sample verdicts for a set of repos (only those that were sampled)."""
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:100]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers")
    if not id_list:
        return {"checks": {}}
    try:
        rows = (
            await db.execute(
                text("SELECT repository_id, verdict, pct_new, pct_empty FROM star_quality WHERE repository_id = ANY(:ids)"),
                {"ids": id_list},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        rows = []
    return {"checks": {str(r.repository_id): {"verdict": r.verdict, "pct_new": r.pct_new,
                                               "pct_empty": r.pct_empty} for r in rows}}


_LOGIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


@router.get("/for-user")
async def for_user(login: str = Query(..., min_length=1, max_length=39), db: AsyncSession = Depends(get_db)):
    """
    Rising repos matched to a GitHub user's public stars. Up to 3 GitHub calls a
    lookup, cached for RADAR_CACHE_TTL and capped at RADAR_DAILY_LIMIT a day.
    """
    login = login.strip()
    if not _LOGIN.match(login):
        raise HTTPException(status_code=422, detail="That isn't a valid GitHub username.")
    key = f"foruser:v1:{login.lower()}"
    cached = await cache_get(key)
    if cached:
        return cached
    used = await cache_incr(f"foruser:count:{date.today().isoformat()}", 86400)
    # Without Redis the daily cap can't be counted, so don't spend the shared GitHub quota.
    if used is None or used > settings.RADAR_DAILY_LIMIT:
        raise HTTPException(status_code=503, detail="Star lookups are paused for today. Try again tomorrow.")
    try:
        starred = await github_service.get_starred(login)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="GitHub didn't answer. Try again in a minute.")
    if starred is None:
        raise HTTPException(status_code=404, detail=f"No GitHub user called {login}.")
    profile = star_profile(starred)
    mine = {s["full_name"].lower() for s in starred if s.get("full_name")}
    rows = (
        await db.execute(
            text(f"SELECT {_CARD_COLS} FROM repositories r WHERE r.is_archived = FALSE "
                 "ORDER BY r.momentum_score DESC LIMIT 500")
        )
    ).fetchall()
    picks = []
    for row in rows:
        card = _card(row)
        if card["full_name"].lower() in mine:
            continue
        score, shared = radar_score(card, profile)
        if score > 0:
            picks.append((score, card, shared))
    picks.sort(key=lambda t: -t[0])
    data = {
        "login": login,
        "starred": len(starred),
        "topics": [t for t, _ in profile["topics"].most_common(6)],
        "languages": [lang for lang, _ in profile["languages"].most_common(3)],
        "repos": [
            {**card, "shared_topics": shared, "like": closest_starred(card, starred)}
            for _, card, shared in picks[:12]
        ],
    }
    await cache_set(key, data, settings.RADAR_CACHE_TTL)
    return data


@router.get("/releases")
async def get_releases(
    ids: str = Query(..., max_length=2000),
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
):
    """Recent releases for a set of repos (watchlist / For You)."""
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:100]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers")
    if not id_list:
        return {"releases": []}
    try:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT rr.repository_id AS id, r.full_name, rr.tag, rr.name,
                           rr.published_at, rr.url, rr.prerelease, rr.snippet
                    FROM repo_releases rr
                    JOIN repositories r ON r.id = rr.repository_id
                    WHERE rr.repository_id = ANY(:ids)
                      AND rr.published_at >= NOW() - (:days * INTERVAL '1 day')
                    ORDER BY rr.published_at DESC
                    LIMIT 50
                    """
                ),
                {"ids": id_list, "days": days},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        rows = []
    return {"releases": [dict(r._mapping) for r in rows]}


@router.get("/digest")
async def get_digest(db: AsyncSession = Depends(get_db)):
    """Exactly what the weekly email contains, for the This Week page."""
    cached = await cache_get("digest:v1")
    if cached:
        return cached
    breakouts, movers, shipped = await fetch_digest(db)

    def _row(r) -> dict:
        m = r._mapping
        return {
            "id": m["id"],
            "full_name": m["full_name"],
            "description": m["description"],
            "language": m["language"],
            "category": m["category"],
            "latest_stars": int(m["latest_stars"] or 0),
            "stars_gained_today": int(m["stars_gained_today"] or 0),
            "stars_gained_week": int(m["stars_gained_week"] or 0),
            "momentum_score": round(float(m["momentum_score"] or 0), 1),
            "github_created_at": m["github_created_at"],
            "backed_by_activity": signal(m),
        }

    data = {
        "breakouts": [_row(r) for r in breakouts],
        "movers": [_row(r) for r in movers],
        "shipped": [dict(r._mapping) for r in shipped],
    }
    await cache_set("digest:v1", data, settings.CACHE_TTL_DASHBOARD)
    return data


async def _vocab(db: AsyncSession) -> tuple[list[str], dict[str, str]]:
    cached = await cache_get("ask:vocab:v1")
    if cached:
        return cached["languages"], cached["categories"]
    langs = [
        r[0] for r in (
            await db.execute(
                text(
                    "SELECT language FROM repositories WHERE language IS NOT NULL "
                    "GROUP BY language HAVING COUNT(*) >= 5 ORDER BY COUNT(*) DESC LIMIT 60"
                )
            )
        ).fetchall()
    ]
    cats = {
        r.slug: r.name
        for r in (await db.execute(text("SELECT slug, name FROM technology_categories"))).fetchall()
    }
    await cache_set("ask:vocab:v1", {"languages": langs, "categories": cats}, 86400)
    return langs, cats


@router.get("/ask")
async def ask(q: str = Query(..., min_length=3, max_length=200), db: AsyncSession = Depends(get_db)):
    start = time.monotonic()
    languages, categories = await _vocab(db)
    filt, how = await parse_question(q.strip(), languages, categories)
    clause, params = filter_sql(filt)
    try:
        rows = (
            await db.execute(text(f"SELECT {_CARD_COLS} FROM repositories r {clause} LIMIT :limit"), params)
        ).fetchall()
    except Exception:  # noqa: BLE001 -- lifecycle column missing before first upgrade
        await db.rollback()
        filt.pop("lifecycle", None)
        clause, params = filter_sql(filt)
        rows = (
            await db.execute(
                text(f"SELECT {_CARD_COLS.replace(', r.lifecycle', '')} FROM repositories r {clause} LIMIT :limit"),
                params,
            )
        ).fetchall()
    return {
        "question": q,
        "understood": describe(filt, categories),
        "filter": filt,
        "parsed_by": how,
        "repos": [_card(r) for r in rows],
        "took_ms": round((time.monotonic() - start) * 1000),
    }
