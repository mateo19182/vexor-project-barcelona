"""Google Maps reviews module.

Extracts public Google Maps reviews left by a Gmail account holder.

Flow:
  1. Load Google session cookies from GOOGLE_SESSION_COOKIES in .env.
  2. Resolve the Gmail address → Gaia ID via Google's internal people-lookup
     endpoint (technique adapted from GHunt: https://github.com/mxrch/GHunt).
  3. Scrape the contributor review page with Playwright.

Setup — copy these cookies from Chrome DevTools (F12 → Application → Cookies
→ google.com) and paste them as a JSON dict in .env:
  GOOGLE_SESSION_COOKIES={"SID":"...","SSID":"...","APISID":"...","SAPISID":"...","__Secure-1PAPISID":"...","NID":"..."}
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from typing import Any

import httpx

from app.config import settings
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

_PEOPLE_URL = "https://people-pa.clients6.google.com/v2/people/lookup"
_MAPS_CONTRIB = "https://www.google.com/maps/contrib/{gaia_id}/reviews"
_AUTH_ORIGIN = "https://people-pa.clients6.google.com"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_cookies() -> dict[str, str] | None:
    """Parse GOOGLE_SESSION_COOKIES from .env (JSON dict or Playwright list)."""
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
        _log(f"[google_maps] cannot parse GOOGLE_SESSION_COOKIES: {e}")
    return None


def _sapisid_hash(sapisid: str, origin: str) -> str:
    ts = int(time.time())
    digest = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    return f"{ts}_{digest}"


async def _get_gaia_id(email: str, cookies: dict[str, str]) -> str | None:
    """Gmail → Gaia ID via Google's internal People API (GHunt technique)."""
    sapisid = cookies.get("__Secure-1PAPISID") or cookies.get("SAPISID") or ""
    if not sapisid:
        _log("[google_maps] no SAPISID cookie found")
        return None

    headers = {
        "Authorization": f"SAPISIDHASH {_sapisid_hash(sapisid, _AUTH_ORIGIN)}",
        "X-Goog-AuthUser": "0",
        "X-Origin": _AUTH_ORIGIN,
        "User-Agent": _UA,
        "Accept": "application/json",
    }
    params = {
        "id": email,
        "type": "EMAIL",
        "match_type": "EXACT",
        "field_mask": "person.metadata",
        "core_id_params.include_in_directory_people": "true",
    }

    try:
        async with httpx.AsyncClient(cookies=cookies, timeout=15.0) as client:
            resp = await client.get(_PEOPLE_URL, params=params, headers=headers)
        _log(f"[google_maps] people-lookup HTTP {resp.status_code}")

        if resp.status_code != 200:
            _log(f"[google_maps] response: {resp.text[:400]}")
            return None

        data = resp.json()
        people = data.get("people") or []
        if isinstance(people, list) and people:
            person_id = people[0].get("personId")
            if person_id:
                _log(f"[google_maps] Gaia ID → {person_id}")
                return str(person_id)

        _log(f"[google_maps] unexpected shape: {json.dumps(data)[:300]}")
        return None

    except Exception as e:  # noqa: BLE001
        _log(f"[google_maps] people-lookup error: {e}")
        return None


