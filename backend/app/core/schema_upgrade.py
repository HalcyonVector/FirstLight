"""
Idempotent schema additions on top of infra/schema.sql.

The refresh pipeline applies these before every run (and the API tries once at
startup), so new tables appear on the hosted database without a manual
migration step. Every statement is safe to run repeatedly.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DDL = [
    # Growth-curve stage, recomputed every scoring run.
    "ALTER TABLE repositories ADD COLUMN IF NOT EXISTS lifecycle VARCHAR(20)",
    # Weekly breakout predictions and whether they came true.
    """
    CREATE TABLE IF NOT EXISTS breakout_calls (
        id               BIGSERIAL PRIMARY KEY,
        repository_id    BIGINT NOT NULL UNIQUE REFERENCES repositories(id) ON DELETE CASCADE,
        called_on        DATE NOT NULL,
        stars_at_call    INT NOT NULL,
        gain7_at_call    INT NOT NULL,
        accel            NUMERIC(6,2) NOT NULL,
        hit_on           DATE,
        best_rank        INT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_calls_called_on ON breakout_calls(called_on DESC)",
    # Recent GitHub releases for top and watched repos.
    """
    CREATE TABLE IF NOT EXISTS repo_releases (
        id               BIGSERIAL PRIMARY KEY,
        repository_id    BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        tag              VARCHAR(200) NOT NULL,
        name             VARCHAR(300),
        published_at     TIMESTAMPTZ NOT NULL,
        url              TEXT,
        prerelease       BOOLEAN NOT NULL DEFAULT FALSE,
        snippet          VARCHAR(300),
        UNIQUE (repository_id, tag)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_releases_published ON repo_releases(published_at DESC)",
    # Stargazer samples stopped working when GitHub hid stargazer lists (June 2026);
    # the table never held rows in production.
    "DROP TABLE IF EXISTS star_quality",
    # This week's stars vs. forks for fast growers, rebuilt every run.
    """
    CREATE TABLE IF NOT EXISTS star_activity (
        repository_id    BIGINT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
        checked_on       DATE NOT NULL,
        stars_week       INT NOT NULL,
        forks_week       INT NOT NULL,
        typical_ratio    NUMERIC(6,4) NOT NULL,
        verdict          VARCHAR(20) NOT NULL
    )
    """,
    # Odds a call comes true, from the model in call_model at the time of the call.
    "ALTER TABLE breakout_calls ADD COLUMN IF NOT EXISTS prob NUMERIC(4,3)",
    # Days a repo's stars jumped, and what we found behind each jump.
    """
    CREATE TABLE IF NOT EXISTS star_spikes (
        id               BIGSERIAL PRIMARY KEY,
        repository_id    BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        spike_date       DATE NOT NULL,
        gain             INT NOT NULL,
        baseline         INT NOT NULL,
        causes           JSONB NOT NULL DEFAULT '[]'::jsonb,
        checked_at       TIMESTAMPTZ,
        UNIQUE (repository_id, spike_date)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_spikes_date ON star_spikes(spike_date DESC)",
    # Which version of the cause-matching rules a spike was explained with.
    "ALTER TABLE star_spikes ADD COLUMN IF NOT EXISTS rule SMALLINT NOT NULL DEFAULT 1",
    # The fitted odds model and its backtest (one row, replaced daily).
    """
    CREATE TABLE IF NOT EXISTS call_model (
        id               SMALLINT PRIMARY KEY DEFAULT 1,
        trained_on       DATE NOT NULL,
        samples          INT NOT NULL,
        positives        INT NOT NULL,
        base_rate        INT NOT NULL,
        model            JSONB NOT NULL,
        backtest         JSONB
    )
    """,
    # Per repo: its biggest week, where it is now, and when it fell to half.
    """
    CREATE TABLE IF NOT EXISTS hype_curves (
        repository_id    BIGINT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
        peak_on          DATE NOT NULL,
        peak_gain7       INT NOT NULL,
        now_gain7        INT NOT NULL,
        half_on          DATE,
        commits_peak     INT NOT NULL DEFAULT 0,
        commits_now      INT NOT NULL DEFAULT 0,
        as_of            DATE NOT NULL
    )
    """,
    # Same columns as the UNIQUE (repository_id, date) index, which Postgres
    # can already scan in either direction. Dropping it frees ~15-20 MB.
    "DROP INDEX IF EXISTS idx_daily_repo_date",
]


async def ensure_schema(session: AsyncSession) -> None:
    # Give up quickly rather than queue behind a long pipeline transaction.
    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    for stmt in DDL:
        await session.execute(text(stmt))
    await session.commit()


async def storage_report(session: AsyncSession) -> tuple[int, list[tuple[str, int]]]:
    """Total database size and the largest tables (bytes, including indexes)."""
    total = (await session.execute(text("SELECT pg_database_size(current_database())"))).scalar()
    rows = (
        await session.execute(
            text(
                """
                SELECT relname, pg_total_relation_size(relid) AS bytes
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY bytes DESC
                LIMIT 8
                """
            )
        )
    ).fetchall()
    return int(total or 0), [(r[0], int(r[1])) for r in rows]
