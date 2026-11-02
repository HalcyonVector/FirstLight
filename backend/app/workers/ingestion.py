"""
Celery tasks for GitHub data ingestion and processing.

Schedule (via celery beat):
  - ingest_trending_repos: every 6 hours
  - compute_trend_scores:  every 6 hours (30 min after ingestion)
  - generate_ai_insights:  daily at 02:00 UTC
  - aggregate_snapshots:   daily at 03:00 UTC
"""

import asyncio
import logging
from datetime import date, timedelta

from celery import Celery
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.repository import (
    DailyMetric,
    InsightReport,
    Repository,
    RepositoryCategory,
    TechnologyCategory,
)
from app.services.ai_service import build_summary, generate_repo_insight
from app.services.github_service import (
    MONITORED_LANGUAGES,
    MONITORED_TOPICS,
    github_service,
)
from app.services.trend_service import (
    aggregate_category_snapshots,
    classify_repo_categories,
    compute_daily_gains,
    compute_weekly_metrics,
)

logger = logging.getLogger(__name__)

celery_app = Celery(
    "github_trending",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "ingest-trending-repos": {
            "task": "app.workers.ingestion.ingest_trending_repos",
            "schedule": 21600,  # 6 hours
        },
        "compute-trend-scores": {
            "task": "app.workers.ingestion.compute_trend_scores",
            "schedule": 21600,
            "options": {"countdown": 1800},  # 30 min after ingestion
        },
        "generate-ai-insights": {
            "task": "app.workers.ingestion.generate_ai_insights",
            "schedule": 86400,  # daily
        },
        "aggregate-snapshots": {
            "task": "app.workers.ingestion.aggregate_snapshots_task",
            "schedule": 86400,
        },
    },
)


def run_async(coro):
    """
    Run an async coroutine on a fresh event loop for a sync Celery task.

    The shared async engine pools connections bound to the loop that first used
    them (asyncpg is loop-affine). Since each task runs on a new loop, we dispose
    the engine afterward so the next task doesn't reuse connections from a dead
    loop ("got Future attached to a different loop").
    """
    from app.core.database import engine

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_trending_repos(self):
    """
    Fetch trending repositories from GitHub and upsert into DB.
    Collects from monitored topics + top languages.
    """
    logger.info("Starting trending repo ingestion")
    try:
        run_async(_ingest_trending_repos())
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc)
        raise self.retry(exc=exc)


