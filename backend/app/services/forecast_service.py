"""
Pure functions behind the explained spikes, the odds on breakout calls, the
hype half-life and the GitHub-stars radar. No I/O here, so all of it is unit
tested; the workers in app/workers/explainers.py feed it rows.
"""

import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from statistics import median

import numpy as np

# ---------------------------------------------------------------- spikes

SPIKE_MIN_GAIN = 150      # stars in one day
SPIKE_RATIO = 3.0         # x the repo's typical day
SPIKE_LOOKBACK_DAYS = 14  # days searched for spikes (and baseline length)
SPIKE_MIN_HISTORY = 5     # earlier days needed before a day can count as a spike


def find_spikes(days: list[tuple[date, int]], today: date) -> list[dict]:
    """
    Days in the last SPIKE_LOOKBACK_DAYS whose star gain is both large and a
    multiple of the repo's typical day (median of up to 14 earlier days).
    Neighbouring spike days are one event: only the biggest within 2 days is kept.
    """
    days = sorted(days)
    found = []
    for i, (d, gain) in enumerate(days):
        if (today - d).days >= SPIKE_LOOKBACK_DAYS or i < SPIKE_MIN_HISTORY:
            continue
        before = [g for dd, g in days[max(0, i - SPIKE_LOOKBACK_DAYS):i] if (d - dd).days <= SPIKE_LOOKBACK_DAYS]
        if len(before) < SPIKE_MIN_HISTORY:
            continue
        baseline = max(median(before), 5)
        if gain >= SPIKE_MIN_GAIN and gain >= SPIKE_RATIO * baseline:
            found.append({"date": d, "gain": int(gain), "baseline": int(round(baseline))})
    kept: list[dict] = []
    for s in sorted(found, key=lambda s: -s["gain"]):
        if all(abs((s["date"] - k["date"]).days) > 2 for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s["date"])


HN_MIN_POINTS = 20  # a story with fewer points didn't cause a jump of 150+ stars
LOBSTERS_MIN_POINTS = 10  # Lobsters scores run far lower than Hacker News points
BLUESKY_MIN_LIKES = 50

# Sites where a bare domain says nothing about which project a link is for.
SHARED_HOSTS = {
    "arxiv.org", "youtube.com", "youtu.be", "medium.com", "x.com", "twitter.com", "huggingface.co",
    "discord.gg", "discord.com", "npmjs.com", "pypi.org", "crates.io", "reddit.com", "substack.com",
    "notion.so", "notion.site", "vercel.app", "netlify.app", "readthedocs.io", "gitbook.io",
    "linkedin.com", "producthunt.com", "google.com", "docs.google.com", "colab.research.google.com",
}


def _url_key(url: str) -> str:
    """host/path, lowercased, without scheme, www. or trailing slash."""
    u = re.sub(r"^[a-z]+://", "", (url or "").strip().lower())
    u = u.removeprefix("www.")
    return re.split(r"[?#]", u, maxsplit=1)[0].rstrip("/")


def homepage_key(url: str | None) -> str | None:
    """
    What a story's URL must start with to be about this repo's homepage, or None
    when the homepage can't identify the project (GitHub itself, or a bare shared
    site such as arxiv.org with no path).
    """
    key = _url_key(url or "")
    if not key or "." not in key.split("/")[0]:
        return None
    host, _, path = key.partition("/")
    if host == "github.com" or host.endswith(".github.com"):
        return None
    if not path and (host in SHARED_HOSTS or any(host.endswith("." + h) for h in SHARED_HOSTS)):
        return None
    return key


def matches_repo(hit: dict, owner: str, name: str, homepage: str | None) -> bool:
    """Whether a Hacker News story is about this repo: its GitHub URL, its title, or its homepage."""
    # owner/name as a whole token, so foo/bar doesn't match foo/barista
    full = re.compile(rf"(?<![\w.-]){re.escape(owner)}/{re.escape(name)}(?![\w.-])", re.IGNORECASE)
    url = hit.get("url") or ""
    if full.search(url) and "github.com/" in url.lower():
        return True
    if full.search(hit.get("title") or ""):
        return True
    if not homepage:
        return False
    key = _url_key(url)
    return key == homepage or key.startswith(homepage + "/")


# ---------------------------------------------------------------- star activity

# GitHub stopped publishing stargazer lists in June 2026, so bought stars are
# judged from what real interest brings along: forks. Fast-growing repos gain
# roughly one fork per 9 stars; stars arriving with far fewer forks than the
# week's typical ratio are flagged.
ACTIVITY_SUSPICIOUS = 0.3  # under 30% of the typical forks-per-star
ACTIVITY_MIXED = 0.5


def activity_verdict(stars_week: int, forks_week: int, typical_ratio: float) -> str:
    """organic / mixed / suspicious, from this week's forks per star against the typical repo's."""
    if stars_week <= 0 or typical_ratio <= 0:
        return "organic"
    rel = (forks_week / stars_week) / typical_ratio
    if rel < ACTIVITY_SUSPICIOUS:
        return "suspicious"
    if rel < ACTIVITY_MIXED:
        return "mixed"
    return "organic"


