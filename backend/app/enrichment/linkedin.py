"""LinkedIn enrichment via LinkdAPI (https://linkdapi.com).

Two endpoints are used:
  * ``/api/v1/profile/overview?username=<handle>`` — basic profile info.
  * ``/api/v1/profile/details?urn=<urn>`` — richer details (headline,
    summary, location, verification) when the overview surfaces a URN.

Returns plain dicts; on failure returns ``{"error": ...}`` so the pipeline
module can translate into gaps without catching exceptions.
"""

from __future__ import annotations

import re

import httpx

_BASE = "https://api.linkdapi.com/api/v1"
_USERNAME_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def extract_username(linkedin_url: str) -> str | None:
    """Pull the vanity slug out of a linkedin.com/in/<slug> URL."""
    if not linkedin_url:
        return None
    m = _USERNAME_RE.search(linkedin_url)
    return m.group(1).strip().rstrip("/") if m else None


async def _get(client: httpx.AsyncClient, path: str, params: dict, api_key: str) -> dict:
    try:
        r = await client.get(
            f"{_BASE}{path}",
            params=params,
            headers={"X-linkdapi-apikey": api_key},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return {"error": "http_error", "detail": str(exc)}
    if r.status_code >= 400:
        return {
            "error": "api_error",
            "status": r.status_code,
            "detail": r.text[:500],
        }
    try:
        return r.json()
    except ValueError:
        return {"error": "bad_json", "detail": r.text[:500]}


async def enrich_linkedin(linkedin_url: str, api_key: str) -> dict:
    """Fetch LinkdAPI overview (+ details when a URN is returned)."""
    username = extract_username(linkedin_url)
    if not username:
        return {"error": "bad_url", "detail": f"could not parse slug from {linkedin_url!r}"}

    async with httpx.AsyncClient() as client:
        overview = await _get(client, "/profile/overview", {"username": username}, api_key)

        if "error" in overview:
            return {
                "username": username,
                "profile_url": linkedin_url,
                "overview": overview,
                "details": None,
            }

        urn = overview.get("urn") or overview.get("profileUrn") or overview.get("id")
        details: dict | None = None
        if urn:
            details = await _get(client, "/profile/details", {"urn": urn}, api_key)

        return {
            "username": username,
            "profile_url": linkedin_url,
            "urn": urn,
            "overview": overview,
            "details": details,
        }
