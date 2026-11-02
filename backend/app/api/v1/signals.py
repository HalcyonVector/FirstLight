"""
Endpoints built on the enrichment pipeline: breakout calls, releases, the
weekly digest and natural-language questions.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.services.ask_service import describe, filter_sql, parse_question
from app.services.digest_service import call_record, fetch_digest, signal

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
    cached = await cache_get("calls:v1")
    if cached:
        return cached
    try:
        data = await call_record(db)
    except Exception:  # noqa: BLE001 -- table not created yet
        await db.rollback()
        data = {"calls": [], "record": {"total": 0, "hits": 0, "misses": 0, "open": 0,
                                        "hit_rate": None, "avg_lead_days": None,
                                        "hit_rank": settings.CALL_HIT_RANK,
                                        "window_days": settings.CALL_WINDOW_DAYS}}
    await cache_set("calls:v1", data, settings.CACHE_TTL_DASHBOARD)
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
