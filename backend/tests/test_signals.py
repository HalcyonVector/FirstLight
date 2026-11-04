"""Unit tests for lifecycle, breakout-call and stargazer heuristics (pure functions)."""

from app.services.trend_service import (
    acceleration,
    classify_lifecycle,
    is_breakout_candidate,
    summarize_stargazers,
)


def test_lifecycle_breakout_when_week_jumps_over_baseline():
    assert classify_lifecycle(900, 200, age_days=400, total_stars=20_000) == "breakout"


def test_lifecycle_breakout_needs_a_real_absolute_gain():
    # 3x the baseline, but only 60 stars: not a breakout
    assert classify_lifecycle(60, 20, age_days=400, total_stars=20_000) == "established"


def test_lifecycle_fading_when_week_halves():
    assert classify_lifecycle(40, 300, age_days=400, total_stars=20_000) == "fading"


def test_lifecycle_without_history_uses_age_and_size():
    assert classify_lifecycle(10, None, age_days=30, total_stars=50_000) == "emerging"
    assert classify_lifecycle(10, None, age_days=900, total_stars=50_000) == "established"
    assert classify_lifecycle(10, None, age_days=900, total_stars=500) == "emerging"


def test_acceleration_floors_tiny_baselines():
    assert acceleration(200, 0) == 20.0
    assert acceleration(200, 100) == 2.0


def test_breakout_candidate_rules():
    assert is_breakout_candidate(400, 50, age_days=60, total_stars=1500)
    assert not is_breakout_candidate(400, 50, age_days=60, total_stars=50_000)  # already big
    assert not is_breakout_candidate(400, 300, age_days=60, total_stars=1500)  # not accelerating
    assert not is_breakout_candidate(100, 5, age_days=60, total_stars=500)  # too few stars
    assert not is_breakout_candidate(400, None, age_days=60, total_stars=1500)  # no history


def test_stargazers_organic_and_suspicious():
    organic = [{"account_age_days": 900, "followers": 5, "repos": 10}] * 95 + [
        {"account_age_days": 3, "followers": 0, "repos": 0}
    ] * 5
    assert summarize_stargazers(organic)["verdict"] == "organic"

    farmed = [{"account_age_days": 2, "followers": 0, "repos": 0}] * 60 + [
        {"account_age_days": 900, "followers": 5, "repos": 10}
    ] * 40
    s = summarize_stargazers(farmed)
    assert s["verdict"] == "suspicious"
    assert s["pct_new"] == 60 and s["sample_size"] == 100


def test_stargazers_empty_sample():
    assert summarize_stargazers([]) is None


def test_frontend_urls_accepts_a_comma_separated_list():
    from app.core.config import Settings

    s = Settings(FRONTEND_URL=" https://new.vercel.app/ , https://old.vercel.app,")
    assert s.frontend_urls == ["https://new.vercel.app", "https://old.vercel.app"]
    assert Settings(FRONTEND_URL="").frontend_urls == []
