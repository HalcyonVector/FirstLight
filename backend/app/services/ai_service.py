"""
AI insight generation — pluggable provider.

Default: Ollama (local, free, no API key). Optional: Anthropic Claude (paid).
Select via AI_PROVIDER in the environment ("ollama" | "anthropic" | "off").
Ollama is called over plain HTTP (httpx), so no extra dependency is needed.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

def reasoning_opts(model: str) -> dict:
    """Extra payload fields for reasoning models (Groq's gpt-oss accepts reasoning_effort)."""
    if settings.LLM_REASONING_EFFORT and "gpt-oss" in model:
        return {"reasoning_effort": settings.LLM_REASONING_EFFORT}
    return {}


INSIGHT_PROMPT_SYSTEM = """You are a developer intelligence analyst.
Analyze GitHub repositories and produce structured, factual insights for software engineers.
Be specific. Cite numbers where available. Max 3 sentences per field. Never be vague."""

INSIGHT_PROMPT_TEMPLATE = """
Repository: {full_name}
Description: {description}
Language: {language}
Topics: {topics}
Stars total: {stars_total:,}
Stars this week: {stars_week:,}
Forks: {forks:,}
Contributors: ~{contributors:,}
Created: {created_at}
Category: {category}

Produce a JSON response with exactly these keys:
{{
  "why_growing": "...",
  "what_it_solves": "...",
  "who_uses_it": "...",
  "tech_stack": "...",
  "verdict": "...",
  "competitors": ["repo/name1", "repo/name2"],
  "tags": ["tag1", "tag2", "tag3"]
}}
Respond with JSON only. No markdown. No explanation.
"""


def _build_prompt(repo: dict) -> str:
    created = repo.get("github_created_at")
    created_str = str(created)[:10] if created else "Unknown"
    return INSIGHT_PROMPT_TEMPLATE.format(
        full_name=repo.get("full_name", "unknown"),
        description=repo.get("description") or "No description provided.",
        language=repo.get("language") or "Unknown",
        topics=", ".join(repo.get("topics", [])[:8]) or "none",
        stars_total=repo.get("latest_stars", 0),
        stars_week=repo.get("stars_gained_week", 0),
        forks=repo.get("latest_forks", 0),
        contributors=repo.get("contributors_count", 0),
        created_at=created_str,
        category=repo.get("category_name") or "General",
    )


async def generate_repo_insight(repo: dict) -> dict | None:
    """
    Generate an AI insight for a repository via the configured provider.
    Returns None on any failure (never raises into the worker loop).
    """
    provider = (settings.AI_PROVIDER or "ollama").lower()
    if provider == "off":
        return None

    prompt = _build_prompt(repo)
    try:
        if provider == "anthropic":
            raw, model, tokens = await _via_anthropic(prompt)
        elif provider in ("groq", "openai", "llm"):
            raw, model, tokens = await _via_openai_compatible(prompt)
        else:
            raw, model, tokens = await _via_ollama(prompt)
    except Exception as e:
        logger.error(
            "AI insight failed (provider=%s) for %s: %s",
            provider,
            repo.get("full_name"),
            e,
        )
        return None

    return _parse_insight(raw, model, tokens)


async def _via_ollama(prompt: str) -> tuple[str, str, int]:
    """Call a local/self-hosted Ollama server. Free, no API key."""
    url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "stream": False,
        "format": "json",  # ask Ollama to constrain output to valid JSON
        "messages": [
            {"role": "system", "content": INSIGHT_PROMPT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.4, "num_predict": settings.AI_MAX_TOKENS},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = data.get("message", {}).get("content", "")
    tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
    return content, settings.OLLAMA_MODEL, tokens


async def _via_openai_compatible(prompt: str) -> tuple[str, str, int]:
    """
    Call any OpenAI-compatible chat API (Groq, Gemini's OpenAI endpoint, OpenAI…).
    Groq's free tier is fast and needs no credit card. Configured via LLM_* settings.
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set (AI_PROVIDER=groq/openai)")
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "temperature": 0.4,
        "max_tokens": settings.AI_MAX_TOKENS,
        "response_format": {"type": "json_object"},  # ask for strict JSON
        "messages": [
            {"role": "system", "content": INSIGHT_PROMPT_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        **reasoning_opts(settings.LLM_MODEL),
    }
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        # Some models reject response_format=json_object; retry once without it.
        if resp.status_code == 400 and "response_format" in resp.text:
            payload.pop("response_format", None)
            resp = await client.post(url, json=payload, headers=headers)
        # Respect free-tier rate limits: wait the server-suggested time and retry once.
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after") or 5)
            await asyncio.sleep(min(retry_after, 30))
            resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    tokens = int(usage.get("total_tokens") or 0)
    return content, settings.LLM_MODEL, tokens


async def _via_anthropic(prompt: str) -> tuple[str, str, int]:
    """Call Anthropic Claude (paid). Imported lazily so it's optional."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await asyncio.to_thread(
        client.messages.create,
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.AI_MAX_TOKENS,
        system=INSIGHT_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    tokens = message.usage.input_tokens + message.usage.output_tokens
    return raw, settings.ANTHROPIC_MODEL, tokens


def _as_text(value) -> str | None:
    """Coerce any LLM output into a string (models often return lists/dicts)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def _as_list(value) -> list[str]:
    """Coerce any LLM output into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return [str(value)]


def _parse_insight(raw: str, model: str, tokens: int) -> dict | None:
    raw = (raw or "").strip()
    # Strip markdown fences if a model added them despite instructions
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI response (%s): %s", model, e)
        return None
    if not isinstance(parsed, dict):
        logger.error("AI response was not a JSON object (%s)", model)
        return None

    return {
        "why_growing": _as_text(parsed.get("why_growing")),
        "what_it_solves": _as_text(parsed.get("what_it_solves")),
        "who_uses_it": _as_text(parsed.get("who_uses_it")),
        "tech_stack": _as_text(parsed.get("tech_stack")),
        "verdict": _as_text(parsed.get("verdict")),
        "competitors": json.dumps(_as_list(parsed.get("competitors"))),
        "tags": _as_list(parsed.get("tags")),
        "model_used": model,
        "tokens_used": tokens,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }


def build_summary(insight: dict) -> str | None:
    """Build a 2-sentence summary from insight fields."""
    verdict = insight.get("verdict")
    why = insight.get("why_growing")
    if verdict and why:
        return f"{why} {verdict}"
    return verdict or why
