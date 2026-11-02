"""
Trend scoring and category classification service.
"""

import logging
import math
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import (
    DailyMetric, Repository, RepositoryCategory,
    TechnologyCategory, TrendSnapshot, WeeklyMetric,
)

logger = logging.getLogger(__name__)

# p95 reference values for normalization (tuned empirically)
P95_STARS_WEEK = 3000
P95_FORKS_WEEK = 500
P95_CONTRIBUTORS = 50
P95_COMMITS = 100
P95_ISSUES = 80


def normalize_log(value: int, p95: int) -> float:
    """Map value to [0, 1] using log scale. p95 → ~0.95."""
    if value <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(p95), 1.0)


MOMENTUM_WEIGHTS = {
    "stars": 0.45,
    "forks": 0.20,
    "contributors": 0.20,
    "commits": 0.10,
    "issues": 0.05,
}

# Star-anomaly heuristic: a big weekly star jump with almost no activity behind it.
ANOMALY_MIN_STARS_WEEK = 500
ANOMALY_MAX_ACTIVITY = 0.15


def momentum_breakdown(
    stars_gained_week: int,
    forks_gained: int,
    new_contributors: int,
    commit_activity: int,
    issues_opened: int,
    age_days: int,
) -> dict:
    """
    Per-signal contribution (in score points, before the recency multiplier)
    plus the multiplier itself. The parts sum to the raw score.
    """
    normalized = {
        "stars": normalize_log(stars_gained_week, P95_STARS_WEEK),
        "forks": normalize_log(forks_gained, P95_FORKS_WEEK),
        "contributors": normalize_log(new_contributors, P95_CONTRIBUTORS),
        "commits": normalize_log(commit_activity, P95_COMMITS),
        "issues": normalize_log(issues_opened, P95_ISSUES),
    }
    parts = {k: v * MOMENTUM_WEIGHTS[k] * 100 for k, v in normalized.items()}
    recency = 1.2 if age_days < 30 else (1.1 if age_days < 90 else 1.0)

    activity = (normalized["forks"] + normalized["contributors"] + normalized["commits"]) / 3
    star_anomaly = stars_gained_week >= ANOMALY_MIN_STARS_WEEK and activity < ANOMALY_MAX_ACTIVITY

    return {"parts": parts, "recency_multiplier": recency, "star_anomaly": star_anomaly}


def compute_momentum_score(
    stars_gained_week: int,
    forks_gained: int,
    new_contributors: int,
    commit_activity: int,
    issues_opened: int,
    age_days: int,
) -> float:
    """
    Composite momentum score 0–100.
    Star velocity is the dominant signal (~45%).
    Recency bonus for repos < 30 days old.
    """
    b = momentum_breakdown(
        stars_gained_week, forks_gained, new_contributors,
        commit_activity, issues_opened, age_days,
    )
    raw = sum(b["parts"].values())
    return round(min(raw * b["recency_multiplier"], 100.0), 2)


def classify_radar_status(score: float, prev_score: float | None) -> str:
    """Classify into rising / stable / declining based on score and trend."""
    if prev_score is None:
        # No week-over-week baseline yet (e.g. first week): judge on absolute
        # momentum, but don't pessimistically mark healthy mid-range categories
        # as "declining" just because there's nothing to compare against.
        if score >= 45:
            return "rising"
        if score >= 18:
            return "stable"
        return "declining"

    # With a baseline, the trend (delta) is the real signal.
    delta = score - prev_score
    if delta > 3:
        return "rising"
    if delta < -3:
        return "declining"
    return "stable"


