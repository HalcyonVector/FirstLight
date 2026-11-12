"""
Queries behind the weekly digest, shared by the email (scripts/send_digest.py)
and the This Week page (/api/v1/digest), so both always show the same thing.
Also the breakout-call track record.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.forecast_service import brier, calibration_bins

# One query shape for both sections. The LATERAL joins pull the freshest daily
# metric (commit / contributor activity, for the hype-vs-substance signal) and
# the primary category, without fanning the row out.
_SELECT = """
    SELECT
        r.id,
        r.full_name,
        r.language,
        r.latest_stars,
        r.latest_forks,
        r.stars_gained_today,
        r.stars_gained_week,
        r.momentum_score,
        r.github_created_at,
        r.description,
        c.name              AS category,
        dm.commit_count_week,
        dm.contributors_count
    FROM repositories r
    LEFT JOIN LATERAL (
        SELECT commit_count_week, contributors_count
        FROM daily_metrics
        WHERE repository_id = r.id
        ORDER BY date DESC
        LIMIT 1
    ) dm ON TRUE
    LEFT JOIN LATERAL (
        SELECT tc.name
        FROM repository_categories rc
        JOIN technology_categories tc ON tc.id = rc.category_id
        WHERE rc.repository_id = r.id
        ORDER BY rc.confidence DESC NULLS LAST
        LIMIT 1
    ) c ON TRUE
"""

MOVERS_SQL = f"""
    {_SELECT}
    WHERE r.is_archived = FALSE AND r.momentum_score > 0
    ORDER BY r.momentum_score DESC
    LIMIT :n
"""

BREAKOUTS_SQL = f"""
    {_SELECT}
    WHERE r.is_archived = FALSE
      AND r.github_created_at >= :cutoff
      AND r.momentum_score >= :minmom
    ORDER BY r.momentum_score DESC
    LIMIT :n
"""

# Newest stable release per repo in the last 7 days, biggest repos first.
SHIPPED_SQL = """
    SELECT * FROM (
        SELECT DISTINCT ON (r.id)
               r.id, r.full_name, r.momentum_score,
               rr.tag, rr.name, rr.published_at, rr.url, rr.snippet
        FROM repo_releases rr
        JOIN repositories r ON r.id = rr.repository_id
        WHERE rr.published_at >= NOW() - INTERVAL '7 days'
          AND rr.prerelease = FALSE
        ORDER BY r.id, rr.published_at DESC
    ) t
    ORDER BY momentum_score DESC
    LIMIT :n
"""


def signal(m) -> bool:
    """True when momentum is backed by real dev activity, not just stars.
    Mirrors the frontend's hype-vs-substance rule."""
    commit = m["commit_count_week"] or 0
    contrib = m["contributors_count"] or 0
    stars = m["latest_stars"] or 0
    fork_ratio = (m["latest_forks"] or 0) / stars if stars else 0.0
    return commit > 0 or contrib > 0 or fork_ratio > 0.04