async def _scrape_reviews(
    gaia_id: str, cookies: dict[str, str]
) -> list[dict[str, Any]]:
    """Scrape Google Maps contributor review page with Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        _log("[google_maps] playwright not installed — run: uv add playwright && uv run playwright install chromium")
        return []

    url = _MAPS_CONTRIB.format(gaia_id=gaia_id)
    _log(f"[google_maps] scraping → {url}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=_UA)
            await context.add_cookies([
                {"name": k, "value": v, "domain": ".google.com", "path": "/", "sameSite": "None", "secure": True}
                for k, v in cookies.items() if v
            ])
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30_000)

            for _ in range(4):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(1_200)

            content = await page.content()
            await browser.close()

        return _parse_reviews(content, url)

    except Exception as e:  # noqa: BLE001
        _log(f"[google_maps] scraping error: {e}")
        return []


def _parse_reviews(html: str, source_url: str) -> list[dict[str, Any]]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _log("[google_maps] beautifulsoup4 not installed — run: uv add beautifulsoup4")
        return []

    soup = BeautifulSoup(html, "html.parser")
    blocks = (
        soup.select("div[data-review-id]")
        or soup.select(".ODSEW-ShBeI-content, .Svr5cf, .GHT2ce")
        or soup.select("section[aria-label]")
    )

    reviews: list[dict[str, Any]] = []
    for block in blocks[:25]:
        text_el = block.select_one(".MyEned, .ODSEW-ShBeI-RgZmSc-ibnC6b, .Jtu6Td, .wiI7pd")
        rating_el = block.select_one("[aria-label*='star'], [aria-label*='estrella'], .kvMYJc")
        business_el = block.select_one(".ODSEW-ShBeI-title, .lcr4fd, .jftiEf, a[href*='/maps/place/']")
        date_el = block.select_one(".ODSEW-ShBeI-RgZmSc, .dehysf, .rsqaWe")

        text = text_el.get_text(strip=True) if text_el else ""
        rating = (rating_el.get("aria-label", "") or "").split()[0] if rating_el else ""
        business = business_el.get_text(strip=True) if business_el else ""
        date = date_el.get_text(strip=True) if date_el else ""

        if text or business:
            reviews.append({"text": text, "rating": rating, "business": business, "date": date, "source": source_url})

    _log(f"[google_maps] parsed {len(reviews)} review(s)")
    return reviews


class GoogleMapsModule:
    name = "google_maps"
    requires: tuple[str, ...] = ("email",)

    async def run(self, ctx: Context) -> ModuleResult:
        cookies = _load_cookies()
        if cookies is None:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=[
                    "GOOGLE_SESSION_COOKIES not set. "
                    "Copy from Chrome DevTools → Application → Cookies → google.com "
                    "and paste as JSON in .env: GOOGLE_SESSION_COOKIES={\"SID\":\"...\", ...}"
                ],
            )

        email = ctx.email or ""
        _log(f"[google_maps] resolving {email}")

        gaia_id = await _get_gaia_id(email, cookies)
        if not gaia_id:
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=[f"Could not resolve Gaia ID for {email}. Cookies may be expired."],
                raw={"email": email},
            )

        maps_url = _MAPS_CONTRIB.format(gaia_id=gaia_id)
        raw_reviews = await _scrape_reviews(gaia_id, cookies)

        if not raw_reviews:
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=f"Resolved Gaia ID {gaia_id} for {email} but found no public Maps reviews.",
                gaps=["No public reviews on Google Maps contributor page"],
                raw={"gaia_id": gaia_id, "maps_url": maps_url, "reviews": []},
            )

        signals: list[Signal] = []
        facts: list[Fact] = []

        for rev in raw_reviews:
            text = rev.get("text", "").strip()
            business = rev.get("business", "").strip()
            rating = rev.get("rating", "").strip()
            date = rev.get("date", "").strip()
            source = rev.get("source", maps_url)

            if business:
                label = business
                if rating:
                    label += f" ({rating}★)"
                if date:
                    label += f" — {date}"
                signals.append(Signal(
                    kind="lifestyle",
                    value=f"Google Maps review: {label}",
                    source=source,
                    confidence=0.85,
                    notes=text[:250] if text else None,
                ))
            elif text:
                facts.append(Fact(
                    claim=f"Google Maps review: {text[:350]}",
                    source=source,
                    confidence=0.80,
                ))

        reviewed_places = [r["business"] for r in raw_reviews if r.get("business")]
        summary = f"Found {len(raw_reviews)} public Google Maps review(s) for {email} (Gaia ID: {gaia_id})."
        if reviewed_places:
            summary += f" Reviewed: {', '.join(reviewed_places[:6])}."

        _log(f"[google_maps] done: {len(signals)} signal(s), {len(facts)} fact(s)")

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=signals,
            facts=facts,
            gaps=[],
            raw={"gaia_id": gaia_id, "maps_url": maps_url, "reviews": raw_reviews},
        )
