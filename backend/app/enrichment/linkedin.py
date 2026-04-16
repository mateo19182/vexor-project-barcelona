"""LinkedIn enrichment via LinkdAPI (https://linkdapi.com).

Two endpoints are used:
  * ``/api/v1/profile/overview?username=<slug>`` — basic profile info;
    returns the URN we need for the details call.
  * ``/api/v1/profile/details?urn=<urn>`` — richer details: about text,
    featured posts, positions, etc.

Both endpoints wrap the payload as
``{success, statusCode, message, errors, data}``; we unwrap ``data`` here
so callers see the fields directly. On HTTP / parse failure we return a
dict containing ``{"error": ..., "detail": ...}`` under whichever key
failed, never raising.
"""

from __future__ import annotations

import re

import httpx

_BASE = "https://linkdapi.com/api/v1"
_USERNAME_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def extract_username(linkedin_url: str) -> str | None:
    """Pull the vanity slug out of a linkedin.com/in/<slug> URL."""
    if not linkedin_url:
        return None
    m = _USERNAME_RE.search(linkedin_url)
    return m.group(1).strip().rstrip("/") if m else None


async def _get(
    client: httpx.AsyncClient, path: str, params: dict, api_key: str
) -> dict:
    """GET + unwrap LinkdAPI's ``data`` envelope. Errors come back as dicts."""
    try:
        r = await client.get(
            f"{_BASE}{path}",
            params=params,
            headers={"X-linkdapi-apikey": api_key},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return {"error": "http_error", "detail": str(exc)}

    try:
        body = r.json()
    except ValueError:
        return {
            "error": "bad_json",
            "status": r.status_code,
            "detail": r.text[:500],
        }

    if r.status_code >= 400 or not body.get("success"):
        return {
            "error": "api_error",
            "status": r.status_code,
            "detail": body.get("message") or str(body)[:500],
        }

    return body.get("data") or {}


async def enrich_linkedin(linkedin_url: str, api_key: str) -> dict:
    """Fetch LinkdAPI overview (+ details when the URN is available)."""
    username = extract_username(linkedin_url)
    if not username:
        return {
            "error": "bad_url",
            "detail": f"could not parse slug from {linkedin_url!r}",
        }

    async with httpx.AsyncClient() as client:
        overview = await _get(
            client, "/profile/overview", {"username": username}, api_key
        )

        if "error" in overview:
            return {
                "username": username,
                "profile_url": linkedin_url,
                "overview": overview,
                "details": None,
            }

        urn = overview.get("urn")
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