async def fetch_digest(session: AsyncSession) -> tuple[list, list, list]:
    """(breakouts, movers, shipped) as SQLAlchemy rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.BREAKOUT_MAX_AGE_DAYS)
    movers = (await session.execute(text(MOVERS_SQL), {"n": settings.DIGEST_TOP_N})).fetchall()
    breakouts = (
        await session.execute(
            text(BREAKOUTS_SQL),
            {"cutoff": cutoff, "minmom": settings.BREAKOUT_MIN_MOMENTUM, "n": settings.DIGEST_TOP_N},
        )
    ).fetchall()
    try:
        shipped = (await session.execute(text(SHIPPED_SQL), {"n": 8})).fetchall()
    except Exception:  # noqa: BLE001 -- releases table not created yet
        await session.rollback()
        shipped = []
    return breakouts, movers, shipped


CAUSE_NAMES = {"hn": "Hacker News", "lobsters": "Lobsters", "bluesky": "Bluesky", "release": "a release"}


def cause_text(c: dict) -> str:
    """'Hacker News: "Show HN: X" (412 points)' or 'a release: v2.0'."""
    name = CAUSE_NAMES.get(c.get("kind"), c.get("kind") or "?")
    if c.get("kind") == "release":
        return f"{name}: {c.get('title')}"
    unit = "likes" if c.get("kind") == "bluesky" else "points"
    return f'{name}: "{(c.get("title") or "")[:90]}" ({c.get("points") or 0:,} {unit})'


async def fetch_week_signals(session: AsyncSession) -> dict:
    """
    For the weekly email and This Week page: calls that resolved in the last 7
    days (came true, or ran out of time) and the week's biggest explained spikes.
    """
    today = datetime.now(timezone.utc).date()
    out: dict = {"resolved": [], "spikes": []}
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT c.repository_id AS id, r.full_name, c.called_on, c.stars_at_call,
                           c.hit_on, c.best_rank, c.prob
                    FROM breakout_calls c JOIN repositories r ON r.id = c.repository_id
                    WHERE c.hit_on > CAST(:today AS DATE) - 7
                       OR (c.hit_on IS NULL
                           AND c.called_on + CAST(:window AS INTEGER) BETWEEN CAST(:today AS DATE) - 7
                                                                          AND CAST(:today AS DATE) - 1)
                    ORDER BY c.hit_on DESC NULLS LAST, c.called_on
                    """
                ),
                {"today": today, "window": settings.CALL_WINDOW_DAYS},
            )
        ).fetchall()
        out["resolved"] = [
            {"id": r.id, "full_name": r.full_name, "called_on": r.called_on, "stars_at_call": r.stars_at_call,
             "status": "hit" if r.hit_on else "miss", "hit_on": r.hit_on, "best_rank": r.best_rank,
             "lead_days": (r.hit_on - r.called_on).days if r.hit_on else None,
             "prob": float(r.prob) if r.prob is not None else None}
            for r in rows
        ]
        spikes = (
            await session.execute(
                text(
                    """
                    SELECT s.repository_id AS id, r.full_name, s.spike_date AS date, s.gain, s.baseline, s.causes
                    FROM star_spikes s JOIN repositories r ON r.id = s.repository_id
                    WHERE s.spike_date > CAST(:today AS DATE) - 7 AND s.causes <> '[]'::jsonb
                    ORDER BY s.gain DESC LIMIT 4
                    """
                ),
                {"today": today},
            )
        ).fetchall()
        out["spikes"] = [dict(s._mapping) for s in spikes]
    except Exception:  # noqa: BLE001 -- tables not created yet
        await session.rollback()
    return out


async def call_record(session: AsyncSession) -> dict:
    """
    Every breakout call with its outcome. A call is a hit once the repo reaches
    the weekly top CALL_HIT_RANK, a miss if CALL_WINDOW_DAYS pass first.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT c.repository_id AS id, c.called_on, c.stars_at_call, c.gain7_at_call,
                       c.accel, c.hit_on, c.best_rank, c.prob,
                       r.full_name, r.description, r.language, r.latest_stars,
                       r.stars_gained_week, r.momentum_score
                FROM breakout_calls c
                JOIN repositories r ON r.id = c.repository_id
                ORDER BY c.called_on DESC, c.accel DESC
                """
            )
        )
    ).fetchall()
    today = datetime.now(timezone.utc).date()
    calls, hits, misses, leads = [], 0, 0, []
    scored: list[tuple[float, int]] = []  # (odds, came true) for resolved calls that had odds
    for r in rows:
        if r.hit_on:
            status = "hit"
            hits += 1
            leads.append((r.hit_on - r.called_on).days)
        elif (today - r.called_on).days > settings.CALL_WINDOW_DAYS:
            status = "miss"
            misses += 1
        else:
            status = "open"
        if status != "open" and r.prob is not None:
            scored.append((float(r.prob), int(status == "hit")))
        calls.append({
            "id": r.id,
            "full_name": r.full_name,
            "description": r.description,
            "language": r.language,
            "called_on": r.called_on,
            "stars_at_call": r.stars_at_call,
            "gain7_at_call": r.gain7_at_call,
            "accel": float(r.accel),
            "latest_stars": int(r.latest_stars or 0),
            "stars_gained_week": int(r.stars_gained_week or 0),
            "momentum_score": float(r.momentum_score or 0),
            "status": status,
            "hit_on": r.hit_on,
            "best_rank": r.best_rank,
            "lead_days": (r.hit_on - r.called_on).days if r.hit_on else None,
            "prob": float(r.prob) if r.prob is not None else None,
        })
    resolved = hits + misses
    return {
        "calls": calls,
        "record": {
            "total": len(calls),
            "hits": hits,
            "misses": misses,
            "open": len(calls) - resolved,
            "hit_rate": round(100 * hits / resolved) if resolved else None,
            "avg_lead_days": round(sum(leads) / len(leads), 1) if leads else None,
            "hit_rank": settings.CALL_HIT_RANK,
            "window_days": settings.CALL_WINDOW_DAYS,
        },
        "live_calibration": {
            "n": len(scored),
            "bins": calibration_bins([p for p, _ in scored], [y for _, y in scored]),
            "brier": brier([p for p, _ in scored], [y for _, y in scored]),
        },
    }
