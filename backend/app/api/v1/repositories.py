from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.database import get_db
from app.models.repository import InsightReport, Repository, RepositoryCategory
from app.schemas.repository import PaginatedRepos, RepoDetail, RepoMetricsResponse
from app.services.trend_service import momentum_breakdown

router = APIRouter()


@router.get("", response_model=PaginatedRepos)
async def list_repositories(
    sort: Literal["stars_gained_today", "stars_gained_week", "momentum_score", "latest_stars"] = "stars_gained_week",
    language: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    cache_key = f"repos:list:{sort}:{language}:{category}:{page}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    offset = (page - 1) * limit

    filters = ["r.is_archived = FALSE"]
    params: dict = {"limit": limit, "offset": offset}

    if language:
        filters.append("r.language = :language")
        params["language"] = language

    category_join = ""
    if category:
        category_join = """
        JOIN repository_categories rc ON rc.repository_id = r.id
        JOIN technology_categories tc ON tc.id = rc.category_id AND tc.slug = :category_slug
        """
        params["category_slug"] = category

    where = " AND ".join(filters)
    sort_col = {
        "stars_gained_today": "r.stars_gained_today",
        "stars_gained_week": "r.stars_gained_week",
        "momentum_score": "r.momentum_score",
        "latest_stars": "r.latest_stars",
    }[sort]

    query = text(f"""
        SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
               r.latest_stars, r.stars_gained_today, r.stars_gained_week,
               r.latest_forks, r.momentum_score, r.topics,
               r.github_created_at, r.first_seen_at
        FROM repositories r
        {category_join}
        WHERE {where}
        ORDER BY {sort_col} DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)

    count_query = text(f"""
        SELECT COUNT(DISTINCT r.id)
        FROM repositories r
        {category_join}
        WHERE {where}
    """)

    result = await db.execute(query, params)
    rows = [dict(r._mapping) for r in result.fetchall()]

    total_result = await db.execute(count_query, params)
    total = total_result.scalar() or 0

    items = []
    for r in rows:
        r["momentum_score"] = float(r.get("momentum_score") or 0)
        r["topics"] = r.get("topics") or []
        r["categories"] = []
        items.append(r)

    response = {
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if total else 0,
        "limit": limit,
    }

    await cache_set(cache_key, response, settings.CACHE_TTL_REPO_DETAIL)
    return response


@router.get("/{repo_id}", response_model=RepoDetail)
async def get_repository(repo_id: int, db: AsyncSession = Depends(get_db)):
    cache_key = f"repos:detail:{repo_id}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    result = await db.execute(
        select(Repository)
        .options(
            # Load each link's category too: async sessions can't lazy-load,
            # so touching rc.category later would raise MissingGreenlet (a 500).
            selectinload(Repository.categories).selectinload(RepositoryCategory.category),
        )
        .where(Repository.id == repo_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Get latest fresh insight
    insight_result = await db.execute(
        select(InsightReport)
        .where(
            InsightReport.subject_id == repo_id,
            InsightReport.report_type == "repository",
        )
        .order_by(InsightReport.generated_at.desc())
        .limit(1)
    )
    latest_insight = insight_result.scalar_one_or_none()

    # Latest scored week, broken into the signals that made up the score
    wk = (
        await db.execute(
            text("""
            SELECT week_start, stars_gained, forks_gained, new_contributors,
                   commit_activity, issues_opened
            FROM weekly_metrics
            WHERE repository_id = :rid
            ORDER BY week_start DESC
            LIMIT 1
            """),
            {"rid": repo_id},
        )
    ).fetchone()
    breakdown = None
    if wk:
        age_days = (
            (datetime.now(timezone.utc) - repo.github_created_at).days
            if repo.github_created_at else 365
        )
        b = momentum_breakdown(
            wk.stars_gained or 0, wk.forks_gained or 0, wk.new_contributors or 0,
            wk.commit_activity or 0, wk.issues_opened or 0, age_days,
        )
        breakdown = {
            "parts": {k: round(v, 1) for k, v in b["parts"].items()},
            "recency_multiplier": b["recency_multiplier"],
            "star_anomaly": b["star_anomaly"],
            "week_start": wk.week_start,
        }

    data = {
        "id": repo.id,
        "github_id": repo.github_id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "name": repo.name,
        "description": repo.description,
        "language": repo.language,
        "license": repo.license,
        "topics": repo.topics or [],
        "homepage_url": repo.homepage_url,
        "is_archived": bool(repo.is_archived),
        "is_fork": bool(repo.is_fork),
        "latest_stars": repo.latest_stars or 0,
        "latest_forks": repo.latest_forks or 0,
        "stars_gained_today": repo.stars_gained_today or 0,
        "stars_gained_week": repo.stars_gained_week or 0,
        "momentum_score": float(repo.momentum_score or 0),
        "github_created_at": repo.github_created_at,
        "github_pushed_at": repo.github_pushed_at,
        "first_seen_at": repo.first_seen_at,
        "last_synced_at": repo.last_synced_at,
        "categories": [
            {
                "id": rc.category.id,
                "name": rc.category.name,
                "slug": rc.category.slug,
                "icon": rc.category.icon,
                "color_hex": rc.category.color_hex,
            }
            for rc in repo.categories
            if rc.category
        ],
        "latest_insight": _format_insight(latest_insight) if latest_insight else None,
        "momentum_breakdown": breakdown,
        **await _enrichment(db, repo_id),
    }

    await cache_set(cache_key, data, settings.CACHE_TTL_REPO_DETAIL)
    return data


@router.get("/{repo_id}/metrics", response_model=RepoMetricsResponse)
async def get_repository_metrics(
    repo_id: int,
    period: Literal["7d", "30d", "90d", "1y"] = "30d",
    db: AsyncSession = Depends(get_db),
):
    days = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}[period]

    daily_result = await db.execute(
        text("""
        SELECT date, stars_total, forks_total,
               COALESCE(stars_gained, 0) AS stars_gained,
               COALESCE(forks_gained, 0) AS forks_gained,
               COALESCE(open_issues, 0) AS open_issues,
               COALESCE(contributors_count, 0) AS contributors_count,
               COALESCE(commit_count_week, 0) AS commit_count_week
        FROM daily_metrics
        WHERE repository_id = :rid
          AND date >= CURRENT_DATE - CAST(:days AS INTEGER)
        ORDER BY date ASC
        """),
        {"rid": repo_id, "days": days},
    )
    daily = [dict(r._mapping) for r in daily_result.fetchall()]

    weekly_result = await db.execute(
        text("""
        SELECT week_start,
               COALESCE(stars_gained, 0) AS stars_gained,
               COALESCE(forks_gained, 0) AS forks_gained,
               COALESCE(new_contributors, 0) AS new_contributors,
               COALESCE(commit_activity, 0) AS commit_activity,
               momentum_score
        FROM weekly_metrics
        WHERE repository_id = :rid
          AND week_start >= CURRENT_DATE - CAST(:days AS INTEGER)
        ORDER BY week_start ASC
        """),
        {"rid": repo_id, "days": days},
    )
    weekly_raw = weekly_result.fetchall()
    weekly = []
    for r in weekly_raw:
        d = dict(r._mapping)
        d["momentum_score"] = float(d.get("momentum_score") or 0)
        weekly.append(d)

    return {"repository_id": repo_id, "daily": daily, "weekly": weekly}


@router.get("/{repo_id}/similar")
async def get_similar(repo_id: int, db: AsyncSession = Depends(get_db)):
    """Repositories that share the most technology categories with this one."""
    result = await db.execute(
        text(
            """
            SELECT r.id, r.full_name, r.owner, r.name, r.description, r.language,
                   r.latest_stars, r.stars_gained_today, r.stars_gained_week,
                   r.latest_forks, r.momentum_score, r.topics,
                   r.github_created_at, r.first_seen_at,
                   COUNT(*) AS shared
            FROM repository_categories rc
            JOIN repositories r ON r.id = rc.repository_id
            WHERE rc.category_id IN (
                SELECT category_id FROM repository_categories WHERE repository_id = :rid
            )
              AND rc.repository_id != :rid
              AND r.is_archived = FALSE
            GROUP BY r.id, r.full_name, r.owner, r.name, r.description, r.language,
                     r.latest_stars, r.stars_gained_today, r.stars_gained_week,
                     r.latest_forks, r.momentum_score, r.topics,
                     r.github_created_at, r.first_seen_at
            ORDER BY shared DESC, r.momentum_score DESC
            LIMIT 6
            """
        ),
        {"rid": repo_id},
    )
    items = []
    for row in result.fetchall():
        d = dict(row._mapping)
        d.pop("shared", None)
        d["momentum_score"] = float(d.get("momentum_score") or 0)
        d["topics"] = d.get("topics") or []
        d["categories"] = []
        items.append(d)
    return {"similar": items}


async def _enrichment(db: AsyncSession, repo_id: int) -> dict:
    """Lifecycle, stargazer sample, releases and breakout call (pipeline-made tables)."""
    try:
        row = (
            await db.execute(
                text(
                    """
                    SELECT r.lifecycle,
                           q.sampled_at, q.sample_size, q.pct_new, q.pct_empty, q.verdict,
                           c.called_on, c.stars_at_call, c.hit_on, c.best_rank
                    FROM repositories r
                    LEFT JOIN star_quality q ON q.repository_id = r.id
                    LEFT JOIN breakout_calls c ON c.repository_id = r.id
                    WHERE r.id = :rid
                    """
                ),
                {"rid": repo_id},
            )
        ).fetchone()
        releases = (
            await db.execute(
                text(
                    """
                    SELECT tag, name, published_at, url, prerelease, snippet
                    FROM repo_releases WHERE repository_id = :rid
                    ORDER BY published_at DESC LIMIT 8
                    """
                ),
                {"rid": repo_id},
            )
        ).fetchall()
    except Exception:  # noqa: BLE001 -- tables not created yet
        await db.rollback()
        return {}

    out: dict = {"lifecycle": row.lifecycle if row else None,
                 "releases": [dict(r._mapping) for r in releases]}
    if row and row.sampled_at:
        out["star_quality"] = {
            "sampled_at": row.sampled_at, "sample_size": row.sample_size,
            "pct_new": row.pct_new, "pct_empty": row.pct_empty, "verdict": row.verdict,
        }
    if row and row.called_on:
        age = (datetime.now(timezone.utc).date() - row.called_on).days
        status = "hit" if row.hit_on else ("miss" if age > settings.CALL_WINDOW_DAYS else "open")
        out["breakout_call"] = {
            "called_on": row.called_on, "stars_at_call": row.stars_at_call,
            "status": status, "hit_on": row.hit_on, "best_rank": row.best_rank,
        }
    out.update(await _explained(db, repo_id, out.get("breakout_call")))
    return out


async def _explained(db: AsyncSession, repo_id: int, call: dict | None) -> dict:
    """Star spikes with their causes, the hype curve, and the call's odds."""
    try:
        spikes = (
            await db.execute(
                text(
                    """
                    SELECT spike_date, gain, baseline, causes FROM star_spikes
                    WHERE repository_id = :rid ORDER BY spike_date DESC LIMIT 6
                    """
                ),
                {"rid": repo_id},
            )
        ).fetchall()
        hype = (
            await db.execute(
                text(
                    """
                    SELECT peak_on, peak_gain7, now_gain7, half_on, commits_peak, commits_now
                    FROM hype_curves WHERE repository_id = :rid
                    """
                ),
                {"rid": repo_id},
            )
        ).fetchone()
        prob = (
            await db.execute(text("SELECT prob FROM breakout_calls WHERE repository_id = :rid"), {"rid": repo_id})
        ).scalar() if call else None
    except Exception:  # noqa: BLE001 -- tables not created yet
        await db.rollback()
        return {}
    out: dict = {
        "spikes": [
            {"date": s.spike_date, "gain": s.gain, "baseline": s.baseline, "causes": s.causes or []}
            for s in spikes
        ],
    }
    if hype:
        out["hype"] = dict(hype._mapping)
    if call is not None and prob is not None:
        call["prob"] = float(prob)
    return out


def _format_insight(insight) -> dict:
    return {
        "id": insight.id,
        "title": insight.title,
        "summary": insight.summary,
        "why_growing": insight.why_growing,
        "what_it_solves": insight.what_it_solves,
        "who_uses_it": insight.who_uses_it,
        "tech_stack": insight.tech_stack,
        "verdict": insight.verdict,
        "competitors": insight.competitors,
        "tags": insight.tags or [],
        "model_used": insight.model_used,
        "generated_at": insight.generated_at or insight.created_at,
    }
