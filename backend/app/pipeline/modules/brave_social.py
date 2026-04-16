"""Brave Search social-link discovery module.

Builds targeted ``site:`` queries from the subject's name and known
usernames, hits the Brave Web Search API, and emits SocialLinks for any
results that land on recognized social platforms. The runner auto-converts
those to ``contact`` signals, unlocking downstream platform modules.

Requires only a ``name`` signal. Runs early (wave 1) so its output feeds
Instagram/Twitter/LinkedIn modules in later waves.
"""

from __future__ import annotations

import asyncio
import re
import sys
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models import SocialLink
from app.pipeline.base import Context, ModuleResult

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# platform label → domain used in site: queries
PLATFORMS: dict[str, str] = {
    "linkedin": "linkedin.com",
    "instagram": "instagram.com",
    "twitter": "x.com",
    "facebook": "facebook.com",
    "github": "github.com",
    "tiktok": "tiktok.com",
}

# extra domain aliases that map back to the same platform
_DOMAIN_TO_PLATFORM: dict[str, str] = {
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "x.com": "twitter",
    "twitter.com": "twitter",
    "facebook.com": "facebook",
    "github.com": "github",
    "tiktok.com": "tiktok",
}

# URL patterns that look like actual profile pages (not search/help/about)
_PROFILE_PATH_RE = re.compile(r"^/[^/]+/?$")  # e.g. /username or /in/username


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _extract_handle(url: str, platform: str) -> str | None:
    """Best-effort handle extraction from a profile URL."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    # LinkedIn: /in/<handle>
    if platform == "linkedin" and len(parts) >= 2 and parts[0] == "in":
        return parts[1]
    # Most platforms: /<handle>
    if len(parts) == 1:
        return parts[0]
    return None


def _is_profile_url(url: str, platform: str) -> bool:
    """Filter out non-profile pages (help articles, search pages, etc.)."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return False
    # reject obvious non-profile paths
    reject = {"help", "about", "search", "explore", "settings", "legal", "privacy", "terms"}
    if parts[0].lower() in reject:
        return False
    # LinkedIn profiles live under /in/<slug> or /company/<slug>
    if platform == "linkedin":
        return len(parts) >= 2 and parts[0] in ("in", "company", "pub")
    # everything else: top-level path = profile
    return len(parts) <= 2


def _build_queries(ctx: Context) -> list[tuple[str, str]]:
    """Return (query_string, platform) pairs to search."""
    queries: list[tuple[str, str]] = []

    name_sig = ctx.best("name")
    name = name_sig.value if name_sig else None

    # Collect known usernames/handles from contact signals
    handles: list[str] = []
    for tag in ("instagram", "twitter", "linkedin", "github", "facebook", "tiktok"):
        for sig in ctx.all("contact", tag):
            h = sig.value.lstrip("@").strip()
            if h:
                handles.append(h)

    # Also grab email local-part as a potential username
    email_sig = ctx.best("contact", "email")
    if email_sig:
        local = email_sig.value.split("@")[0].strip()
        if local and local not in handles:
            handles.append(local)

    country = ctx.case.country or ""

    # For each platform, search with the name (+ country hint)
    if name:
        for platform, domain in PLATFORMS.items():
            q = f'"{name}" site:{domain}'
            if country:
                q += f" {country}"
            queries.append((q, platform))

    # For each known handle, search across all platforms
    for handle in handles:
        for platform, domain in PLATFORMS.items():
            queries.append((f"{handle} site:{domain}", platform))

    return queries


async def _brave_search(query: str, api_key: str) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": 5}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(BRAVE_SEARCH_URL, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    return (data.get("web") or {}).get("results") or []


class BraveSocialModule:
    name = "brave_social"
    requires: tuple[tuple[str, str | None], ...] = (("name", None),)

    async def run(self, ctx: Context) -> ModuleResult:
        api_key = settings.brave_api_key
        if not api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["BRAVE_API_KEY not configured"],
            )

        queries = _build_queries(ctx)
        if not queries:
            return ModuleResult(
                name=self.name,
                status="no_data",
                gaps=["No name or handles available to search"],
            )

        _log(f"[brave_social] running {len(queries)} queries")

        # Fire all queries concurrently
        tasks = [_brave_search(q, api_key) for q, _ in queries]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls: set[str] = set()
        social_links: list[SocialLink] = []
        all_queries: list[str] = []
        errors: list[str] = []

        for (query, platform), result in zip(queries, raw_results):
            all_queries.append(query)
            if isinstance(result, Exception):
                errors.append(f"{query}: {result}")
                continue
            for item in result:
                url = (item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                # verify the URL actually belongs to this platform
                matched_platform = _domain_match(url)
                if matched_platform != platform:
                    continue
                if not _is_profile_url(url, platform):
                    continue
                seen_urls.add(url)
                handle = _extract_handle(url, platform)
                social_links.append(SocialLink(
                    platform=platform,
                    url=url,
                    handle=handle,
                    confidence=0.65,
                ))

        _log(
            f"[brave_social] done: {len(social_links)} link(s) from "
            f"{len(queries)} queries, {len(errors)} error(s)"
        )

        gaps = []
        if errors:
            gaps.append(f"{len(errors)} search(es) failed")
        if not social_links:
            gaps.append("No social profiles found via Brave search")

        return ModuleResult(
            name=self.name,
            status="ok" if social_links else "no_data",
            summary=(
                f"Found {len(social_links)} social profile(s) via Brave search"
                if social_links
                else "No social profiles found"
            ),
            social_links=social_links,
            gaps=gaps,
            raw={
                "queries": all_queries,
                "links_found": len(social_links),
                "errors": errors,
            },
        )


def _domain_match(url: str) -> str | None:
    """Return platform name if URL belongs to a known social domain."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    for domain, platform in _DOMAIN_TO_PLATFORM.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None
