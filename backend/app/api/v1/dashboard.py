from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.schemas.repository import DashboardResponse

router = APIRouter()

AI_CATEGORY_SLUGS = ["ai-agents", "mcp-servers", "llm-frameworks", "coding-assistants", "vector-databases"]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    cache_key = "dashboard:v2"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Top gaining today
    top_today_result = await db.execute(
        text("""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics, r.github_created_at,
               r.first_seen_at
        FROM repositories r
        WHERE r.is_archived = FALSE
        ORDER BY r.stars_gained_today DESC
        LIMIT 15
        """)
    )
    top_today = [dict(row._mapping) for row in top_today_result.fetchall()]

    # Top gaining this week
    top_week_result = await db.execute(
        text("""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics, r.github_created_at,
               r.first_seen_at
        FROM repositories r
        WHERE r.is_archived = FALSE
        ORDER BY r.stars_gained_week DESC
        LIMIT 15
        """)
    )
    top_week = [dict(row._mapping) for row in top_week_result.fetchall()]

    # Trending categories with top repos
    cats_result = await db.execute(
        text("""
        SELECT tc.id, tc.name, tc.slug, tc.icon, tc.color_hex,
               ts.momentum_score, ts.stars_gained_week, ts.repo_count, ts.radar_status
        FROM technology_categories tc
        LEFT JOIN trend_snapshots ts ON ts.category_id = tc.id
            AND ts.date = (SELECT MAX(date) FROM trend_snapshots WHERE category_id = tc.id)
        ORDER BY COALESCE(ts.momentum_score, 0) DESC
        LIMIT 8
        """)
    )
    trending_categories = []
    for row in cats_result.fetchall():
        cat_data = dict(row._mapping)
        # Top 3 repos per category
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
            LIMIT 3
            """),
            {"cid": cat_data["id"]},
        )
        top_repos = [dict(r._mapping) for r in repos_result.fetchall()]
        trending_categories.append({
            "category": {
                "id": cat_data["id"],
                "name": cat_data["name"],
                "slug": cat_data["slug"],
                "icon": cat_data["icon"],
                "color_hex": cat_data["color_hex"],
            },
            "momentum_score": float(cat_data.get("momentum_score") or 0),
            "stars_gained_week": cat_data.get("stars_gained_week") or 0,
            "repo_count": cat_data.get("repo_count") or 0,
            "radar_status": cat_data.get("radar_status") or "stable",
            "top_repos": _format_repo_list(top_repos),
        })

    # AI ecosystem
    ai_result = await db.execute(
        text("""
        SELECT DISTINCT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics, r.github_created_at, r.first_seen_at
        FROM repositories r
        JOIN repository_categories rc ON rc.repository_id = r.id
        JOIN technology_categories tc ON tc.id = rc.category_id
        WHERE tc.slug = ANY(:slugs) AND r.is_archived = FALSE
        ORDER BY r.stars_gained_week DESC
        LIMIT 5
        """),
        {"slugs": AI_CATEGORY_SLUGS},
    )
    ai_ecosystem = _format_repo_list([dict(r._mapping) for r in ai_result.fetchall()])

    # New entrants (first seen < 14 days, high momentum)
    new_result = await db.execute(
        text("""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics, r.github_created_at, r.first_seen_at
        FROM repositories r
        WHERE r.first_seen_at >= NOW() - INTERVAL '14 days'
          AND r.is_archived = FALSE
        ORDER BY r.momentum_score DESC
        LIMIT 5
        """)
    )
    new_entrants = _format_repo_list([dict(r._mapping) for r in new_result.fetchall()])

    await _attach_verdicts(db, top_today)
    await _attach_verdicts(db, top_week)
    await _attach_prev_ranks(db, top_today)

    # Data freshness — how much real history we've actually accumulated.
    fresh = (
        await db.execute(
            text("SELECT MIN(date) AS since, COUNT(DISTINCT date) AS days FROM daily_metrics")
        )
    ).fetchone()
    data_since = fresh._mapping["since"] if fresh else None
    snapshot_days = int(fresh._mapping["days"] or 0) if fresh else 0

    response = {
        "top_gaining_today": _format_repo_list(top_today),
        "top_gaining_week": _format_repo_list(top_week),
        "trending_categories": trending_categories,
        "ai_ecosystem": ai_ecosystem,
        "new_entrants": new_entrants,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_since": data_since.isoformat() if data_since else None,
        "snapshot_days": snapshot_days,
    }

    await cache_set(cache_key, response, settings.CACHE_TTL_DASHBOARD)
    return response


def _format_repo_list(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["momentum_score"] = float(r.get("momentum_score") or 0)
        r["topics"] = r.get("topics") or []
        r["categories"] = []
        r.setdefault("verdict", None)
        r.setdefault("prev_rank", None)
    return rows


async def _attach_prev_ranks(db: AsyncSession, rows: list[dict]) -> None:
    """Attach each repo's rank on the previous day's stars-gained board (for ▲/▼ arrows)."""
    ids = [r["id"] for r in rows]
    if not ids:
        return
    res = await db.execute(
        text(
            """
            WITH prev AS (
                SELECT DISTINCT date FROM daily_metrics ORDER BY date DESC OFFSET 1 LIMIT 1
            )
            SELECT repository_id, rnk FROM (
                SELECT dm.repository_id,
                       RANK() OVER (ORDER BY dm.stars_gained DESC) AS rnk
                FROM daily_metrics dm
                JOIN repositories r ON r.id = dm.repository_id AND r.is_archived = FALSE
                WHERE dm.date = (SELECT date FROM prev)
            ) ranked
            WHERE repository_id = ANY(:ids)
            """
        ),
        {"ids": ids},
    )
    rmap = {m["repository_id"]: int(m["rnk"]) for m in (row._mapping for row in res.fetchall())}
    for r in rows:
        r["prev_rank"] = rmap.get(r["id"])


async def _attach_verdicts(db: AsyncSession, rows: list[dict]) -> None:
    """Attach the latest AI 'verdict' one-liner to each repo dict (if one exists)."""
    ids = [r["id"] for r in rows]
    if not ids:
        return
    res = await db.execute(
        text(
            """
            SELECT DISTINCT ON (subject_id) subject_id, verdict, summary
            FROM insight_reports
            WHERE report_type = 'repository' AND subject_id = ANY(:ids)
            ORDER BY subject_id, generated_at DESC
            """
        ),
        {"ids": ids},
    )
    vmap = {
        m["subject_id"]: (m["verdict"] or m["summary"])
        for m in (row._mapping for row in res.fetchall())
    }
    for r in rows:
        r["verdict"] = vmap.get(r["id"])
