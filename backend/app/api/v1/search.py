import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.schemas.repository import SearchResponse

router = APIRouter()


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    language: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"search:{q.lower().strip()}:{limit}:{language}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    start = time.monotonic()
    q_clean = q.strip()

    # Full-text search + trigram similarity on repos
    repos_result = await db.execute(
        text("""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics,
               r.github_created_at, r.first_seen_at,
               ts_rank(
                 to_tsvector('english', coalesce(r.name,'') || ' ' || coalesce(r.description,'')),
                 plainto_tsquery('english', :q)
               ) AS rank
        FROM repositories r
        WHERE (
            to_tsvector('english', coalesce(r.name,'') || ' ' || coalesce(r.description,''))
            @@ plainto_tsquery('english', :q)
          OR r.name ILIKE :q_like
          OR :q_lower = ANY(r.topics)
        )
        AND r.is_archived = FALSE
        AND (CAST(:language AS TEXT) IS NULL OR r.language = :language)
        ORDER BY rank DESC, r.momentum_score DESC
        LIMIT :limit
        """),
        {"q": q_clean, "q_like": f"%{q_clean}%", "q_lower": q_clean.lower(), "limit": limit,
         "language": language},
    )
    repo_rows = repos_result.fetchall()

    # Count for metadata
    count_result = await db.execute(
        text("""
        SELECT COUNT(*) FROM repositories r
        WHERE (
            to_tsvector('english', coalesce(r.name,'') || ' ' || coalesce(r.description,''))
            @@ plainto_tsquery('english', :q)
          OR r.name ILIKE :q_like
          OR :q_lower = ANY(r.topics)
        )
        AND r.is_archived = FALSE
        AND (CAST(:language AS TEXT) IS NULL OR r.language = :language)
        """),
        {"q": q_clean, "q_like": f"%{q_clean}%", "q_lower": q_clean.lower(), "language": language},
    )
    total = count_result.scalar() or 0

    # Category search
    cats_result = await db.execute(
        text("""
        SELECT id, name, slug, icon, color_hex
        FROM technology_categories
        WHERE name ILIKE :q_like OR slug ILIKE :q_like
           OR :q_lower = ANY(keywords)
        LIMIT 5
        """),
        {"q_like": f"%{q_clean}%", "q_lower": q_clean.lower()},
    )

    repos = []
    for r in repo_rows:
        d = dict(r._mapping)
        d.pop("rank", None)
        d["momentum_score"] = float(d.get("momentum_score") or 0)
        d["topics"] = d.get("topics") or []
        d["categories"] = []
        repos.append(d)

    categories = [dict(r._mapping) for r in cats_result.fetchall()]
    took_ms = int((time.monotonic() - start) * 1000)

    response = {
        "repos": repos,
        "categories": categories,
        "total_repos": total,
        "took_ms": took_ms,
    }

    await cache_set(cache_key, response, settings.CACHE_TTL_SEARCH)
    return response