async def _ingest_trending_repos() -> None:
    seen_ids: set[int] = set()
    all_repos: list[dict] = []

    # Collect from topics
    for topic in MONITORED_TOPICS:
        repos = await github_service.fetch_trending_by_topic(topic, days_pushed=7)
        for r in repos:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_repos.append(github_service.parse_repo_data(r))

    # Collect from monitored languages
    for lang in MONITORED_LANGUAGES:
        repos = await github_service.fetch_trending_by_language(lang, days_pushed=7)
        for r in repos:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_repos.append(github_service.parse_repo_data(r))

    # Two different github_ids can arrive with the same full_name in one run
    # (a rename plus a reuse of the old name); only one can own it. Keep the
    # most-starred and drop the other, or the batched INSERT violates
    # repositories_full_name_key regardless of the pre-step below.
    by_name: dict[str, dict] = {}
    for r in all_repos:
        cur = by_name.get(r["full_name"])
        if cur is None or (r.get("latest_stars") or 0) > (cur.get("latest_stars") or 0):
            by_name[r["full_name"]] = r
    all_repos = list(by_name.values())

    logger.info("Fetched %d unique repos from GitHub", len(all_repos))
    today = date.today()

    if not all_repos:
        logger.info("No repos fetched from GitHub; skipping DB write")
        return

    # Bulk path: a hosted DB (e.g. Supabase) can be far from the runner, so the old
    # per-repo select/flush/classify loop meant ~7 network round-trips per repo
    # (thousands total). Here we do a handful of batched INSERT ... ON CONFLICT
    # statements instead, and commit after each phase so data lands progressively.
    BATCH = 500

    async with AsyncSessionLocal() as session:
        # Load categories ONCE, then classify in Python (was a query per repo).
        cats = (await session.execute(select(TechnologyCategory))).scalars().all()
        cat_index = [
            (
                c.id,
                {k.lower() for k in (c.keywords or [])},
                {t.lower() for t in (c.github_topics or [])},
            )
            for c in cats
        ]

        # 1) Upsert repositories; capture github_id -> id for the child rows.
        gid_to_id: dict[int, int] = {}
        repo_rows = [
            {k: rd[k] for k in rd if k != "open_issues"}  # open_issues -> daily_metrics
            for rd in all_repos
        ]
        for i in range(0, len(repo_rows), BATCH):
            chunk = repo_rows[i:i + BATCH]

            # A repo can be renamed/transferred on GitHub, or a new repo can reuse
            # an owner/name combo that used to belong to a different github_id.
            # Either way, "full_name" collides with a *different* row than the one
            # ON CONFLICT (github_id) is about to touch, which trips the separate
            # repositories_full_name_key unique constraint and aborts the insert.
            # Free up the name first so the real upsert below can't collide.
            # This must also cover rows whose github_id IS in this chunk but
            # whose *current* name is being claimed by a different incoming
            # row (two repos swapping/renaming names in one run) -- the old
            # "github_id != ALL(gids)" filter skipped those and still tripped
            # repositories_full_name_key (e.g. feder-cr/dots, 2026-10-07).
            # Any row holding a wanted name is moved aside unless the incoming
            # row for that name is that same github_id; the upsert then
            # restores/sets the right names.
            await session.execute(
                text(
                    "UPDATE repositories r SET full_name = r.full_name || '-stale-' || r.id "
                    "WHERE r.full_name = ANY(:names) AND NOT EXISTS ("
                    "SELECT 1 FROM unnest(CAST(:gids AS bigint[]), CAST(:names AS text[])) "
                    "AS t(gid, fn) WHERE t.gid = r.github_id AND t.fn = r.full_name)"
                ),
                {
                    "names": [r["full_name"] for r in chunk],
                    "gids": [r["github_id"] for r in chunk],
                },
            )

            stmt = pg_insert(Repository).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["github_id"],
                set_={
                    "full_name": stmt.excluded.full_name,
                    "owner": stmt.excluded.owner,
                    "name": stmt.excluded.name,
                    "latest_stars": stmt.excluded.latest_stars,
                    "latest_forks": stmt.excluded.latest_forks,
                    "latest_watchers": stmt.excluded.latest_watchers,
                    "github_updated_at": stmt.excluded.github_updated_at,
                    "github_pushed_at": stmt.excluded.github_pushed_at,
                    "topics": stmt.excluded.topics,
                    "last_synced_at": func.now(),
                },
            ).returning(Repository.id, Repository.github_id)
            for rid, gid in (await session.execute(stmt)).all():
                gid_to_id[gid] = rid
        await session.commit()

        # 2) Upsert today's daily metric per repo.
        metric_rows = []
        for rd in all_repos:
            rid = gid_to_id.get(rd["github_id"])
            if rid is None:
                continue
            metric_rows.append({
                "repository_id": rid,
                "date": today,
                "stars_total": rd["latest_stars"],
                "forks_total": rd["latest_forks"],
                "watchers": rd["latest_watchers"],
                "open_issues": rd.get("open_issues", 0),
                "releases_count": 0,
            })
        for i in range(0, len(metric_rows), BATCH):
            stmt = pg_insert(DailyMetric).values(metric_rows[i:i + BATCH])
            stmt = stmt.on_conflict_do_update(
                index_elements=["repository_id", "date"],
                set_={
                    "stars_total": stmt.excluded.stars_total,
                    "forks_total": stmt.excluded.forks_total,
                    "watchers": stmt.excluded.watchers,
                },
            )
            await session.execute(stmt)
        await session.commit()

        # 3) Classify in Python, then upsert repository_categories in bulk.
        cat_rows = []
        for rd in all_repos:
            rid = gid_to_id.get(rd["github_id"])
            if rid is None:
                continue
            topics_lower = {t.lower() for t in (rd.get("topics") or [])}
            language = (rd.get("language") or "").lower()
            for cid, keywords, github_topics in cat_index:
                score = (
                    len(topics_lower & github_topics) * 0.5
                    + len(topics_lower & keywords) * 0.3
                    + (0.1 if language and language in keywords else 0.0)
                )
                if score > 0:
                    cat_rows.append({
                        "repository_id": rid,
                        "category_id": cid,
                        "confidence": min(score, 1.0),
                        "tagged_by": "auto",
                    })
        for i in range(0, len(cat_rows), BATCH):
            stmt = pg_insert(RepositoryCategory).values(cat_rows[i:i + BATCH])
            stmt = stmt.on_conflict_do_update(
                index_elements=["repository_id", "category_id"],
                set_={"confidence": func.greatest(
                    RepositoryCategory.confidence, stmt.excluded.confidence
                )},
            )
            await session.execute(stmt)
        await session.commit()

        # 4) Richer signals: fetch contributor + weekly-commit counts for the top
        #    repos by stars and store them on today's metric row. These feed the
        #    contributor (20%) and commit (10%) weights in the momentum score.
        #    Bounded concurrency; each getter already degrades to 0 on failure.
        await _fetch_signals(session, all_repos, gid_to_id, today)

    logger.info("Ingestion complete: %d repos upserted", len(all_repos))