def post_matches_repo(post: dict, owner: str, name: str, homepage: str | None) -> bool:
    """A social post (with the links it carries) is about this repo."""
    if matches_repo({"url": "", "title": post.get("title") or ""}, owner, name, None):
        return True
    return any(matches_repo({"url": link, "title": ""}, owner, name, homepage) for link in post.get("links") or [])


def within(at: str | None, start: datetime, end: datetime) -> bool:
    """An ISO timestamp (any offset) falls in [start, end]."""
    if not at:
        return False
    try:
        t = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return start <= t <= end


def lifetime_points(weeks: list[dict], latest_stars: int) -> list[dict]:
    """
    GitHub's weekly star counts (newest first) to a cumulative series (oldest
    first), walking back from today's total. Unstars aren't in the weekly
    counts, so early weeks can read a little low; never below zero.
    """
    total, points = int(latest_stars or 0), []
    for w in weeks:
        points.append({"week": datetime.fromtimestamp(w["week"], tz=timezone.utc).date().isoformat(),
                       "stars": max(total, 0)})
        total -= w["total"]
    return points[::-1]


# ---------------------------------------------------------------- call odds

FEATURES = ("accel", "gain7", "stars", "age")


def call_features(accel: float, gain7: int, stars: int, age_days: int) -> list[float]:
    return [
        math.log(max(accel, 1.0)),
        math.log1p(max(gain7, 0)),
        math.log1p(max(stars, 0)),
        math.log1p(max(age_days, 0)),
    ]


def fit_logistic(x: list[list[float]], y: list[int], l2: float = 10.0, steps: int = 800) -> dict:
    """
    L2-regularised logistic regression by gradient descent on standardised
    features. Small and dependency-light: a few hundred samples at most.
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    mean = xa.mean(axis=0)
    std = xa.std(axis=0)
    std[std == 0] = 1.0
    z = (xa - mean) / std
    n, k = z.shape
    w = np.zeros(k)
    b = math.log((ya.mean() + 1e-3) / (1 - ya.mean() + 1e-3))
    lr = 0.5
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(z @ w + b)))
        err = p - ya
        w -= lr * (z.T @ err / n + l2 * w / n)
        b -= lr * err.mean()
    return {"w": w.round(5).tolist(), "b": round(float(b), 5),
            "mean": mean.round(5).tolist(), "std": std.round(5).tolist()}


def predict(model: dict, feats: list[float]) -> float:
    z = [(f - m) / s for f, m, s in zip(feats, model["mean"], model["std"])]
    logit = model["b"] + sum(wi * zi for wi, zi in zip(model["w"], z))
    return 1 / (1 + math.exp(-max(min(logit, 30), -30)))


def brier(probs: list[float], labels: list[int]) -> float | None:
    if not probs:
        return None
    return round(sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs), 4)


CAL_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0001)


def calibration_bins(probs: list[float], labels: list[int]) -> list[dict]:
    """Predicted vs. actual hit rate in five probability bands (empty bands dropped)."""
    out = []
    for lo, hi in zip(CAL_EDGES, CAL_EDGES[1:]):
        pairs = [(p, y) for p, y in zip(probs, labels) if lo <= p < hi]
        if pairs:
            out.append({
                "lo": round(lo, 1),
                "hi": round(min(hi, 1.0), 1),
                "n": len(pairs),
                "predicted": round(100 * sum(p for p, _ in pairs) / len(pairs)),
                "actual": round(100 * sum(y for _, y in pairs) / len(pairs)),
            })
    return out


MIN_SKILL = 0.05  # the model must be at least 5% better than guessing the average
MIN_TEST_HITS = 8  # ...on a held-out set with enough hits that the margin isn't luck


def train_and_backtest(samples: list[dict], min_samples: int = 40, min_pos: int = 5) -> dict | None:
    """
    samples: {"date", "accel", "gain7", "stars", "age", "hit"}, oldest first.
    Fits on the earliest 70% and scores the rest (the backtest), then refits on
    everything for live use. None when history is too thin to say anything.
    """
    samples = sorted(samples, key=lambda s: s["date"])
    pos = sum(s["hit"] for s in samples)
    if len(samples) < min_samples or pos < min_pos or pos == len(samples):
        return None

    def xy(rows):
        return ([call_features(r["accel"], r["gain7"], r["stars"], r["age"]) for r in rows],
                [int(r["hit"]) for r in rows])

    cut = int(len(samples) * 0.7)
    train, test = samples[:cut], samples[cut:]
    backtest = None
    if sum(r["hit"] for r in train) >= 3 and test:
        m = fit_logistic(*xy(train))
        xt, yt = xy(test)
        pt = [predict(m, f) for f in xt]
        base = sum(r["hit"] for r in train) / len(train)
        ranked = sorted(zip(pt, yt), key=lambda t: -t[0])
        top = ranked[: max(1, len(ranked) // 3)]
        b_model, b_base = brier(pt, yt), brier([base] * len(yt), yt)
        backtest = {
            "test_n": len(yt),
            "test_hits": sum(yt),
            "test_from": str(test[0]["date"]),
            "test_to": str(test[-1]["date"]),
            "bins": calibration_bins(pt, yt),
            "brier": b_model,
            "brier_base": b_base,
            "skill": round(1 - b_model / b_base, 3) if b_base else None,
            "base_rate": round(100 * sum(yt) / len(yt)),
            "top_third_rate": round(100 * sum(y for _, y in top) / len(top)),
        }
    final = fit_logistic(*xy(samples))
    # A forecaster that can't clearly beat the plain average on held-out history
    # shouldn't rank anything: until it does, every call gets the average odds.
    final["usable"] = bool(
        backtest
        and backtest["skill"] is not None
        and backtest["skill"] >= MIN_SKILL
        and backtest["top_third_rate"] > backtest["base_rate"]
        and backtest["test_hits"] >= MIN_TEST_HITS
    )
    final["base_rate"] = round(pos / len(samples), 4)
    return {
        "model": final,
        "samples": len(samples),
        "positives": pos,
        "base_rate": round(100 * pos / len(samples)),
        "backtest": backtest,
    }


def call_odds(model: dict, feats: list[float]) -> float:
    """The model's odds when it has earned them, otherwise the historical average."""
    if model.get("usable", False):  # a model saved before the trust check isn't trusted
        return predict(model, feats)
    return float(model.get("base_rate", 0.0))


