"""Wallapop marketplace enrichment.

Searches Wallapop for active listings by the debtor's name near their known
address. Uses Playwright to bypass Wallapop's CloudFront WAF (direct HTTP
requests to api.wallapop.com return 403). Intercepts the /search/section
JSON response the web app receives.

Validates candidates with two signals:

  1. Location proximity — each listing carries lat/lon. We use the closest
     listing distance across all of a seller's items.

  2. Phone match — all listing descriptions are scanned for Spanish mobile
     numbers (6xx / 7xx). If a number is found:
       • Matches known phone  → confidence 0.92 (near-certain)
       • Different number     → confidence drops hard (×0.20 penalty)
       • No phone found       → location score unchanged

For candidates that pass the confidence threshold, seller reviews are fetched
from the V1 API using the user_id obtained from search results.
"""

from __future__ import annotations

import math
import re
import sys
from typing import Any

import httpx

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_WALLAPOP_V1_BASE = "https://api.wallapop.com/api/v1"
_TIMEOUT_S = 20

_PHONE_RE = re.compile(r"\b(?:\+34[\s\-]?)?[67]\d{8}\b")

_REVIEW_THRESHOLD = 0.35


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _normalize_phone(phone: str) -> str:
    p = re.sub(r"[\s\-\.\(\)]", "", phone)
    return re.sub(r"^\+34", "", p)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + (
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _location_score(min_km: float) -> float:
    if min_km < 2:
        return 0.25
    if min_km < 5:
        return 0.15
    if min_km < 10:
        return 0.08
    return 0.0


# ── V1 reviews ──────────────────────────────────────────────────────────────

async def _fetch_reviews(user_id: str) -> list[dict]:
    """Fetch reviews received by a seller via the V1 API (no WAF on V1)."""
    url = f"{_WALLAPOP_V1_BASE}/review.json/user/{user_id}/received"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            data = r.json()
            reviews = data.get("reviews") or data.get("data") or []
            return [
                {
                    "scoring": rv.get("scoring"),
                    "comments": (rv.get("comments") or "").strip(),
                    "date": rv.get("date"),
                    "is_shipping": rv.get("isShippingTransaction", False),
                }
                for rv in reviews
                if isinstance(rv, dict)
            ]
    except Exception as exc:
        _log(f"[wallapop] reviews fetch failed for user {user_id}: {exc}")
        return []


# ── Playwright search ────────────────────────────────────────────────────────

async def _search_via_playwright(
    name: str,
    lat: float | None,
    lon: float | None,
    distance_m: int,
) -> list[dict]:
    """Open Wallapop in a headless browser and intercept the search API response."""
    from playwright.async_api import async_playwright
    import asyncio

    items: list[dict] = []
    url = f"https://es.wallapop.com/app/search?keywords={name.replace(' ', '+')}"
    if lat is not None and lon is not None:
        url += f"&latitude={lat}&longitude={lon}&distance={distance_m}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        async def on_response(response):
            if "/search/section" in response.url:
                try:
                    body = await response.json()
                    section = (body.get("data") or {}).get("section") or {}
                    items.extend(section.get("items") or [])
                    _log(f"[wallapop] intercepted {len(section.get('items', []))} items")
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=25_000)
            await asyncio.sleep(2)
        except Exception as exc:
            _log(f"[wallapop] Playwright navigation error: {exc}")
        finally:
            await browser.close()

    return items


# ── Public API ───────────────────────────────────────────────────────────────

async def geocode_address(address: str, user_agent: str) -> tuple[float, float] | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                _NOMINATIM_URL,
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": user_agent},
            )
            data = r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as exc:
        _log(f"[wallapop] geocode failed: {exc}")
    return None


