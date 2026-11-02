"""
"Ask the data": turn a plain-English question into a structured repo filter.

The LLM only ever produces a filter (validated against known languages and
categories), never SQL. Questions are cached for a week and LLM parsing is
capped per day; past the cap, or with no key, a keyword parser takes over.
"""

import json
import logging
import re
from datetime import date

import httpx

from app.core.cache import cache_get, cache_incr, cache_set
from app.core.config import settings
from app.services.trend_service import LIFECYCLE_STAGES

logger = logging.getLogger(__name__)

SORTS = ("momentum", "week", "today", "stars", "newest")

_SYSTEM = """You convert questions about GitHub repositories into a JSON filter.
Keys (omit any that the question does not imply):
  "language": one of {languages}
  "category": one of {categories}
  "lifecycle": one of {stages}
  "min_stars", "max_stars": integers (total stars)
  "max_age_days": integer, only when the question asks for NEW/young repos
  "sort": one of {sorts} ("week" = most stars gained this week, "today" = today,
          "stars" = most stars overall, "newest" = most recently created,
          "momentum" = overall momentum score, the default)
  "text": 1-3 keywords for anything not covered above (e.g. "orm", "terminal")
  "limit": integer 1-20
Respond with the JSON object only."""

_STOP = set(
    "a an the of for in on with and or to me show list find which what whats what's are is "
    "best top most fastest growing hot trending popular new newest repos repositories "
    "projects libraries library tools tool github this that week month today stars star "
    "written built using please some any by over under than more less".split()
)


def _norm(q: str) -> str:
    return " ".join(q.lower().split())


def clean_filter(raw: dict, languages: list[str], categories: dict[str, str]) -> dict:
    """Keep only valid keys/values. categories maps slug -> display name."""
    out: dict = {}
    lang = raw.get("language")
    if isinstance(lang, str):
        match = next((l for l in languages if l.lower() == lang.lower()), None)
        if match:
            out["language"] = match
    cat = raw.get("category")
    if isinstance(cat, str):
        c = cat.lower()
        match = next((s for s, n in categories.items() if s == c or n.lower() == c), None)
        if match:
            out["category"] = match
    if raw.get("lifecycle") in LIFECYCLE_STAGES:
        out["lifecycle"] = raw["lifecycle"]
    for key in ("min_stars", "max_stars", "max_age_days"):
        try:
            v = int(raw[key])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0:
            out[key] = v
    out["sort"] = raw.get("sort") if raw.get("sort") in SORTS else "momentum"
    txt = raw.get("text")
    if isinstance(txt, str):
        words = [w for w in re.findall(r"[a-z0-9+#.\-]+", txt.lower()) if w not in _STOP][:3]
        if words:
            out["text"] = " ".join(words)
    try:
        out["limit"] = max(1, min(int(raw.get("limit") or 12), 20))
    except (TypeError, ValueError):
        out["limit"] = 12
    return out


def _stars(num: str, suffix: str) -> int:
    return int(float(num) * (1000 if suffix == "k" else 1))


def heuristic_filter(q: str, languages: list[str], categories: dict[str, str]) -> dict:
    s = f" {_norm(q)} "
    raw: dict = {}

    for lang in sorted(languages, key=len, reverse=True):
        l = lang.lower()
        pattern = r"(?<![a-z0-9])" + re.escape(l) + r"(?![a-z0-9+#])"
        if l == "go":
            pattern = r"\b(golang|go)\b(?! to)"
        if re.search(pattern, s):
            raw["language"] = lang
            break

    for slug, name in categories.items():
        words = {name.lower(), slug.replace("-", " "), name.lower().rstrip("s")}
        if any(f" {w}" in s for w in words):
            raw["category"] = slug
            break

    if re.search(r"breaking out|breakout", s):
        raw["lifecycle"] = "breakout"
    elif re.search(r"fading|dying|declining|cooling", s):
        raw["lifecycle"] = "fading"
    elif re.search(r"\bestablished\b|\bmature\b", s):
        raw["lifecycle"] = "established"

    if re.search(r"\b(brand new|new|young|recent|newly)\b", s):
        raw["max_age_days"] = 30 if "this month" in s else 90

    m = re.search(r"(?:under|below|less than|fewer than|<)\s*(\d+(?:\.\d+)?)\s*(k?)", s)
    if m:
        raw["max_stars"] = _stars(m.group(1), m.group(2))
    m = re.search(r"(?:over|above|more than|at least|>)\s*(\d+(?:\.\d+)?)\s*(k?)", s)
    if m:
        raw["min_stars"] = _stars(m.group(1), m.group(2))

    if "today" in s:
        raw["sort"] = "today"
    elif re.search(r"fastest|growing|hot|trending|rising|this week", s):
        raw["sort"] = "week"
    elif re.search(r"most starred|most popular|biggest|largest", s):
        raw["sort"] = "stars"
    elif re.search(r"newest|latest", s):
        raw["sort"] = "newest"

    if not any(k in raw for k in ("language", "category", "lifecycle")):
        lang_words = {l.lower() for l in languages}
        words = [w for w in re.findall(r"[a-z0-9+#.\-]+", s) if w not in _STOP and w not in lang_words]
        words = [w for w in words if not re.fullmatch(r"\d+k?", w)]
        if words:
            raw["text"] = " ".join(words[:3])
    return clean_filter(raw, languages, categories)


