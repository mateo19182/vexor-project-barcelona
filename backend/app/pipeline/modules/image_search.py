"""Reverse-image-search module.

Runs SerpAPI's ``google_lens`` engine in ``exact_matches`` mode against the
subject's Instagram profile picture, then surfaces each exact match as a
candidate other-platform profile (or a generic web appearance).

Exact-match only — we deliberately skip the broader ``visual_matches``
results because those are dominated by lookalike faces that share only
generic features (hair colour, pose, crop) and produce an unusable amount
of noise. Exact matches restrict the response to pages hosting the *same
image bytes*, which is a far stronger signal.

Critical honesty caveat: exact-image reuse is still **not** identity
verification. A subject can avatar a stock photo, re-upload someone else's
picture, or share a family photo — any of which will surface unrelated
pages. Everything emitted is hard-capped at low confidence and labelled as
a visual-only match so synthesis and the human collector treat the entries
as leads to verify — not as ground truth.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.enrichment.image_store import download_image, get_photos_dir
from app.enrichment.reverse_image import (
    VisualMatch,
    fetch_instagram_profile_pic,
    reverse_image_lookup,
)
from app.models import Fact, Signal, SocialLink
from app.pipeline.base import Context, ModuleResult

# Confidence ceilings — matches are visual-only, identity unverified.
SOCIAL_LINK_CONFIDENCE = 0.3
FACT_CONFIDENCE = 0.2

# Cap the number of matches we pull from SerpAPI; more = noisier.
MAX_MATCHES = 25

# Same warning string used on every run — keeps the dossier consistent and
# makes it easy to grep for unverified findings.
UNVERIFIED_GAP = (
    "Visual-match results are not identity-verified; manual or LLM "
    "same-person check required before trusting any discovered profile."
)

# domain (lowercased, suffix-match) -> canonical platform name
PLATFORM_BY_DOMAIN: dict[str, str] = {
    "linkedin.com": "LinkedIn",
    "twitter.com": "Twitter",
    "x.com": "Twitter",
    "facebook.com": "Facebook",
    "fb.com": "Facebook",
    "instagram.com": "Instagram",
    "threads.net": "Threads",
    "tiktok.com": "TikTok",
    "github.com": "GitHub",
    "youtube.com": "YouTube",
    "reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
    "medium.com": "Medium",
    "substack.com": "Substack",
    "about.me": "About.me",
    "behance.net": "Behance",
    "dribbble.com": "Dribbble",
    "stackoverflow.com": "Stack Overflow",
    "quora.com": "Quora",
}


def _log(msg: str) -> None:
    print(f"[image_search] {msg}", file=sys.stderr, flush=True)


def _platform_for(domain: str) -> str | None:
    if not domain:
        return None
    domain = domain.lower().lstrip(".")
    for suffix in sorted(PLATFORM_BY_DOMAIN, key=len, reverse=True):
        if domain == suffix or domain.endswith(f".{suffix}"):
            return PLATFORM_BY_DOMAIN[suffix]
    return None


_HANDLE_PATTERNS: dict[str, re.Pattern[str]] = {
    "LinkedIn": re.compile(r"^/in/([A-Za-z0-9_\-%.]+)/?"),
    "GitHub": re.compile(r"^/([A-Za-z0-9][A-Za-z0-9_\-]*)/?$"),
    "Twitter": re.compile(r"^/([A-Za-z0-9_]+)/?$"),
    "TikTok": re.compile(r"^/@([A-Za-z0-9_.]+)/?"),
    "Instagram": re.compile(r"^/([A-Za-z0-9_.]+)/?$"),
    "Medium": re.compile(r"^/@([A-Za-z0-9_.\-]+)/?"),
    "Threads": re.compile(r"^/@([A-Za-z0-9_.]+)/?"),
    "Behance": re.compile(r"^/([A-Za-z0-9_\-]+)/?$"),
    "Dribbble": re.compile(r"^/([A-Za-z0-9_\-]+)/?$"),
}

_TWITTER_RESERVED = {
    "i", "status", "home", "explore", "notifications", "messages",
    "search", "settings", "login", "signup", "tos", "privacy",
}


def _extract_handle(platform: str, url: str) -> str | None:
    pattern = _HANDLE_PATTERNS.get(platform)
    if not pattern:
        return None
    try:
        path = urlparse(url).path or "/"
    except ValueError:
        return None
    m = pattern.match(path)
    if not m:
        return None
    handle = m.group(1).strip()
    if not handle:
        return None
    if platform == "Twitter" and handle.lower() in _TWITTER_RESERVED:
        return None
    return handle


def _is_self_match(match: VisualMatch, subject_handle: str) -> bool:
    """True if this match is the same IG profile we started from."""
    if "instagram.com" not in match.domain:
        return False
    try:
        path = urlparse(match.url).path or "/"
    except ValueError:
        return False
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    return segments[0].lower() == subject_handle.lower()


class ImageSearchModule:
    name = "image_search"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "instagram"),)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()

        ig_sig = ctx.best("contact", "instagram")
        handle = (ig_sig.value if ig_sig else "").lstrip("@").strip()
        if not handle:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["No instagram signal on context"],
                duration_s=time.monotonic() - t0,
            )

        if not settings.serper_api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary="Reverse-image search disabled (SERPER_API_KEY not set).",
                gaps=["SERPER_API_KEY not configured — module disabled"],
                duration_s=time.monotonic() - t0,
            )
        if not settings.hikerapi_token:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary="Reverse-image search disabled (HIKERAPI_TOKEN not set).",
                gaps=[
                    "HIKERAPI_TOKEN not configured — cannot resolve Instagram "
                    "profile picture URL"
                ],
                duration_s=time.monotonic() - t0,
            )

        _log(f"looking up profile pic for @{handle}")
        image_url = await fetch_instagram_profile_pic(handle)
        if not image_url:
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=(
                    f"Could not resolve Instagram profile picture URL for "
                    f"@{handle}; reverse-image search skipped."
                ),
                gaps=[
                    "Failed to resolve Instagram profile picture URL via "
                    "hikerapi — reverse-image search not attempted",
                ],
                raw={"provider": "serpapi_google_lens_exact", "handle": handle},
                duration_s=time.monotonic() - t0,
            )

        _log(f"running SerpAPI google_lens exact_matches on {image_url[:80]}...")
        try:
            matches = await reverse_image_lookup(image_url, limit=MAX_MATCHES)
        except httpx.HTTPStatusError as exc:
            _log(f"serpapi HTTP {exc.response.status_code}: {exc.response.text[:200]}")
            return ModuleResult(
                name=self.name,
                status="error",
                summary="Reverse-image search failed.",
                gaps=[f"SerpAPI returned HTTP {exc.response.status_code}"],
                raw={
                    "provider": "serpapi_google_lens_exact",
                    "image_url": image_url,
                    "handle": handle,
                    "http_status": exc.response.status_code,
                },
                duration_s=time.monotonic() - t0,
            )
        except (httpx.HTTPError, ValueError) as exc:
            _log(f"serpapi request failed: {exc}")
            return ModuleResult(
                name=self.name,
                status="error",
                summary="Reverse-image search failed.",
                gaps=[f"SerpAPI request error: {type(exc).__name__}"],
                raw={
                    "provider": "serpapi_google_lens_exact",
                    "image_url": image_url,
                    "handle": handle,
                },
                duration_s=time.monotonic() - t0,
            )

        # Drop the source IG profile itself — it's not a lead.
        matches = [m for m in matches if not _is_self_match(m, handle)]

        social_links: list[SocialLink] = []
        facts: list[Fact] = []
        platform_counts: Counter[str] = Counter()

        for match in matches:
            platform = _platform_for(match.domain)
            if platform:
                platform_counts[platform] += 1
                social_links.append(
                    SocialLink(
                        platform=platform,
                        url=match.url,
                        handle=_extract_handle(platform, match.url),
                        confidence=SOCIAL_LINK_CONFIDENCE,
                    )
                )
            else:
                title = match.title or match.domain or match.url
                facts.append(
                    Fact(
                        claim=f"Profile picture also appears on: {title}",
                        source=match.url,
                        confidence=FACT_CONFIDENCE,
                    )
                )

        gaps: list[str] = [UNVERIFIED_GAP]
        if not matches:
            gaps.append("No exact image matches found for the profile picture")
            summary = (
                f"Reverse image search (exact match) on @{handle}'s profile "
                f"picture returned no matches."
            )
        else:
            platform_summary = (
                ", ".join(
                    f"{p} ({n})" for p, n in platform_counts.most_common()
                )
                if platform_counts
                else "no recognised platforms"
            )
            summary = (
                f"Reverse image search (exact match) on @{handle}'s profile "
                f"picture returned {len(matches)} exact match(es); candidate "
                f"profiles on {platform_summary}. Same-image reuse is not "
                "identity-verified — matches may be stock photos, re-uploads, "
                "or unrelated accounts."
            )

        # Download profile pic + match thumbnails to centralized photos dir.
        # Emit contact:photo so vision_batch is scheduled after us.
        rm_dir = get_photos_dir(ctx.case.case_id, "reverse_matches")
        source_downloaded = await download_image(image_url, rm_dir / f"{handle}_source.jpg")
        for idx, match in enumerate(matches):
            if match.thumbnail:
                await download_image(
                    match.thumbnail,
                    rm_dir / f"{handle}_match_{idx:03d}.jpg",
                )

        extra_signals: list[Signal] = []
        if source_downloaded:
            extra_signals.append(Signal(
                kind="contact", tag="photo",
                value=image_url,
                source=f"https://www.instagram.com/{handle}/",
                confidence=0.75,
                notes=f"Instagram profile picture used for reverse-image search",
            ))

        _log(
            f"done: {len(matches)} match(es), {len(social_links)} social_link(s), "
            f"{len(facts)} fact(s), platforms={dict(platform_counts)}"
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=extra_signals,
            social_links=social_links,
            facts=facts,
            gaps=gaps,
            raw={
                "provider": "serpapi_google_lens_exact",
                "handle": handle,
                "image_url": image_url,
                "exact_match_count": len(matches),
                "platform_breakdown": dict(platform_counts),
                "raw_matches": [
                    {
                        "url": m.url,
                        "title": m.title,
                        "domain": m.domain,
                        "thumbnail": m.thumbnail,
                    }
                    for m in matches
                ],
            },
            duration_s=time.monotonic() - t0,
        )
