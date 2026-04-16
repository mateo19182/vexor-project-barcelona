"""Shared client for the platform-registration check API.

The upstream exposes one VM per platform, each with the same two-step shape:

  POST /cs  →  {"s": "<session-uuid>"}        # session create (empty body)
  POST /h   →  {"s": "<status>"}              # handle check
      body: {"s": session, "w": identifier, "p": proxy_url}

Observed status values (as of 2026-04-16 probing):
  Twitter VM   : REGISTERED        → registered=True
  iCloud VM    : SUCCESS / FAIL    → True / False
  Instagram VM : INVALID           → treated as ambiguous

The upstream speaks HTTPS on a self-signed cert — we disable verification.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

_TIMEOUT = 20.0
# Map upstream status strings to a tri-state:
#   True  → confirmed registered
#   False → confirmed not registered
#   None  → ambiguous (bad session, rate-limit, malformed identifier, etc.)
_STATUS_MAP: dict[str, bool | None] = {
    "REGISTERED": True,
    "SUCCESS": True,
    "VALID": True,
    "FOUND": True,
    "NOT_REGISTERED": False,
    "FAIL": False,
    "NOT_FOUND": False,
    "UNREGISTERED": False,
    "INVALID": None,
    "ERROR": None,
}


def _log(platform: str, msg: str) -> None:
    print(f"[{platform}_check] {msg}", file=sys.stderr, flush=True)


@dataclass
class PlatformCheckResult:
    """Outcome of a single registration check."""

    registered: bool | None
    status_raw: str
    identifier: str
    http_status: int
    session_id: str | None
    duration_s: float
    error: str | None = None
    data: dict[str, Any] | None = None  # rich "d" payload from REGISTERED responses


async def check_platform(
    *,
    platform: str,
    host: str,
    port: str,
    api_key: str,
    identifier: str,
    proxy: str,
) -> PlatformCheckResult:
    """Run the /cs → /h flow for one identifier against one platform VM."""
    t0 = time.monotonic()
    base = f"https://{host}:{port}"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(verify=False, timeout=_TIMEOUT) as client:
        try:
            cs = await client.post(f"{base}/cs", headers=headers, json={})
        except Exception as exc:  # noqa: BLE001
            _log(platform, f"/cs transport error: {exc}")
            return PlatformCheckResult(
                registered=None,
                status_raw="",
                identifier=identifier,
                http_status=-1,
                session_id=None,
                duration_s=time.monotonic() - t0,
                error=f"/cs failed: {exc}",
            )

        if cs.status_code != 200:
            return PlatformCheckResult(
                registered=None,
                status_raw="",
                identifier=identifier,
                http_status=cs.status_code,
                session_id=None,
                duration_s=time.monotonic() - t0,
                error=f"/cs HTTP {cs.status_code}",
            )

        # /cs can return either a bare UUID string or {"s": "<uuid>"}.
        session_id = _extract_session(cs.text)
        if not session_id:
            return PlatformCheckResult(
                registered=None,
                status_raw="",
                identifier=identifier,
                http_status=cs.status_code,
                session_id=None,
                duration_s=time.monotonic() - t0,
                error=f"/cs unparseable body: {cs.text[:80]!r}",
            )

        payload = {"s": session_id, "w": identifier, "p": proxy}
        try:
            h = await client.post(f"{base}/h", headers=headers, json=payload)
        except Exception as exc:  # noqa: BLE001
            return PlatformCheckResult(
                registered=None,
                status_raw="",
                identifier=identifier,
                http_status=-1,
                session_id=session_id,
                duration_s=time.monotonic() - t0,
                error=f"/h failed: {exc}",
            )

        status_raw = _extract_status(h.text)
        registered = _STATUS_MAP.get(status_raw.upper())
        data = _extract_data(h.text)
        return PlatformCheckResult(
            registered=registered,
            status_raw=status_raw,
            identifier=identifier,
            http_status=h.status_code,
            session_id=session_id,
            duration_s=time.monotonic() - t0,
            data=data,
        )


def _extract_session(body: str) -> str | None:
    body = body.strip()
    if not body:
        return None
    # JSON {"s": "..."} form
    if body.startswith("{"):
        try:
            import json

            data = json.loads(body)
            if isinstance(data, dict):
                s = data.get("s") or data.get("session")
                if isinstance(s, str):
                    return s
        except Exception:  # noqa: BLE001
            return None
        return None
    # Bare UUID form — strip quotes if present
    return body.strip('"').strip()


def _extract_status(body: str) -> str:
    body = body.strip()
    if body.startswith("{"):
        try:
            import json

            data = json.loads(body)
            if isinstance(data, dict):
                s = data.get("s") or data.get("status") or ""
                return str(s)
        except Exception:  # noqa: BLE001
            return ""
    return body.strip('"').strip()


def _extract_data(body: str) -> dict[str, Any] | None:
    body = body.strip()
    if body.startswith("{"):
        try:
            import json

            data = json.loads(body)
            if isinstance(data, dict):
                d = data.get("d")
                if isinstance(d, dict):
                    return d
        except Exception:  # noqa: BLE001
            return None
    return None


def build_module_result(
    *,
    module_name: str,
    platform_label: str,
    result: PlatformCheckResult,
) -> dict[str, Any]:
    """Shape a PlatformCheckResult into the common summary/signals/gaps/raw
    bundle used by every *_check module. Returned as a plain dict so each
    module can drop it straight into ModuleResult(**...).
    """
    from app.models import Signal  # local import to avoid cycle at import time

    raw = {
        "platform": platform_label,
        "identifier": result.identifier,
        "status_raw": result.status_raw,
        "http_status": result.http_status,
        "session_id": result.session_id,
        "error": result.error,
    }
    signals: list[Signal] = []
    gaps: list[str] = []

    if result.error:
        return {
            "status": "error",
            "summary": f"{platform_label} check failed: {result.error}",
            "signals": signals,
            "gaps": [result.error],
            "raw": raw,
        }

    if result.registered is True:
        signals.append(
            Signal(
                kind="contact",
                value=f"{platform_label} account registered to {result.identifier}",
                source=f"platform_check:{module_name}",
                confidence=0.8,
                notes=f"Upstream status: {result.status_raw}",
            )
        )
        return {
            "status": "ok",
            "summary": f"{result.identifier} is registered on {platform_label}.",
            "signals": signals,
            "gaps": gaps,
            "raw": raw,
        }

    if result.registered is False:
        return {
            "status": "ok",
            "summary": f"{result.identifier} is NOT registered on {platform_label}.",
            "signals": signals,
            "gaps": gaps,
            "raw": raw,
        }

    # Ambiguous / unknown status.
    gaps.append(
        f"{platform_label} returned ambiguous status {result.status_raw!r} "
        f"for {result.identifier}"
    )
    return {
        "status": "no_data",
        "summary": (
            f"{platform_label} check for {result.identifier} was inconclusive "
            f"(status: {result.status_raw or 'empty'})."
        ),
        "signals": signals,
        "gaps": gaps,
        "raw": raw,
    }
