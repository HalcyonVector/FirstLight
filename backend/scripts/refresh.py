"""
Manually run the data pipeline in ONE event loop.

    python scripts/refresh.py            # ingest + compute scores
    python scripts/refresh.py --insights # also generate AI insights (needs Ollama)

Running everything on a single loop avoids the asyncpg "different loop" error you
get from chaining multiple asyncio.run(...) calls.
"""

import asyncio
import logging
import os
import sys
from datetime import date

# Make the app package importable regardless of how this script is invoked
# (running "python scripts/refresh.py" otherwise puts scripts/ on the path, not /app).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.schema_upgrade import ensure_schema, storage_report  # noqa: E402
from app.services.health_service import WarningCounter, health_issues  # noqa: E402
from app.services.notify_service import notify  # noqa: E402
from app.workers import enrichment, explainers  # noqa: E402
from app.workers.ingestion import (  # noqa: E402
    _aggregate_snapshots,
    _compute_trend_scores,
    _generate_ai_insights,
    _ingest_trending_repos,
)

FREE_TIER_BYTES = 500 * 1024 * 1024  # Supabase free plan

# Show the pipeline's own step summaries ("Spikes: 6 found…"); keep libraries at warnings.
logging.basicConfig(level=logging.WARNING, format="    %(message)s")
logging.getLogger("app").setLevel(logging.INFO)
# Counts every app warning so the end-of-run health check can tell a quiet failure.
WARNINGS = WarningCounter()
logging.getLogger("app").addHandler(WARNINGS)


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


async def _enrich() -> list[tuple[str, str]]:
    """Post-scoring steps. One failing step must not cost the others; returns the failures."""
    today = date.today()
    steps = [
        ("call odds model (daily)", lambda s: explainers.train_call_model(s, today)),
        ("lifecycle stages + breakout calls", lambda s: enrichment.update_lifecycles_and_calls(s, today)),
        ("releases", enrichment.fetch_releases),
        ("star activity check", enrichment.check_star_activity),
        ("star spikes", lambda s: explainers.detect_spikes(s, today)),
        ("spike causes (Hacker News, Lobsters, Bluesky, releases)", lambda s: explainers.explain_spikes(s, today)),
        ("hype curves (daily)", lambda s: explainers.update_hype_curves(s, today)),
        ("retention", lambda s: enrichment.prune(s, today)),
    ]
    failed = []
    for label, step in steps:
        print(f"→ {label}…")
        async with AsyncSessionLocal() as session:
            try:
                await step(session)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                print(f"  ! {label} failed: {exc}")
                failed.append((label, str(exc)))
    return failed


async def _report_storage() -> int:
    async with AsyncSessionLocal() as session:
        total, tables = await storage_report(session)
    print(f"→ database size: {_mb(total)} of {_mb(FREE_TIER_BYTES)} ({100 * total / FREE_TIER_BYTES:.0f}%)")
    for name, size in tables:
        print(f"    {name:<24} {_mb(size)}")
    return total


async def _alert(issues: list[str]) -> None:
    """One email to the owner (first ALERT_EMAIL_TO address) listing what went wrong."""
    print("→ health check: " + ("; ".join(issues) if issues else "ok"))
    if not issues:
        return
    lines = "\n".join(f"- {i}" for i in issues)
    body = f"The FirstLight refresh finished with problems:\n\n{lines}"
    try:
        await notify(f"FirstLight refresh: {len(issues)} problem{'s' if len(issues) > 1 else ''}", body,
                     owner_only=True)
    except Exception as exc:  # noqa: BLE001 -- the alert itself must never fail the run
        print(f"  ! alert email failed: {exc}")


async def main(with_insights: bool) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await ensure_schema(session)
        print("→ ingesting trending repos…")
        await _ingest_trending_repos()
        print("→ computing trend scores…")
        await _compute_trend_scores()
        print("→ aggregating category snapshots (Trends/Radar)…")
        await _aggregate_snapshots()
    except Exception as exc:
        # The core pipeline crashed: GitHub also marks the run failed, but say why by email.
        await _alert([f"Refresh stopped before enrichment: {type(exc).__name__}: {str(exc)[:300]}"])
        raise
    failed = await _enrich()
    attempted = 0
    if with_insights:
        print("→ generating AI insights…")
        attempted = await _generate_ai_insights()
    db_bytes = await _report_storage()
    await _alert(health_issues(failed, WARNINGS.counts, WARNINGS.samples, attempted, db_bytes, FREE_TIER_BYTES))
    print("✓ done")


if __name__ == "__main__":
    asyncio.run(main("--insights" in sys.argv))
