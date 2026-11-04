"""Unit tests for lifecycle, breakout-call and stargazer heuristics (pure functions)."""

from app.services.trend_service import (
    acceleration,
    classify_lifecycle,
    is_breakout_candidate,
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


def test_star_activity_flags_stars_that_arrive_without_forks():
    from app.services.forecast_service import activity_verdict

    typical = 0.11  # median forks per star among fast growers
    assert activity_verdict(6000, 700, typical) == "organic"
    assert activity_verdict(5800, 268, typical) == "mixed"       # 0.046, under half the norm
    assert activity_verdict(11813, 298, typical) == "suspicious"  # 0.025, a quarter of the norm
    assert activity_verdict(0, 0, typical) == "organic"


def test_frontend_urls_accepts_a_comma_separated_list():
    from app.core.config import Settings

    s = Settings(FRONTEND_URL=" https://new.vercel.app/ , https://old.vercel.app,")
    assert s.frontend_urls == ["https://new.vercel.app", "https://old.vercel.app"]
    assert Settings(FRONTEND_URL="").frontend_urls == []
