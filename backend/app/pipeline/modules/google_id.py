"""Google ID resolver module.

Input  (requires): ctx.email
Output (ctx_patch): ctx.gaia_id

Resolves a Gmail address to its Google Gaia ID using the same technique as
GHunt (https://github.com/mxrch/GHunt): authenticates against Google's
internal people-pa endpoint via SAPISIDHASH + the Photos API key.

Auth: GOOGLE_SESSION_COOKIES in .env — JSON dict of Google session cookies.
Copy from Chrome DevTools → Application → Cookies → google.com.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time

import httpx

from app.config import settings
from app.models import AttributedValue, ContextPatch
from app.pipeline.base import Context, ModuleResult

_PEOPLE_URL = "https://people-pa.clients6.google.com/v2/people/lookup"
_PHOTOS_ORIGIN = "https://photos.google.com"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_cookies() -> dict[str, str] | None:
    raw = settings.google_session_cookies
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        if isinstance(data, list):
            return {str(c["name"]): str(c["value"]) for c in data if "name" in c and "value" in c}
    except Exception as e:  # noqa: BLE001
        _log(f"[google_id] cannot parse GOOGLE_SESSION_COOKIES: {e}")
    return None


def _sapisid_hash(sapisid: str, origin: str) -> str:
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    return f"{ts}_{digest}"


async def resolve_gaia_id(email: str, cookies: dict[str, str]) -> str | None:
    """Resolve a Gmail address to its Gaia ID via Google's people-pa API."""
    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-1PAPISID") or ""
    if not sapisid:
        _log("[google_id] no SAPISID cookie found")
        return None

    headers = {
        "Host": "people-pa.clients6.google.com",
        "Authorization": f"SAPISIDHASH {_sapisid_hash(sapisid, _PHOTOS_ORIGIN)}",
        "X-Goog-AuthUser": "0",
        "X-Goog-Api-Key": settings.google_photos_api_key,
        "Origin": _PHOTOS_ORIGIN,
        "Referer": _PHOTOS_ORIGIN,
        "User-Agent": _UA,
    }
    params = {
        "id": email,
        "type": "EMAIL",
        "matchType": "EXACT",
        "requestMask.includeField.paths": "person.metadata",
    }

    try:
        async with httpx.AsyncClient(cookies=cookies, timeout=15.0) as client:
            resp = await client.get(_PEOPLE_URL, params=params, headers=headers)
        _log(f"[google_id] people-lookup HTTP {resp.status_code}")

        if resp.status_code != 200:
            _log(f"[google_id] response: {resp.text[:400]}")
            return None

        data = resp.json()
        people = data.get("people") or {}
        if isinstance(people, dict) and people:
            gaia_id = next(iter(people))
            _log(f"[google_id] {email} → {gaia_id}")
            return gaia_id
        matches = data.get("matches") or []
        if matches:
            ids = matches[0].get("personId") or []
            if ids:
                _log(f"[google_id] {email} → {ids[0]} (from matches)")
                return str(ids[0])

        _log(f"[google_id] no result for {email}: {json.dumps(data)[:200]}")
        return None

    except Exception as e:  # noqa: BLE001
        _log(f"[google_id] lookup error: {e}")
        return None


class GoogleIdModule:
    name = "google_id"
    requires: tuple[str, ...] = ("email",)

    async def run(self, ctx: Context) -> ModuleResult:
        if ctx.gaia_id:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary=f"Gaia ID already in context: {ctx.gaia_id}",
            )

        cookies = _load_cookies()
        if cookies is None:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["GOOGLE_SESSION_COOKIES not set in .env"],
            )

        email = ctx.email or ""
        gaia_id = await resolve_gaia_id(email, cookies)

        if not gaia_id:
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=[f"Could not resolve Gaia ID for {email}. Cookies may be expired."],
                raw={"email": email},
            )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=f"{email} → Gaia ID {gaia_id}",
            ctx_patch=ContextPatch(
                gaia_id=AttributedValue(
                    value=gaia_id,
                    source=f"https://www.google.com/maps/contrib/{gaia_id}",
                    confidence=1.0,
                )
            ),
            raw={"email": email, "gaia_id": gaia_id},
        )
