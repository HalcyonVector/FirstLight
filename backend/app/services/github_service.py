"""
GitHub API service.
Handles all communication with GitHub REST API with rate limiting and retry.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


def _parse_dt(value: str | None) -> datetime | None:
    """Convert a GitHub ISO-8601 timestamp (e.g. '2025-07-22T22:22:28Z') to datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# Categories / topics to actively monitor
MONITORED_TOPICS = [
    "ai-agent", "agents", "mcp", "model-context-protocol",
    "llm", "large-language-models", "langchain", "llamaindex",
    "vector-database", "embeddings", "rag", "fine-tuning",
    "code-generation", "code-completion", "ai-coding", "copilot",
    "mlops", "inference", "model-serving", "llm-inference",
    "developer-tools", "cli", "devtools", "productivity",
    "opentelemetry", "observability", "monitoring",
    "kubernetes", "terraform", "docker", "infrastructure",
    "database", "sql", "vector-search",
    "security", "cybersecurity", "authentication",
    "react", "nextjs", "svelte", "frontend",
    "fastapi", "backend", "api",
    "data-engineering", "etl", "data-pipeline",
    "fintech", "payments",
]

# Languages to track for trending
MONITORED_LANGUAGES = [
    "Python", "TypeScript", "JavaScript", "Rust", "Go",
    "Java", "C++", "C#", "Ruby", "Swift", "Kotlin", "Zig",
]


class GitHubRateLimitError(Exception):
    pass