async def _fetch_signals(session, all_repos, gid_to_id, today) -> None:
    top = sorted(all_repos, key=lambda r: r.get("latest_stars", 0), reverse=True)
    top = top[: settings.SIGNALS_TOP_N]
    if not top:
        return
    sem = asyncio.Semaphore(settings.SIGNALS_CONCURRENCY)

    async def _one(rd):
        rid = gid_to_id.get(rd["github_id"])
        if rid is None:
            return None
        async with sem:
            contributors = await github_service.get_contributors_count(rd["owner"], rd["name"])
            commits = await github_service.get_weekly_commit_activity(rd["owner"], rd["name"])
        return {"rid": rid, "contributors": contributors, "commits": commits, "d": today}

    results = [r for r in await asyncio.gather(*[_one(rd) for rd in top]) if r]
    for i in range(0, len(results), 500):
        await session.execute(
            text(
                "UPDATE daily_metrics SET contributors_count = :contributors, "
                "commit_count_week = :commits "
                "WHERE repository_id = :rid AND date = :d"
            ),
            results[i:i + 500],
        )
    await session.commit()
    logger.info("Fetched contributor/commit signals for %d repos", len(results))


@celery_app.task(bind=True, max_retries=2)
def compute_trend_scores(self):
    """Compute daily gains and weekly momentum scores."""
    logger.info("Computing trend scores")
    try:
        run_async(_compute_trend_scores())
    except Exception as exc:
        raise self.retry(exc=exc)


async def _compute_trend_scores() -> None:
    today = date.today()
    # Monday of current week
    week_start = today - timedelta(days=today.weekday())

    async with AsyncSessionLocal() as session:
        updated = await compute_daily_gains(session, today)
        logger.info("Daily gains computed for %d repos", updated)

        await compute_weekly_metrics(session, week_start)
        logger.info("Weekly metrics computed for week %s", week_start)

        # Fire any watchlist push alerts now that momentum is fresh
        try:
            await _dispatch_push_alerts(session)
        except Exception as exc:  # never let alerts break the pipeline
            logger.warning("Push alert dispatch failed: %s", exc)


async def _dispatch_push_alerts(session) -> None:
    """
    Send a Web Push notification when a watched repo crosses a subscriber's
    momentum threshold. Re-arms when the repo drops back below the threshold,
    and prunes dead (expired) subscriptions.
    """
    from app.services.push_service import push_enabled, send_web_push

    if not push_enabled():
        return

    subs = (
        await session.execute(
            text(
                "SELECT id, endpoint, p256dh, auth, repo_ids, threshold, alerted_repo_ids "
                "FROM push_subscriptions"
            )
        )
    ).fetchall()
    if not subs:
        return

    # Collect every watched repo id across all subscriptions in one query
    all_ids: set[int] = set()
    for s in subs:
        all_ids.update(s._mapping["repo_ids"] or [])
    if not all_ids:
        return

    repo_rows = (
        await session.execute(
            text(
                "SELECT id, full_name, name, momentum_score, stars_gained_week "
                "FROM repositories WHERE id = ANY(:ids)"
            ),
            {"ids": list(all_ids)},
        )
    ).fetchall()
    repo_map = {r._mapping["id"]: r._mapping for r in repo_rows}

    sent = 0
    for s in subs:
        sm = s._mapping
        threshold = sm["threshold"]
        alerted = set(sm["alerted_repo_ids"] or [])
        watched = sm["repo_ids"] or []
        new_alerted = set(alerted)
        expired = False

        for rid in watched:
            repo = repo_map.get(rid)
            if not repo:
                continue
            momentum = float(repo["momentum_score"] or 0)

            if momentum >= threshold and rid not in alerted:
                payload = {
                    "title": f"{repo['name']} crossed {threshold}",
                    "body": (
                        f"{repo['full_name']} · momentum {round(momentum)} · "
                        f"+{repo['stars_gained_week']:,} stars/wk"
                    ),
                    "url": f"/repos/{rid}",
                }
                result = send_web_push(
                    {"endpoint": sm["endpoint"], "p256dh": sm["p256dh"], "auth": sm["auth"]},
                    payload,
                )
                if result == "expired":
                    await session.execute(
                        text("DELETE FROM push_subscriptions WHERE id = :id"),
                        {"id": sm["id"]},
                    )
                    expired = True
                    break
                if result == "ok":
                    new_alerted.add(rid)
                    sent += 1
            elif momentum < threshold and rid in alerted:
                # re-arm so it can alert again on the next crossing
                new_alerted.discard(rid)

        if not expired and new_alerted != alerted:
            await session.execute(
                text("UPDATE push_subscriptions SET alerted_repo_ids = :a WHERE id = :id"),
                {"a": list(new_alerted), "id": sm["id"]},
            )

    await session.commit()
    logger.info("Push alerts dispatched: %d sent across %d subscriptions", sent, len(subs))