async def search_wallapop(
    name: str,
    lat: float | None = None,
    lon: float | None = None,
    phone: str | None = None,
    distance_m: int = 15_000,
) -> dict[str, Any]:
    """Search Wallapop via Playwright and score candidate sellers.

    Scoring per candidate:
      • Base = location_score(min distance across their listings)
      • Phone match → overrides to 0.92
      • Different phone found → base × 0.20
      • No phone → base unchanged

    Reviews fetched from V1 API for candidates above threshold.

    Returns:
        {
            "matches": [
                {
                    "seller":   {user_id, profile_url},
                    "items":    [{title, description, price_eur, url, location}],
                    "phones":   [str],
                    "reviews":  [{scoring, comments, date, is_shipping}],
                    "min_km":   float | None,
                    "score":    float,
                    "evidence": [str],
                }
            ],
            "errors": [str],
        }
    """
    normalized_phone = _normalize_phone(phone) if phone else None

    raw_items = await _search_via_playwright(name, lat, lon, distance_m)
    _log(f"[wallapop] {len(raw_items)} total items for '{name}'")

    if not raw_items:
        return {"matches": [], "errors": []}

    # Group by user_id
    sellers: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        uid = item.get("user_id", "")
        if not uid:
            continue
        if uid not in sellers:
            sellers[uid] = {
                "user_id": uid,
                "profile_url": f"https://es.wallapop.com/app/user/{uid}/published",
                "items": [],
            }
        loc = item.get("location") or {}
        sellers[uid]["items"].append({
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "price_eur": (item.get("price") or {}).get("amount"),
            "url": f"https://es.wallapop.com/item/{item.get('web_slug') or item.get('id', '')}",
            "location": {
                "city": loc.get("city"),
                "postal_code": loc.get("postal_code"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
            },
        })

    matches = []
    for seller in sellers.values():
        evidence: list[str] = []

        # Location: minimum distance across all listings
        min_km: float | None = None
        if lat is not None and lon is not None:
            distances = [
                _haversine_km(lat, lon, i["location"]["latitude"], i["location"]["longitude"])
                for i in seller["items"]
                if i["location"]["latitude"] is not None and i["location"]["longitude"] is not None
            ]
            if distances:
                min_km = min(distances)

        loc_score = _location_score(min_km) if min_km is not None else 0.0
        if min_km is not None:
            evidence.append(f"closest listing {min_km:.1f}km from known address")

        # Phone: scan every listing description
        all_text = " ".join(i["title"] + " " + i["description"] for i in seller["items"])
        phones_found = list({_normalize_phone(p) for p in _PHONE_RE.findall(all_text)})

        if phones_found:
            if normalized_phone and normalized_phone in phones_found:
                score = 0.92
                evidence.append(f"phone {phone} confirmed in listing description")
            else:
                score = round(loc_score * 0.20, 2)
                evidence.append(
                    f"different phone(s) in listings: {', '.join(phones_found)}"
                )
        else:
            score = loc_score

        matches.append({
            "seller": {
                "user_id": seller["user_id"],
                "profile_url": seller["profile_url"],
            },
            "items": seller["items"],
            "phones": phones_found,
            "reviews": [],
            "min_km": round(min_km, 2) if min_km is not None else None,
            "score": round(score, 2),
            "evidence": evidence,
        })

    matches.sort(key=lambda m: m["score"], reverse=True)

    # Fetch reviews for candidates that pass the threshold
    import asyncio
    review_tasks = [
        _fetch_reviews(m["seller"]["user_id"])
        for m in matches
        if m["score"] >= _REVIEW_THRESHOLD
    ]
    if review_tasks:
        results = await asyncio.gather(*review_tasks, return_exceptions=True)
        idx = 0
        for m in matches:
            if m["score"] >= _REVIEW_THRESHOLD:
                rv = results[idx]
                m["reviews"] = rv if isinstance(rv, list) else []
                idx += 1
                if m["reviews"]:
                    _log(f"[wallapop] {len(m['reviews'])} review(s) for user {m['seller']['user_id']}")

    return {"matches": matches, "errors": []}