async def _llm_filter(q: str, languages: list[str], categories: dict[str, str]) -> dict | None:
    if not settings.LLM_API_KEY or (settings.AI_PROVIDER or "").lower() not in ("groq", "openai", "llm"):
        return None
    system = _SYSTEM.format(
        languages=", ".join(languages),
        categories=", ".join(categories),
        stages=", ".join(LIFECYCLE_STAGES),
        sorts=", ".join(SORTS),
    )
    payload = {
        "model": settings.ASK_MODEL,
        "temperature": 0,
        "max_tokens": 150,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": q}],
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                settings.LLM_BASE_URL.rstrip("/") + "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
            resp.raise_for_status()
            raw = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:  # noqa: BLE001
        logger.warning("Ask LLM parse failed, falling back to keywords: %s", e)
        return None
    return clean_filter(raw if isinstance(raw, dict) else {}, languages, categories)


async def parse_question(q: str, languages: list[str], categories: dict[str, str]) -> tuple[dict, str]:
    """(filter, how) where how is "ai" or "keywords"."""
    key = f"ask:v1:{_norm(q)}"
    cached = await cache_get(key)
    if cached:
        return cached["filter"], cached["how"]

    filt, how = None, "keywords"
    used = await cache_incr(f"ask:count:{date.today().isoformat()}", 86400)
    # cache_incr is None without Redis: no way to enforce the cap, so stay on keywords.
    if used is not None and used <= settings.ASK_DAILY_LIMIT:
        filt = await _llm_filter(q, languages, categories)
        if filt is not None:
            how = "ai"
    if filt is None:
        filt = heuristic_filter(q, languages, categories)
    await cache_set(key, {"filter": filt, "how": how}, 7 * 86400)
    return filt, how


def filter_sql(f: dict) -> tuple[str, dict]:
    """WHERE/ORDER clauses for a cleaned filter. Values are always bound."""
    where = ["r.is_archived = FALSE"]
    params: dict = {"limit": f.get("limit", 12)}
    join = ""
    if "language" in f:
        where.append("r.language = :language")
        params["language"] = f["language"]
    if "category" in f:
        join = (
            "JOIN repository_categories rc ON rc.repository_id = r.id "
            "JOIN technology_categories tc ON tc.id = rc.category_id AND tc.slug = :category"
        )
        params["category"] = f["category"]
    if "lifecycle" in f:
        where.append("r.lifecycle = :lifecycle")
        params["lifecycle"] = f["lifecycle"]
    if "min_stars" in f:
        where.append("r.latest_stars >= :min_stars")
        params["min_stars"] = f["min_stars"]
    if "max_stars" in f:
        where.append("r.latest_stars <= :max_stars")
        params["max_stars"] = f["max_stars"]
    if "max_age_days" in f:
        where.append("r.github_created_at >= NOW() - (:max_age * INTERVAL '1 day')")
        params["max_age"] = f["max_age_days"]
    if "text" in f:
        where.append(
            "(to_tsvector('english', coalesce(r.name,'') || ' ' || coalesce(r.owner,'') || ' ' || "
            "coalesce(r.description,'')) @@ plainto_tsquery('english', :text) "
            "OR :text_one = ANY(r.topics))"
        )
        params["text"] = f["text"]
        params["text_one"] = f["text"].replace(" ", "-")
    order = {
        "momentum": "r.momentum_score DESC",
        "week": "r.stars_gained_week DESC",
        "today": "r.stars_gained_today DESC",
        "stars": "r.latest_stars DESC",
        "newest": "r.github_created_at DESC",
    }[f.get("sort", "momentum")]
    return f"{join} WHERE {' AND '.join(where)} ORDER BY {order} NULLS LAST, r.id", params


def describe(f: dict, categories: dict[str, str]) -> str:
    """Human-readable read-back of what was understood."""
    bits = []
    if "lifecycle" in f:
        bits.append(f["lifecycle"])
    if "max_age_days" in f:
        bits.append(f"created in the last {f['max_age_days']} days")
    if "language" in f:
        bits.append(f["language"])
    if "category" in f:
        bits.append(categories.get(f["category"], f["category"]))
    if "text" in f:
        bits.append(f"matching “{f['text']}”")
    if "min_stars" in f:
        bits.append(f"≥ {f['min_stars']:,} stars")
    if "max_stars" in f:
        bits.append(f"≤ {f['max_stars']:,} stars")
    sort = {
        "momentum": "by momentum",
        "week": "by stars gained this week",
        "today": "by stars gained today",
        "stars": "by total stars",
        "newest": "newest first",
    }[f.get("sort", "momentum")]
    return f"Repos{' · ' + ' · '.join(bits) if bits else ''}, {sort}"
