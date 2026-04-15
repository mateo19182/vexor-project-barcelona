"""Reverse-image-search provider client.

Two small async helpers:

* ``fetch_instagram_profile_pic`` — resolve an Instagram handle to a public
  profile-picture URL via the hikerapi v1 endpoint. Uses the same
  ``HIKERAPI_TOKEN`` that the Instagram enrichment already reads from
  settings.
* ``reverse_image_lookup`` — POST the image URL to SerpAPI's ``google_lens``
  engine with ``type=exact_matches`` and normalize the ``exact_matches``
  payload into a list of :class:`VisualMatch` records. Exact-match only
  (not generic visual matches) — keeps results to pages that host the
  *same* image rather than visually-similar lookalikes.

Deliberately thin: no interpretation of matches lives here — that's the
module's job. This file only speaks HTTP.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings

HIKERAPI_BASE = "https://api.hikerapi.com"
SERPAPI_BASE = "https://serpapi.com/search.json"

_TIMEOUT = 30.0


def _log(msg: str) -> None:
    print(f"[reverse_image] {msg}", file=sys.stderr, flush=True)


@dataclass(frozen=True)
class VisualMatch:
    """Normalized exact-match record from SerpAPI google_lens.

    Name retained for backwards-compatibility — entries now come from the
    ``exact_matches`` response field (``type=exact_matches``), meaning the
    page hosts the same image bytes rather than a visually-similar one.
    """

    url: str           # Page URL where the image appears
    title: str         # Page title (may be empty)
    domain: str        # Lowercased hostname (e.g. "linkedin.com")
    thumbnail: str     # URL of the matched thumbnail (may be empty)


async def fetch_instagram_profile_pic(handle: str) -> str | None:
    """Return the HD profile-pic URL for ``handle`` via hikerapi.

    Returns ``None`` if the token is missing, the lookup errors, or the
    response is missing the expected field. Errors are logged, never raised —
    the caller decides whether a missing picture is a gap or a skip.
    """
    token = settings.hikerapi_token
    if not token:
        _log("HIKERAPI_TOKEN not set — cannot resolve IG profile pic")
        return None

    handle = handle.lstrip("@").strip()
    if not handle:
        return None

    url = f"{HIKERAPI_BASE}/v1/user/by/username"
    headers = {"x-access-key": token, "accept": "application/json"}
    params = {"username": handle}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        _log(f"hikerapi request failed for @{handle}: {exc}")
        return None

    if resp.status_code != 200:
        _log(f"hikerapi HTTP {resp.status_code} for @{handle}: {resp.text[:200]}")
        return None

    try:
        data = resp.json()
    except ValueError:
        _log(f"hikerapi returned non-JSON for @{handle}")
        return None

    # hikerapi wraps the user object under `user` in some schema versions and
    # returns it flat in others — tolerate both.
    user = data.get("user") if isinstance(data, dict) else None
    if not isinstance(user, dict):
        user = data if isinstance(data, dict) else {}

    pic = user.get("profile_pic_url_hd") or user.get("profile_pic_url")
    if not isinstance(pic, str) or not pic.startswith("http"):
        _log(f"hikerapi response missing profile_pic_url for @{handle}")
        return None

    _log(f"resolved @{handle} profile pic: {pic[:80]}...")
    return pic


async def reverse_image_lookup(
    image_url: str,
    *,
    limit: int = 25,
) -> list[VisualMatch]:
    """Run SerpAPI google_lens exact-match search and return normalized matches.

    Uses ``type=exact_matches`` so SerpAPI returns only pages hosting the
    *same* image, not visually-similar ones. This removes the bulk of the
    lookalike noise (random faces that happen to match generic features)
    while still being identity-unverified — a subject can share a stock
    photo, or a photo may be reused across unrelated re-uploads.

    Raises ``RuntimeError`` if ``SERPAPI_API_KEY`` is unset — the caller is
    expected to check configuration first. HTTP / JSON errors surface as
    exceptions; the caller logs and converts them to a module ``error`` state.
    """
    api_key = settings.serpapi_api_key
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY not configured")

    params = {
        "engine": "google_lens",
        "type": "exact_matches",
        "url": image_url,
        "api_key": api_key,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(SERPAPI_BASE, params=params)
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, dict):
        return []

    raw_matches = data.get("exact_matches") or []
    if not isinstance(raw_matches, list):
        return []

    out: list[VisualMatch] = []
    for raw in raw_matches[:limit]:
        if not isinstance(raw, dict):
            continue
        link = str(raw.get("link") or "").strip()
        if not link:
            continue
        domain = ""
        try:
            host = urlparse(link).hostname or ""
            domain = host.lower()
        except ValueError:
            domain = ""
        # Prefer `title`; fall back to `source` (site name) when the entry
        # has no page title — common for exact-match results.
        title = str(raw.get("title") or raw.get("source") or "").strip()
        out.append(
            VisualMatch(
                url=link,
                title=title,
                domain=domain,
                thumbnail=str(raw.get("thumbnail") or "").strip(),
            )
        )

    _log(
        f"serpapi google_lens exact_matches: {len(raw_matches)} match(es), "
        f"{len(out)} usable after limit={limit}"
    )
    return out
