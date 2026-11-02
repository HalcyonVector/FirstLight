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
    # Latest stargazer sample per repo (one row, overwritten).
    """
    CREATE TABLE IF NOT EXISTS star_quality (
        repository_id    BIGINT PRIMARY KEY REFERENCES repositories(id) ON DELETE CASCADE,
        sampled_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        sample_size      INT NOT NULL,
        pct_new          INT NOT NULL,
        pct_empty        INT NOT NULL,
        verdict          VARCHAR(20) NOT NULL
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
