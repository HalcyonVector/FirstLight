"""Spike detection, call odds, hype half-life and the stars radar (pure functions)."""

import math
import random
from datetime import date, timedelta

from app.services.forecast_service import (
    brier,
    calibration_bins,
    closest_starred,
    find_spikes,
    homepage_key,
    hype_curve,
    hype_summary,
    matches_repo,
    predict,
    radar_score,
    star_profile,
    train_and_backtest,
)

TODAY = date(2026, 11, 5)


def _days(gains: list[int]) -> list[tuple[date, int]]:
    start = TODAY - timedelta(days=len(gains) - 1)
    return [(start + timedelta(days=i), g) for i, g in enumerate(gains)]


def test_find_spikes_flags_a_jump_against_the_repos_own_baseline():
    gains = [40] * 20 + [600, 300, 50, 45]
    spikes = find_spikes(_days(gains), TODAY)
    assert [s["gain"] for s in spikes] == [600]  # the 300 next day is the same event
    assert spikes[0]["baseline"] == 40


def test_find_spikes_ignores_steady_big_repos_and_small_blips():
    assert find_spikes(_days([900] * 24), TODAY) == []
    assert find_spikes(_days([5] * 20 + [120, 5, 5, 5]), TODAY) == []  # under the 150 floor


def test_find_spikes_needs_history_and_recency():
    assert find_spikes(_days([10, 10, 900]), TODAY) == []  # too little history
    old = _days([20] * 10 + [800] + [20] * 20)  # spike 20 days ago
    assert find_spikes(old, TODAY) == []


def test_matches_repo_by_url_title_or_homepage():
    assert matches_repo({"url": "https://github.com/Foo/Bar", "title": "x"}, "foo", "bar", None)
    assert matches_repo({"url": "", "title": "Show HN: foo/bar, a thing"}, "foo", "bar", None)
    assert matches_repo({"url": "https://www.bar.dev/blog", "title": "Bar"}, "foo", "bar", "bar.dev")
    assert not matches_repo({"url": "https://bar.dev.evil.com", "title": "x"}, "foo", "bar", "bar.dev")


def test_homepage_on_a_shared_site_only_matches_its_own_page():
    paper = homepage_key("http://arxiv.org/abs/2604.26962")
    assert paper == "arxiv.org/abs/2604.26962"
    other = {"url": "https://arxiv.org/abs/2501.00001", "title": "Attention Is Not What You Need"}
    assert not matches_repo(other, "HKUDS", "DeepTutor", paper)
    assert matches_repo({"url": "https://arxiv.org/abs/2604.26962v2", "title": "x"}, "a", "b", paper) is False
    assert matches_repo({"url": "https://arxiv.org/abs/2604.26962", "title": "x"}, "a", "b", paper)
    assert homepage_key("https://huggingface.co") is None  # bare shared site
    assert homepage_key("https://github.com/foo/bar") is None
    assert homepage_key("https://www.claude-mem.ai/") == "claude-mem.ai"
    assert homepage_key("") is None and homepage_key(None) is None
    assert matches_repo({"url": "https://github.com/foo/bar/tree/main", "title": "x"}, "foo", "bar", None)
    assert not matches_repo({"url": "https://github.com/foo/barista", "title": "foo/barista"}, "foo", "bar", None)
    assert not matches_repo({"url": "https://example.com", "title": "unrelated"}, "foo", "bar", None)