# ---------------------------------------------------------------- hype half-life

HYPE_MIN_PEAK = 700  # weekly stars a repo must reach to count as having had hype


def hype_curve(points: list[tuple[date, int, int]]) -> dict | None:
    """
    points: (date, rolling 7-day star gain, commits in trailing week), oldest first.
    Returns the peak, where momentum is now, and when it first fell below half.
    """
    if not points:
        return None
    peak_i = max(range(len(points)), key=lambda i: points[i][1])
    peak_on, peak, commits_peak = points[peak_i]
    if peak < HYPE_MIN_PEAK:
        return None
    half_on = next((d for d, g, _ in points[peak_i + 1:] if g < peak / 2), None)
    last_on, now, commits_now = points[-1]
    return {
        "peak_on": peak_on,
        "peak_gain7": int(peak),
        "now_gain7": int(now),
        "half_on": half_on,
        "commits_peak": int(commits_peak or 0),
        "commits_now": int(commits_now or 0),
        "as_of": last_on,
    }


def hype_summary(curves: list[dict], today: date, min_age_days: int = 14) -> dict | None:
    """
    Across repos whose peak is at least min_age_days old: median days for weekly
    stars to halve, share still at half their peak or better, and share whose
    commit activity held up (among repos with commit data).
    """
    old = [c for c in curves if (today - c["peak_on"]).days >= min_age_days]
    if not old:
        return None
    halved = [(c["half_on"] - c["peak_on"]).days for c in old if c["half_on"]]
    holding = [c for c in old if c["now_gain7"] >= c["peak_gain7"] / 2]
    with_commits = [c for c in old if c["commits_peak"] > 0]
    building = [c for c in with_commits if c["commits_now"] >= max(1, c["commits_peak"] / 2)]
    return {
        "n": len(old),
        "fade_days": int(median(halved)) if halved else None,
        "holding_pct": round(100 * len(holding) / len(old)),
        "building_pct": round(100 * len(building) / len(with_commits)) if with_commits else None,
    }


# ---------------------------------------------------------------- stars radar

def star_profile(starred: list[dict]) -> dict:
    """Topic and language weights from a user's starred repos."""
    topics = Counter(t for r in starred for t in (r.get("topics") or []))
    langs = Counter(r["language"] for r in starred if r.get("language"))
    return {"topics": topics, "languages": langs, "n": max(len(starred), 1)}


def radar_score(repo: dict, profile: dict) -> tuple[float, list[str]]:
    """How well a tracked repo matches the profile, and the shared topics behind it."""
    shared = [t for t in (repo.get("topics") or []) if t in profile["topics"]]
    topic_fit = sum(math.log1p(profile["topics"][t]) for t in shared)
    lang = repo.get("language")
    lang_fit = math.log1p(profile["languages"].get(lang, 0)) * 0.6 if lang else 0.0
    fit = topic_fit + lang_fit
    if fit <= 0:
        return 0.0, []
    momentum = float(repo.get("momentum_score") or 0)
    shared.sort(key=lambda t: -profile["topics"][t])
    return fit * (10 + momentum), shared[:3]


def closest_starred(repo: dict, starred: list[dict]) -> str | None:
    """The starred repo sharing the most topics (at least two) with this one, to explain a pick."""
    mine = set(repo.get("topics") or [])
    best, best_n = None, 1
    for s in starred:
        n = len(mine & set(s.get("topics") or []))
        if n > best_n:
            best, best_n = s["full_name"], n
    return best