class GitHubService:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.GITHUB_API_BASE,
                headers={
                    "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _check_rate_limit(self, response: httpx.Response) -> None:
        remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
        if remaining < 10:
            logger.warning("GitHub rate limit low: %d remaining", remaining)
        if response.status_code == 429 or (
            response.status_code == 403 and "rate limit" in response.text.lower()
        ):
            raise GitHubRateLimitError("GitHub rate limit exceeded")

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def _get(self, path: str, params: dict | None = None) -> Any:
        response = await self.client.get(path, params=params)
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    async def search_repositories(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 100,
        page: int = 1,
    ) -> dict:
        """Search GitHub repositories."""
        return await self._get(
            "/search/repositories",
            params={
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
                "page": page,
            },
        )

    async def get_repository(self, owner: str, repo: str) -> dict:
        """Get full repository metadata."""
        return await self._get(f"/repos/{owner}/{repo}")

    async def get_contributors_count(self, owner: str, repo: str) -> int:
        """Approximate contributor count via HEAD request + Link header."""
        try:
            response = await self.client.get(
                f"/repos/{owner}/{repo}/contributors",
                params={"per_page": 1, "anon": "true"},
            )
            self._check_rate_limit(response)
            link = response.headers.get("Link", "")
            if 'rel="last"' in link:
                # Extract page number from last link
                import re
                match = re.search(r'page=(\d+)>; rel="last"', link)
                if match:
                    return int(match.group(1))
            items = response.json()
            return len(items) if isinstance(items, list) else 0
        except Exception as e:
            logger.warning("Failed to get contributors for %s/%s: %s", owner, repo, e)
            return 0

    async def get_weekly_commit_activity(self, owner: str, repo: str) -> int:
        """Get number of commits in the last week."""
        try:
            data = await self._get(f"/repos/{owner}/{repo}/stats/commit_activity")
            if isinstance(data, list) and data:
                # Last element is most recent week
                return data[-1].get("total", 0)
            return 0
        except Exception as e:
            logger.warning("Failed to get commit activity for %s/%s: %s", owner, repo, e)
            return 0

    # GitHub's Search API allows ~30 requests/minute regardless of token. Pace each
    # search so the whole (now larger) topic/language sweep stays under that limit
    # instead of the tail getting rate-limited and returning nothing.
    _SEARCH_SPACING_SEC = 2.1

    async def fetch_trending_by_topic(self, topic: str, days_pushed: int = 1) -> list[dict]:
        """Fetch repos that match a topic and were pushed recently."""
        from datetime import date, timedelta
        await asyncio.sleep(self._SEARCH_SPACING_SEC)
        since = (date.today() - timedelta(days=days_pushed)).isoformat()
        query = f"topic:{topic} pushed:>={since}"
        try:
            result = await self.search_repositories(query, sort="stars", per_page=100)
            return result.get("items", [])
        except Exception as e:
            logger.error("Failed to fetch topic %s: %s", topic, e)
            return []

    async def fetch_trending_by_language(self, language: str, days_pushed: int = 7) -> list[dict]:
        """Fetch top repos for a language updated recently."""
        from datetime import date, timedelta
        await asyncio.sleep(self._SEARCH_SPACING_SEC)
        since = (date.today() - timedelta(days=days_pushed)).isoformat()
        query = f"language:{language} pushed:>={since} stars:>100"
        try:
            result = await self.search_repositories(query, sort="stars", per_page=50)
            return result.get("items", [])
        except Exception as e:
            logger.error("Failed to fetch language %s: %s", language, e)
            return []

    async def get_recent_releases(self, owner: str, repo: str, n: int = 5) -> list[dict]:
        """Latest published (non-draft) releases, newest first."""
        try:
            data = await self._get(f"/repos/{owner}/{repo}/releases", params={"per_page": n})
        except Exception as e:
            logger.warning("Failed to get releases for %s/%s: %s", owner, repo, e)
            return []
        out = []
        for rel in data if isinstance(data, list) else []:
            if rel.get("draft") or not rel.get("published_at") or not rel.get("tag_name"):
                continue
            body = " ".join((rel.get("body") or "").split())
            out.append({
                "tag": rel["tag_name"][:200],
                "name": (rel.get("name") or rel["tag_name"])[:300],
                "published_at": _parse_dt(rel["published_at"]),
                "url": rel.get("html_url"),
                "prerelease": bool(rel.get("prerelease")),
                "snippet": body[:280] or None,
            })
        return out

    async def get_starred(self, login: str, max_pages: int = 3) -> list[dict] | None:
        """
        A user's starred repos (newest first, up to 100 per page). None if the
        user doesn't exist. Only the fields the radar needs are kept.
        """
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            try:
                data = await self._get(f"/users/{login}/starred", params={"per_page": 100, "page": page})
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise
            for r in data if isinstance(data, list) else []:
                out.append({
                    "full_name": r.get("full_name"),
                    "language": r.get("language"),
                    "topics": r.get("topics") or [],
                })
            if not isinstance(data, list) or len(data) < 100:
                break
        return out

    def parse_repo_data(self, raw: dict) -> dict:
        """Transform GitHub API response to our model fields."""
        owner_data = raw.get("owner", {})
        license_data = raw.get("license") or {}
        return {
            "github_id": raw["id"],
            "owner": owner_data.get("login", ""),
            "name": raw["name"],
            "full_name": raw["full_name"],
            "description": raw.get("description"),
            "language": raw.get("language"),
            "license": license_data.get("spdx_id"),
            "topics": raw.get("topics", []),
            "homepage_url": raw.get("homepage") or None,
            "default_branch": raw.get("default_branch", "main"),
            "is_archived": raw.get("archived", False),
            "is_fork": raw.get("fork", False),
            "is_template": raw.get("is_template", False),
            "latest_stars": raw.get("stargazers_count", 0),
            "latest_forks": raw.get("forks_count", 0),
            "latest_watchers": raw.get("watchers_count", 0),
            "open_issues": raw.get("open_issues_count", 0),
            "github_created_at": _parse_dt(raw.get("created_at")),
            "github_updated_at": _parse_dt(raw.get("updated_at")),
            "github_pushed_at": _parse_dt(raw.get("pushed_at")),
        }


# Module-level singleton
github_service = GitHubService()