def _samples(n: int, seed: int = 7) -> list[dict]:
    """Synthetic calls where sharper acceleration really does hit more often."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        accel = rng.uniform(2.5, 30)
        p = 1 / (1 + math.exp(-(-3 + 1.5 * math.log(accel))))
        out.append({
            "date": date(2026, 8, 1) + timedelta(days=i % 60),
            "accel": accel, "gain7": rng.randint(150, 3000), "stars": rng.randint(200, 4900),
            "age": rng.randint(5, 360), "hit": rng.random() < p,
        })
    return out


def test_train_and_backtest_learns_the_signal_and_scores_it():
    result = train_and_backtest(_samples(600))
    assert result is not None
    bt = result["backtest"]
    assert bt["test_n"] == 180
    assert bt["brier"] <= bt["brier_base"]  # beats always predicting the base rate
    assert bt["top_third_rate"] >= bt["base_rate"]
    low = predict(result["model"], [0.92, 6.0, 7.0, 4.0])   # accel ~2.5
    high = predict(result["model"], [3.3, 6.0, 7.0, 4.0])   # accel ~27
    assert high > low


def test_train_and_backtest_refuses_thin_history():
    assert train_and_backtest(_samples(20)) is None
    no_hits = [dict(s, hit=False) for s in _samples(100)]
    assert train_and_backtest(no_hits) is None


def test_calibration_bins_and_brier():
    bins = calibration_bins([0.1, 0.15, 0.7, 0.9], [0, 1, 1, 1])
    assert [(b["lo"], b["n"], b["actual"]) for b in bins] == [(0.0, 2, 50), (0.6, 1, 100), (0.8, 1, 100)]
    assert brier([1.0, 0.0], [1, 0]) == 0
    assert brier([], []) is None


def test_hype_curve_finds_peak_and_halving():
    d0 = date(2026, 9, 1)
    pts = [(d0 + timedelta(days=i), g, c) for i, (g, c) in enumerate(
        [(100, 5), (900, 8), (2000, 12), (1500, 10), (900, 9), (700, 9)])]
    c = hype_curve(pts)
    assert c["peak_on"] == d0 + timedelta(days=2)
    assert c["peak_gain7"] == 2000 and c["now_gain7"] == 700
    assert c["half_on"] == d0 + timedelta(days=4)
    assert c["commits_peak"] == 12 and c["commits_now"] == 9
    assert hype_curve([(d0, 300, 0)]) is None  # never really hyped


def test_hype_summary_uses_only_settled_peaks():
    d = TODAY - timedelta(days=40)
    curves = [
        {"peak_on": d, "peak_gain7": 2000, "now_gain7": 200, "half_on": d + timedelta(days=6),
         "commits_peak": 10, "commits_now": 8},
        {"peak_on": d, "peak_gain7": 1000, "now_gain7": 700, "half_on": None,
         "commits_peak": 0, "commits_now": 0},
        {"peak_on": TODAY - timedelta(days=2), "peak_gain7": 5000, "now_gain7": 5000, "half_on": None,
         "commits_peak": 3, "commits_now": 3},
    ]
    s = hype_summary(curves, TODAY)
    assert s == {"n": 2, "fade_days": 6, "holding_pct": 50, "building_pct": 100}


def test_radar_prefers_shared_topics_and_explains_the_pick():
    starred = [
        {"full_name": "a/vec", "language": "Rust", "topics": ["database", "vector-search", "rust"]},
        {"full_name": "b/db", "language": "Rust", "topics": ["database", "sql"]},
        {"full_name": "c/ui", "language": "TypeScript", "topics": ["react"]},
    ]
    profile = star_profile(starred)
    dbish = {"full_name": "x/newdb", "language": "Rust", "topics": ["database", "vector-search"], "momentum_score": 40}
    ui = {"full_name": "y/btn", "language": "TypeScript", "topics": ["react"], "momentum_score": 40}
    other = {"full_name": "z/game", "language": "C", "topics": ["game"], "momentum_score": 90}
    s_db, shared = radar_score(dbish, profile)
    s_ui, _ = radar_score(ui, profile)
    assert s_db > s_ui > 0
    assert shared[0] == "database"
    assert radar_score(other, profile) == (0.0, [])
    assert closest_starred(dbish, starred) == "a/vec"
    assert closest_starred(ui, starred) is None  # one shared topic isn't enough to name a repo