async def compute_daily_gains(session: AsyncSession, today: date) -> int:
    """
    For all repos, compute stars_gained = today_stars - yesterday_stars.
    Updates both daily_metrics.stars_gained and repositories cached columns.
    Returns count of repos updated.
    """
    yesterday = today - timedelta(days=1)

    result = await session.execute(
        text("""
        UPDATE daily_metrics d
        SET stars_gained = d.stars_total - COALESCE(
            (SELECT prev.stars_total FROM daily_metrics prev
             WHERE prev.repository_id = d.repository_id
               AND prev.date = :yesterday),
            d.stars_total
        )
        WHERE d.date = :today
        RETURNING d.repository_id
        """),
        {"today": today, "yesterday": yesterday},
    )
    updated_ids = [r[0] for r in result.fetchall()]

    # Update denormalized cache on repositories
    if updated_ids:
        await session.execute(
            text("""
            UPDATE repositories r
            SET stars_gained_today = COALESCE(
                (SELECT stars_gained FROM daily_metrics
                 WHERE repository_id = r.id AND date = :today), 0
            ),
            updated_at = NOW()
            WHERE id = ANY(:ids)
            """),
            {"today": today, "ids": updated_ids},
        )

    await session.commit()
    return len(updated_ids)


async def compute_weekly_metrics(session: AsyncSession, week_start: date) -> int:
    """
    Aggregate daily_metrics for the week into weekly_metrics.
    Compute momentum score per repo.
    """
    week_end = week_start + timedelta(days=6)

    # Aggregate weekly data
    result = await session.execute(
        text("""
        INSERT INTO weekly_metrics
            (repository_id, week_start, stars_gained, forks_gained, new_contributors, commit_activity)
        SELECT
            repository_id,
            :week_start,
            COALESCE(SUM(stars_gained), 0),
            COALESCE(SUM(forks_gained), 0),
            -- contributors gained across the week (growth within the window)
            GREATEST(COALESCE(MAX(contributors_count) - MIN(contributors_count), 0), 0),
            COALESCE(MAX(commit_count_week), 0)
        FROM daily_metrics
        WHERE date BETWEEN :week_start AND :week_end
        GROUP BY repository_id
        ON CONFLICT (repository_id, week_start) DO UPDATE
            SET stars_gained     = EXCLUDED.stars_gained,
                forks_gained     = EXCLUDED.forks_gained,
                new_contributors = EXCLUDED.new_contributors,
                commit_activity  = EXCLUDED.commit_activity
        RETURNING repository_id
        """),
        {"week_start": week_start, "week_end": week_end},
    )
    repo_ids = [r[0] for r in result.fetchall()]

    if not repo_ids:
        await session.commit()
        return 0

    # Score all repos in Python from a single SELECT, then bulk-update.
    # (Was a per-repo loop of ~3 queries each — thousands of round-trips to a
    # remote DB. Now: one SELECT + two executemany UPDATEs.)
    rows = (
        await session.execute(
            text("""
            SELECT w.repository_id, w.stars_gained, w.forks_gained, w.new_contributors,
                   w.commit_activity, w.issues_opened,
                   EXTRACT(EPOCH FROM (NOW() - r.github_created_at))/86400 AS age_days
            FROM weekly_metrics w
            JOIN repositories r ON r.id = w.repository_id
            WHERE w.week_start = :ws
            """),
            {"ws": week_start},
        )
    ).fetchall()

    weekly_updates = []
    repo_updates = []
    for m in rows:
        score = compute_momentum_score(
            m.stars_gained, m.forks_gained, m.new_contributors or 0,
            m.commit_activity or 0, m.issues_opened or 0,
            int(m.age_days or 0),
        )
        weekly_updates.append({"score": score, "rid": m.repository_id, "ws": week_start})
        repo_updates.append({"score": score, "sw": m.stars_gained or 0, "rid": m.repository_id})

    if weekly_updates:
        await session.execute(
            text("UPDATE weekly_metrics SET momentum_score = :score "
                 "WHERE repository_id = :rid AND week_start = :ws"),
            weekly_updates,
        )
        await session.execute(
            text("UPDATE repositories SET momentum_score = :score, stars_gained_week = :sw "
                 "WHERE id = :rid"),
            repo_updates,
        )

    await session.commit()
    return len(repo_ids)


