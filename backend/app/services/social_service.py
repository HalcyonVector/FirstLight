"""
Lobsters and Bluesky, the other public places a repo gets shared, used to
explain star spikes alongside Hacker News. Both are read without a key:

- Lobsters has no search API, but /domains/<host>.json lists every story
  linking to a site. Two pages of github.com cover several weeks.
- Bluesky's AppView search (api.bsky.app) takes a date window.
"""

import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

LOBSTERS = "https://lobste.rs"
BLUESKY_SEARCH = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"


class LobstersRateLimited(Exception):
    """Lobsters said 429: stop asking it for the rest of the run."""


async def lobsters_domain(client: httpx.AsyncClient, host: str, pages: int = 1) -> list[dict]:
    """Stories linking to host, newest first."""
    out = []
    for page in range(1, pages + 1):
        path = f"/domains/{host}.json" if page == 1 else f"/domains/{host}/page/{page}.json"
        try:
            resp = await client.get(LOBSTERS + path, timeout=15.0)
            # Lobsters answers 500 (not 404) for a domain nobody has posted, so both mean "no stories".
            if resp.status_code in (404, 500):
                break
            if resp.status_code == 429:
                raise LobstersRateLimited(host)
            resp.raise_for_status()
            items = resp.json()
        except LobstersRateLimited:
            raise
        except Exception as e:  # noqa: BLE001 -- explanations are best-effort
            logger.warning("Lobsters lookup failed for %s: %s", host, e)
            break
        for s in items if isinstance(items, list) else []:
            out.append({
                "id": s.get("short_id"),
                "title": s.get("title") or "",
                "url": s.get("url") or "",
                "points": int(s.get("score") or 0),
                "comments": int(s.get("comment_count") or 0),
                "at": s.get("created_at"),
                "link": s.get("short_id_url") or f"{LOBSTERS}/s/{s.get('short_id')}",
            })
        if not items:
            break
    return out


def _post_links(post: dict) -> list[str]:
    """Every URL a Bluesky post carries: link facets and an embedded card."""
    record = post.get("record") or {}
    links = [
        f.get("uri")
        for facet in record.get("facets") or []
        for f in facet.get("features") or []
        if f.get("uri")
    ]
    external = ((post.get("embed") or {}).get("external") or {}).get("uri")
    if external:
        links.append(external)
    return links


async def bluesky_posts(client: httpx.AsyncClient, query: str, start: datetime, end: datetime) -> list[dict]:
    """Top posts matching query in [start, end], with the links they carry."""
    try:
        resp = await client.get(
            BLUESKY_SEARCH,
            params={"q": query, "sort": "top", "limit": 25,
                    "since": start.isoformat().replace("+00:00", "Z"),
                    "until": end.isoformat().replace("+00:00", "Z")},
            timeout=15.0,
        )
        resp.raise_for_status()
        posts = resp.json().get("posts") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("Bluesky search failed for %r: %s", query, e)
        return []
    out = []
    for p in posts:
        handle = (p.get("author") or {}).get("handle") or ""
        rkey = (p.get("uri") or "").rsplit("/", 1)[-1]
        out.append({
            "id": p.get("uri"),
            "title": " ".join(((p.get("record") or {}).get("text") or "").split())[:160],
            "links": _post_links(p),
            "points": int(p.get("likeCount") or 0),
            "comments": int(p.get("repostCount") or 0),
            "at": (p.get("record") or {}).get("createdAt"),
            "link": f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else None,
        })
    return out
