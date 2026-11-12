"""Refresh health check, social cause matching, digest wording and the lifetime star series."""

import logging
from collections import Counter
from datetime import datetime, timezone

from app.services.digest_service import cause_text
from app.services.forecast_service import lifetime_points, post_matches_repo, within
from app.services.health_service import AI_LOGGER, WarningCounter, health_issues

MB = 1024 * 1024


def test_healthy_run_has_no_issues():
    assert health_issues([], Counter(), {}, insights_attempted=20, db_bytes=200 * MB, db_limit=500 * MB) == []


def test_failed_step_ai_outage_and_full_database_are_reported():
    warnings = Counter({AI_LOGGER: 20})
    issues = health_issues(
        [("star spikes", "relation does not exist")], warnings,
        {AI_LOGGER: "AI insight failed: 404 Not Found"}, insights_attempted=20,
        db_bytes=420 * MB, db_limit=500 * MB,
    )
    assert len(issues) == 3
    assert issues[0].startswith("Step failed: star spikes")
    assert "20 of 20 failed" in issues[1] and "404" in issues[1]
    assert "84%" in issues[2]


def test_a_couple_of_ai_failures_are_not_an_outage():
    assert health_issues([], Counter({AI_LOGGER: 2}), {}, 20, 0, 500 * MB) == []


def test_warning_counter_counts_by_logger():
    counter = WarningCounter()
    log = logging.getLogger("app.test_health")
    log.addHandler(counter)
    log.warning("first")
    log.warning("second")
    log.info("not counted")
    log.removeHandler(counter)
    assert counter.counts["app.test_health"] == 2
    assert counter.samples["app.test_health"] == "first"


def test_bluesky_post_matches_by_link_or_text():
    linked = {"title": "this is wild", "links": ["https://github.com/foo/bar"]}
    named = {"title": "just tried foo/bar and wow", "links": []}
    other = {"title": "bar is great", "links": ["https://github.com/foo/barista"]}
    assert post_matches_repo(linked, "foo", "bar", None)
    assert post_matches_repo(named, "foo", "bar", None)
    assert not post_matches_repo(other, "foo", "bar", None)
    assert post_matches_repo({"title": "", "links": ["https://bar.dev/launch"]}, "foo", "bar", "bar.dev")


def test_within_handles_offsets():
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = datetime(2026, 11, 4, 23, 59, tzinfo=timezone.utc)
    assert within("2026-11-02T04:52:32.741-05:00", start, end)  # Lobsters style
    assert within("2026-11-03T10:00:00Z", start, end)  # Bluesky style
    assert not within("2026-10-20T10:00:00Z", start, end)
    assert not within(None, start, end) and not within("garbage", start, end)


def test_cause_text_reads_naturally():
    assert cause_text({"kind": "hn", "title": "Show HN: X", "points": 412}) == 'Hacker News: "Show HN: X" (412 points)'
    assert cause_text({"kind": "bluesky", "title": "look", "points": 90}) == 'Bluesky: "look" (90 likes)'
    assert cause_text({"kind": "release", "title": "v2.0"}) == "a release: v2.0"


def test_lifetime_points_walk_back_from_todays_total():
    week = lambda d: int(datetime(2026, 11, d, tzinfo=timezone.utc).timestamp())  # noqa: E731
    weeks = [{"week": week(8), "total": 30}, {"week": week(1), "total": 50}]  # newest first
    assert lifetime_points(weeks, 1000) == [
        {"week": "2026-11-01", "stars": 970},
        {"week": "2026-11-08", "stars": 1000},
    ]
    assert lifetime_points([{"week": week(1), "total": 500}, {"week": week(8), "total": 900}], 100)[0]["stars"] == 0
