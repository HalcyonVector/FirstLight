from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.schemas.repository import CategoryTrendDetail, RadarResponse, TrendsResponse

router = APIRouter()


@router.get("", response_model=TrendsResponse)
async def get_trends(
    period: str = "7d",
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"trends:{period}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        text("""
        SELECT tc.id, tc.name, tc.slug, tc.icon, tc.color_hex,
               ts.momentum_score, ts.stars_gained_week, ts.repo_count, ts.radar_status
        FROM technology_categories tc
        LEFT JOIN trend_snapshots ts ON ts.category_id = tc.id
            AND ts.date = (SELECT MAX(date) FROM trend_snapshots WHERE category_id = tc.id)
        ORDER BY COALESCE(ts.momentum_score, 0) DESC
        """)
    )

    categories = []
    for row in result.fetchall():
        d = dict(row._mapping)
        categories.append({
            "category": {
                "id": d["id"], "name": d["name"], "slug": d["slug"],
                "icon": d["icon"], "color_hex": d["color_hex"],
            },
            "momentum_score": float(d.get("momentum_score") or 0),
            "stars_gained_week": d.get("stars_gained_week") or 0,
            "repo_count": d.get("repo_count") or 0,
            "radar_status": d.get("radar_status") or "stable",
            "top_repos": [],
        })

    response = {"categories": categories, "period": period}
    await cache_set(cache_key, response, settings.CACHE_TTL_TRENDS)
    return response


@router.get("/radar", response_model=RadarResponse)
async def get_radar(db: AsyncSession = Depends(get_db)):
    cache_key = "radar:v1"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    today = date.today()
    result = await db.execute(
        text("""
        SELECT tc.id, tc.name, tc.slug, tc.icon, tc.color_hex,
               ts.momentum_score, ts.radar_status, ts.repo_count, ts.stars_gained_week,
               prev.momentum_score AS prev_momentum_score
        FROM technology_categories tc
        LEFT JOIN trend_snapshots ts ON ts.category_id = tc.id
            AND ts.date = (SELECT MAX(date) FROM trend_snapshots WHERE category_id = tc.id)
        LEFT JOIN trend_snapshots prev ON prev.category_id = tc.id
            AND prev.date = (
                SELECT MAX(date) FROM trend_snapshots
                WHERE category_id = tc.id AND date < ts.date
            )
        ORDER BY COALESCE(ts.momentum_score, 0) DESC
        """)
    )

    rising, stable, declining = [], [], []
    for row in result.fetchall():
        d = dict(row._mapping)
        score = float(d.get("momentum_score") or 0)
        prev = float(d.get("prev_momentum_score") or 0)
        item = {
            "category": {
                "id": d["id"], "name": d["name"], "slug": d["slug"],
                "icon": d["icon"], "color_hex": d["color_hex"],
            },
            "momentum_score": score,
            "change_vs_last_week": round(score - prev, 2),
            "repo_count": d.get("repo_count") or 0,
            "stars_gained_week": d.get("stars_gained_week") or 0,
        }
        status = d.get("radar_status") or "stable"
        if status == "rising":
            rising.append(item)
        elif status == "declining":
            declining.append(item)
        else:
            stable.append(item)

    response = {
        "rising": sorted(rising, key=lambda x: x["momentum_score"], reverse=True),
        "stable": sorted(stable, key=lambda x: x["momentum_score"], reverse=True),
        "declining": sorted(declining, key=lambda x: x["momentum_score"], reverse=True),
        "as_of": today.isoformat(),
    }
    await cache_set(cache_key, response, settings.CACHE_TTL_TRENDS)
    return response


@router.get("/{category_slug}", response_model=CategoryTrendDetail)
async def get_category_trend(
    category_slug: str,
    period: str = "30d",
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"trend:category:{category_slug}:{period}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)

    cat_result = await db.execute(
        text("SELECT id, name, slug, icon, color_hex FROM technology_categories WHERE slug = :slug"),
        {"slug": category_slug},
    )
    cat = cat_result.fetchone()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat_dict = dict(cat._mapping)

    snapshots_result = await db.execute(
        text("""
        SELECT date, total_stars, repo_count, stars_gained_week, momentum_score, radar_status
        FROM trend_snapshots
        WHERE category_id = :cid AND date >= CURRENT_DATE - CAST(:days AS INTEGER)
        ORDER BY date ASC
        """),
        {"cid": cat_dict["id"], "days": days},
    )
    snapshots = []
    for r in snapshots_result.fetchall():
        d = dict(r._mapping)
        d["momentum_score"] = float(d.get("momentum_score") or 0)
        snapshots.append(d)

    repos_result = await db.execute(
        text("""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics,
               r.github_created_at, r.first_seen_at
        FROM repositories r
        JOIN repository_categories rc ON rc.repository_id = r.id
        WHERE rc.category_id = :cid AND r.is_archived = FALSE
        ORDER BY r.momentum_score DESC
        LIMIT 10
        """),
        {"cid": cat_dict["id"]},
    )
    top_repos = []
    for r in repos_result.fetchall():
        d = dict(r._mapping)
        d["momentum_score"] = float(d.get("momentum_score") or 0)
        d["topics"] = d.get("topics") or []
        d["categories"] = []
        top_repos.append(d)

    latest_snap = snapshots[-1] if snapshots else {}
    response = {
        "category": cat_dict,
        "snapshots": snapshots,
        "top_repos": top_repos,
        "current_momentum": latest_snap.get("momentum_score", 0),
        "radar_status": latest_snap.get("radar_status", "stable"),
    }
    await cache_set(cache_key, response, settings.CACHE_TTL_TRENDS)
    return response
