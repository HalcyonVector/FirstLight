"""
Hacker News stories via the public Algolia search API (no key, generous limits).
Used to explain star spikes: a Show HN or front-page link usually precedes one.
"""

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

HN_SEARCH = "https://hn.algolia.com/api/v1/search"


async def stories_between(client: httpx.AsyncClient, query: str, start: datetime, end: datetime) -> list[dict]:
    """Stories matching query posted in [start, end], most points first."""
    try:
        resp = await client.get(
            HN_SEARCH,
            params={
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{int(start.timestamp())},created_at_i<{int(end.timestamp())}",
                "hitsPerPage": 10,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception as e:  # noqa: BLE001 -- explanations are best-effort
        logger.warning("HN search failed for %r: %s", query, e)
        return []
    out = []
    for h in hits:
        out.append({
            "id": h.get("objectID"),
            "title": h.get("title") or "",
            "url": h.get("url") or "",
            "points": int(h.get("points") or 0),
            "comments": int(h.get("num_comments") or 0),
            "at": datetime.fromtimestamp(int(h.get("created_at_i") or 0), tz=timezone.utc).isoformat(),
        })
    return sorted(out, key=lambda s: -s["points"])