async def aggregate_category_snapshots(session: AsyncSession, snapshot_date: date) -> None:
    """Build trend_snapshots by aggregating repos per category."""
    categories = (await session.execute(select(TechnologyCategory))).scalars().all()

    # Get last week's snapshots for radar classification
    last_week = snapshot_date - timedelta(days=7)

    for cat in categories:
        # Sum star velocity for all repos in this category
        result = await session.execute(
            text("""
            SELECT
                COUNT(DISTINCT r.id)                  AS repo_count,
                COALESCE(SUM(r.latest_stars), 0)      AS total_stars,
                COALESCE(SUM(r.stars_gained_week), 0) AS stars_gained_week,
                COALESCE(SUM(r.latest_forks), 0)      AS contributor_count,
                -- category momentum reflects the leaders, not the dormant long tail:
                -- average of the top 10 repos by momentum in the category
                COALESCE((
                    SELECT AVG(t.momentum_score) FROM (
                        SELECT r2.momentum_score
                        FROM repositories r2
                        JOIN repository_categories rc2 ON rc2.repository_id = r2.id
                        WHERE rc2.category_id = :cid AND r2.is_archived = FALSE
                        ORDER BY r2.momentum_score DESC
                        LIMIT 10
                    ) t
                ), 0)                                 AS avg_momentum
            FROM repositories r
            JOIN repository_categories rc ON rc.repository_id = r.id
            WHERE rc.category_id = :cid
              AND r.is_archived = FALSE
            """),
            {"cid": cat.id},
        )
        row = result.fetchone()
        if not row or row.repo_count == 0:
            continue

        # Get previous week's score for radar delta
        prev_result = await session.execute(
            text("SELECT momentum_score FROM trend_snapshots WHERE category_id = :cid AND date = :d"),
            {"cid": cat.id, "d": last_week},
        )
        prev_row = prev_result.fetchone()
        prev_score = float(prev_row.momentum_score) if prev_row else None
        current_score = float(row.avg_momentum or 0)

        radar = classify_radar_status(current_score, prev_score)

        await session.execute(
            text("""
            INSERT INTO trend_snapshots
              (category_id, date, total_stars, repo_count, stars_gained_week, momentum_score, radar_status)
            VALUES (:cid, :d, :ts, :rc, :sw, :ms, :rs)
            ON CONFLICT (category_id, date) DO UPDATE
              SET total_stars = EXCLUDED.total_stars,
                  repo_count = EXCLUDED.repo_count,
                  stars_gained_week = EXCLUDED.stars_gained_week,
                  momentum_score = EXCLUDED.momentum_score,
                  radar_status = EXCLUDED.radar_status
            """),
            {
                "cid": cat.id, "d": snapshot_date, "ts": int(row.total_stars),
                "rc": row.repo_count, "sw": int(row.stars_gained_week),
                "ms": round(current_score, 2), "rs": radar,
            },
        )

    await session.commit()


async def classify_repo_categories(
    session: AsyncSession, repo_id: int, topics: list[str], language: str | None
) -> list[int]:
    """
    Auto-classify a repository into technology categories based on
    its GitHub topics and language.
    Returns list of matched category IDs.
    """
    cats = (await session.execute(select(TechnologyCategory))).scalars().all()
    matched: list[tuple[int, float]] = []

    for cat in cats:
        score = 0.0
        topics_lower = {t.lower() for t in (topics or [])}
        keywords_lower = {k.lower() for k in (cat.keywords or [])}
        github_topics_lower = {t.lower() for t in (cat.github_topics or [])}

        # Direct topic match (high confidence)
        topic_hits = topics_lower & github_topics_lower
        score += len(topic_hits) * 0.5

        # Keyword match in topics or language
        kw_hits = topics_lower & keywords_lower
        score += len(kw_hits) * 0.3

        if language and language.lower() in keywords_lower:
            score += 0.1

        if score > 0:
            matched.append((cat.id, min(score, 1.0)))

    if matched:
        for cat_id, confidence in matched:
            await session.execute(
                text("""
                INSERT INTO repository_categories (repository_id, category_id, confidence, tagged_by)
                VALUES (:rid, :cid, :conf, 'auto')
                ON CONFLICT (repository_id, category_id) DO UPDATE
                SET confidence = GREATEST(repository_categories.confidence, EXCLUDED.confidence)
                """),
                {"rid": repo_id, "cid": cat_id, "conf": confidence},
            )

    return [c[0] for c in matched]
