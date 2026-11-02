"""Unit tests for the momentum scoring algorithm (pure functions, no DB)."""

import random

from app.services.trend_service import compute_momentum_score, normalize_log


def test_normalize_log_zero_and_negative():
    assert normalize_log(0, 3000) == 0.0
    assert normalize_log(-10, 3000) == 0.0


def test_normalize_log_monotonic_and_capped():
    assert normalize_log(100, 3000) < normalize_log(1000, 3000)
    # at p95 it should be near (but not over) 1.0
    assert 0.9 <= normalize_log(3000, 3000) <= 1.0
    # far above p95 is clamped to exactly 1.0
    assert normalize_log(10_000_000, 3000) == 1.0


def test_momentum_zero_inputs_is_zero():
    assert compute_momentum_score(0, 0, 0, 0, 0, age_days=365) == 0.0


def test_momentum_capped_at_100():
    score = compute_momentum_score(10_000_000, 10_000_000, 10_000, 10_000, 10_000, age_days=5)
    assert score == 100.0


def test_recency_bonus_lifts_new_repos():
    old = compute_momentum_score(1000, 100, 10, 20, 10, age_days=365)
    fresh = compute_momentum_score(1000, 100, 10, 20, 10, age_days=10)
    assert fresh > old


def test_star_velocity_dominates():
    stars_only = compute_momentum_score(2000, 0, 0, 0, 0, age_days=365)
    forks_only = compute_momentum_score(0, 2000, 0, 0, 0, age_days=365)
    # star weight 0.45 > fork weight 0.20
    assert stars_only > forks_only


def test_score_always_in_range():
    for _ in range(200):
        score = compute_momentum_score(
            random.randint(0, 6000),
            random.randint(0, 1500),
            random.randint(0, 120),
            random.randint(0, 300),
            random.randint(0, 300),
            age_days=random.randint(0, 800),
        )
        assert 0.0 <= score <= 100.0


def test_breakdown_parts_sum_to_score():
    from app.services.trend_service import momentum_breakdown

    args = (1200, 80, 6, 40, 10)
    b = momentum_breakdown(*args, age_days=200)
    assert b["recency_multiplier"] == 1.0
    assert round(sum(b["parts"].values()), 2) == compute_momentum_score(*args, age_days=200)


def test_star_anomaly_flags_stars_without_activity():
    from app.services.trend_service import momentum_breakdown

    assert momentum_breakdown(5000, 0, 0, 0, 0, age_days=400)["star_anomaly"] is True
    assert momentum_breakdown(5000, 300, 20, 80, 0, age_days=400)["star_anomaly"] is False
    # small repos never trip it
    assert momentum_breakdown(100, 0, 0, 0, 0, age_days=400)["star_anomaly"] is False
