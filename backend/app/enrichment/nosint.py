"""NoSINT enricher — streams SSE results from the NoSINT CSINT platform.

API: GET https://nosint.org/api/v1/search?target=EMAIL&module_target=email
Auth: Authorization: Bearer <api_key>
Protocol: Server-Sent Events (text/event-stream)

Each SSE event is a JSON object. Three shapes:
  start:   {"search_id": "...", "status": "started", "total_modules": N}
  result:  {"search_id": "...", "module_name": "...", "target_url": "...",
             "is_valid": bool, "result": {...}, "cached": bool, ...}
  done:    {"done": true}
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import httpx
from pydantic import BaseModel

_BASE = "https://nosint.org/api/v1"
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class NosintResult(BaseModel):
    email: str
    search_id: str | None = None
    total_modules: int = 0
    hits: list[dict[str, Any]] = []       # is_valid=True results only
    all_results: list[dict[str, Any]] = []  # every module result received
    gaps: list[str] = []
    duration_s: float = 0.0


async def enrich_nosint(email: str, api_key: str) -> NosintResult:
    """Stream the NoSINT search for *email* and collect all module results."""
    t0 = time.monotonic()
    url = f"{_BASE}/search"
    params = {"target": email, "module_target": "email"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "User-Agent": _UA,
    }

    search_id: str | None = None
    total_modules: int = 0
    all_results: list[dict[str, Any]] = []
    gaps: list[str] = []

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", url, params=params, headers=headers, timeout=_TIMEOUT
            ) as response:
                if response.status_code == 401:
                    gaps.append("NoSINT: invalid or missing API key (401)")
                    return NosintResult(email=email, gaps=gaps, duration_s=time.monotonic() - t0)
                if response.status_code == 400:
                    gaps.append("NoSINT: bad request — check target/module_target params (400)")
                    return NosintResult(email=email, gaps=gaps, duration_s=time.monotonic() - t0)
                if response.status_code != 200:
                    gaps.append(f"NoSINT: unexpected HTTP {response.status_code}")
                    return NosintResult(email=email, gaps=gaps, duration_s=time.monotonic() - t0)

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue

                    payload_str = line[len("data:"):].strip()
                    if not payload_str:
                        continue

                    try:
                        event = json.loads(payload_str)
                    except json.JSONDecodeError as exc:
                        _log(f"[nosint] JSON parse error: {exc} — line: {payload_str[:120]}")
                        continue

                    # Done signal — stop reading
                    if event.get("done"):
                        _log(f"[nosint] stream complete ({len(all_results)} module results)")
                        break

                    # Start event
                    if event.get("status") == "started":
                        search_id = event.get("search_id")
                        total_modules = event.get("total_modules", 0)
                        _log(f"[nosint] search {search_id} started — {total_modules} modules")
                        continue

                    # Module result event
                    if "module_name" in event:
                        all_results.append(event)

    except httpx.TimeoutException:
        gaps.append("NoSINT: request timed out (>120 s)")
        _log("[nosint] timeout")
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"NoSINT: unexpected error — {exc}")
        _log(f"[nosint] error: {exc}")

    hits = [r for r in all_results if r.get("is_valid")]
    _log(f"[nosint] {len(hits)}/{len(all_results)} modules returned valid data")

    return NosintResult(
        email=email,
        search_id=search_id,
        total_modules=total_modules,
        hits=hits,
        all_results=all_results,
        gaps=gaps,
        duration_s=time.monotonic() - t0,
    )