@celery_app.task(bind=True, max_retries=2)
def aggregate_snapshots_task(self):
    """Aggregate category trend snapshots."""
    logger.info("Aggregating category snapshots")
    try:
        run_async(_aggregate_snapshots())
    except Exception as exc:
        raise self.retry(exc=exc)


async def _aggregate_snapshots() -> None:
    today = date.today()
    async with AsyncSessionLocal() as session:
        await aggregate_category_snapshots(session, today)
        # Retention: keep daily_metrics under Supabase's free-tier size cap.
        cutoff = today - timedelta(days=settings.DATA_RETENTION_DAYS)
        await session.execute(
            text("DELETE FROM daily_metrics WHERE date < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
    logger.info("Category snapshots aggregated for %s", today)


@celery_app.task(bind=True, max_retries=2)
def generate_ai_insights(self):
    """Generate AI insights for top repos that don't have a fresh one."""
    logger.info("Generating AI insights")
    try:
        run_async(_generate_ai_insights())
    except Exception as exc:
        raise self.retry(exc=exc)


async def _generate_ai_insights() -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # Get top repos by momentum without a fresh insight. One row per repo:
        # the category is pulled via a LATERAL (highest-confidence tag) instead of
        # a plain join, so a repo tagged in several categories is not processed
        # multiple times, and "no fresh insight" is a NOT EXISTS to avoid fan-out.
        result = await session.execute(
            text("""
            SELECT r.id, r.full_name, r.description, r.language, r.topics,
                   r.latest_stars, r.stars_gained_week, r.latest_forks,
                   r.github_created_at,
                   c.name as category_name
            FROM repositories r
            LEFT JOIN LATERAL (
                SELECT tc.name
                FROM repository_categories rc
                JOIN technology_categories tc ON tc.id = rc.category_id
                WHERE rc.repository_id = r.id
                ORDER BY rc.confidence DESC NULLS LAST
                LIMIT 1
            ) c ON TRUE
            WHERE r.is_archived = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM insight_reports ir
                  WHERE ir.subject_id = r.id
                    AND ir.report_type = 'repository'
                    AND ir.expires_at > NOW()
              )
              -- An expired but recent insight is still good enough if momentum
              -- has barely moved since it was written; spend the call elsewhere.
              AND NOT EXISTS (
                  SELECT 1 FROM insight_reports ir
                  JOIN LATERAL (
                      SELECT wm.momentum_score
                      FROM weekly_metrics wm
                      WHERE wm.repository_id = r.id
                        AND wm.week_start <= ir.generated_at::date
                      ORDER BY wm.week_start DESC
                      LIMIT 1
                  ) m ON TRUE
                  WHERE ir.subject_id = r.id
                    AND ir.report_type = 'repository'
                    AND ir.generated_at > NOW() - (:max_age * INTERVAL '1 day')
                    AND ABS(r.momentum_score - m.momentum_score) < :delta
              )
            ORDER BY r.momentum_score DESC
            LIMIT :limit
            """),
            {
                "limit": settings.TOP_REPOS_FOR_INSIGHTS,
                "max_age": settings.INSIGHT_MAX_AGE_DAYS,
                "delta": settings.INSIGHT_REFRESH_DELTA,
            },
        )
        rows = result.fetchall()
        logger.info("Generating insights for %d repos", len(rows))

        for row in rows:
            repo_dict = dict(row._mapping)
            insight = await generate_repo_insight(repo_dict)
            # Space calls to respect the provider's requests-per-minute limit.
            await asyncio.sleep(settings.AI_INSIGHT_DELAY_SEC)
            if insight is None:
                continue

            report = InsightReport(
                report_type="repository",
                subject_id=row.id,
                period_start=date.today(),
                period_end=date.today(),
                title=f"Intelligence Report: {row.full_name}",
                summary=build_summary(insight),
                why_growing=insight.get("why_growing"),
                what_it_solves=insight.get("what_it_solves"),
                who_uses_it=insight.get("who_uses_it"),
                tech_stack=insight.get("tech_stack"),
                verdict=insight.get("verdict"),
                competitors=insight.get("competitors"),
                tags=insight.get("tags", []),
                model_used=insight.get("model_used"),
                tokens_used=insight.get("tokens_used"),
                generated_at=now,
                expires_at=datetime.fromisoformat(insight["expires_at"])
                if insight.get("expires_at") else None,
            )
            session.add(report)
            await session.flush()

        await session.commit()

    logger.info("Insight generation complete")
