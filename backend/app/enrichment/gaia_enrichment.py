"""GAIA enrichment — Google account public intelligence.

Given a Gaia ID, fetches:
  - Display name + profile picture
  - Contributor stats via Google's internal locationhistory API (GHunt technique)
  - Public Google Maps reviews via Playwright
  - Public photos uploaded to Google Maps via Playwright (CSS background-image extraction)

Stats use a direct httpx call — no Playwright needed.
Photos require Playwright because Maps renders them as CSS background-images, not <img> tags.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import httpx
from pydantic import BaseModel, Field


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_MAPS_REVIEWS = "https://www.google.com/maps/contrib/{gaia_id}/reviews"
_MAPS_PHOTOS  = "https://www.google.com/maps/contrib/{gaia_id}/photos"

# GHunt's protobuf template for the stats endpoint.
# {} is replaced with the gaia_id. Response is JSON with a 5-char prefix to strip.
_STATS_PB = (
    "!1s{}!2m3!1sYE3rYc2rEsqOlwSHx534DA!7e81!15i14416!6m2!4b1!7b1!9m0"
    "!16m4!1i100!4b1!5b1!6BQ0FFU0JrVm5TVWxEenc9PQ"
    "!17m28!1m6!1m2!1i0!2i0!2m2!1i458!2i736!1m6!1m2!1i1868!2i0!2m2!1i1918!2i736"
    "!1m6!1m2!1i0!2i0!2m2!1i1918!2i20!1m6!1m2!1i0!2i716!2m2!1i1918!2i736"
    "!18m12!1m3!1d806313.5865720833!2d150.19484835!3d-34.53825215"
    "!2m3!1f0!2f0!3f0!3m2!1i1918!2i736!4f13.1"
)
_STATS_URL = "https://www.google.com/locationhistory/preview/mas"


# ─── Data models ─────────────────────────────────────────────────────────────

class Review(BaseModel):
    place: str
    rating: str       # "4" / "5" etc., empty if not found
    text: str
    time_ago: str     # "hace 3 meses", "2 months ago", etc.
    place_url: str
    source_url: str


class ContributorPhoto(BaseModel):
    url: str
    place_name: str = ""


class ContributorStats(BaseModel):
    reviews_count: int = 0
    ratings_count: int = 0   # star ratings without text
    photos_count: int = 0
    local_guides_level: int = 0


class GaiaEnrichment(BaseModel):
    gaia_id: str
    profile_url: str
    name: str = ""
    profile_pic_url: str = ""
    stats: ContributorStats = Field(default_factory=ContributorStats)
    reviews: list[Review] = []
    photos: list[ContributorPhoto] = []
    total_reviews: int = 0
    gaps: list[str] = []


# ─── Public entry point ───────────────────────────────────────────────────────

async def fetch_gaia(
    gaia_id: str,
    cookies: dict[str, str],
) -> GaiaEnrichment:
    """Fetch all public GAIA intel for the given Gaia ID."""
    profile_url = _MAPS_REVIEWS.format(gaia_id=gaia_id)

    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return GaiaEnrichment(
            gaia_id=gaia_id,
            profile_url=profile_url,
            gaps=["playwright not installed — run: uv add playwright && uv run playwright install chromium"],
        )

    gaps: list[str] = []

    # ── Stats — direct API call (GHunt technique, no Playwright) ──────────
    _log(f"[gaia_enrichment] fetching stats for {gaia_id}")
    stats, stats_gap = await _fetch_stats(gaia_id, cookies)
    if stats_gap:
        gaps.append(stats_gap)

    # ── Reviews page — Playwright ─────────────────────────────────────────
    _log(f"[gaia_enrichment] fetching reviews page for {gaia_id}")
    try:
        reviews_html = await _render_page(profile_url, cookies, scrolls=6)
    except Exception as e:  # noqa: BLE001
        return GaiaEnrichment(
            gaia_id=gaia_id,
            profile_url=profile_url,
            stats=stats,
            gaps=[f"Reviews page render failed: {e}"] + gaps,
        )

    name, profile_pic_url = _parse_profile(reviews_html)
    # Local Guides level is only in the HTML, not the stats API
    level = _parse_local_guides_level(reviews_html)
    if level:
        stats.local_guides_level = level
    reviews = _parse_reviews(reviews_html, profile_url)
    _log(f"[gaia_enrichment] name={name!r}  stats={stats}  reviews={len(reviews)}")

    # ── Photos page — Playwright + JS background-image extraction ─────────
    photos_url = _MAPS_PHOTOS.format(gaia_id=gaia_id)
    _log(f"[gaia_enrichment] fetching photos page for {gaia_id}")
    try:
        photos = await _fetch_photos_playwright(photos_url, cookies)
        _log(f"[gaia_enrichment] found {len(photos)} photo(s)")
    except Exception as e:  # noqa: BLE001
        photos = []
        gaps.append(f"Photos page render failed: {e}")

    if not reviews:
        gaps.append("No public reviews found on the contributor page")
    if not photos:
        gaps.append("No public photos found on the contributor page")

    return GaiaEnrichment(
        gaia_id=gaia_id,
        profile_url=profile_url,
        name=name,
        profile_pic_url=profile_pic_url,
        stats=stats,
        reviews=reviews,
        photos=photos,
        total_reviews=len(reviews),
        gaps=gaps,
    )


# ─── Stats via internal API (GHunt technique) ────────────────────────────────

async def _fetch_stats(
    gaia_id: str,
    cookies: dict[str, str],
) -> tuple[ContributorStats, str]:
    """Fetch contributor stats from Google's internal locationhistory API.

    Returns (stats, error_message). error_message is empty on success.

    Response format (after stripping 5-char prefix):
      data[16][8][0] → list of [?, ?, ?, ?, ?, ?, name, count, ...]
      Keys: "Reviews", "Ratings", "Photos"
    """
    stats = ContributorStats()
    try:
        async with httpx.AsyncClient(
            cookies=cookies,
            headers={"User-Agent": _UA},
            follow_redirects=False,
            timeout=15.0,
        ) as client:
            resp = await client.get(
                _STATS_URL,
                params={"authuser": "0", "hl": "en", "gl": "us", "pb": _STATS_PB.format(gaia_id)},
            )

        if resp.status_code == 302:
            loc = resp.headers.get("location", "")
            if "sorry/index" in loc:
                return stats, "Stats API: IP blocked by Google (rate limited)"
            return stats, f"Stats API: unexpected redirect to {loc}"

        if resp.status_code != 200:
            return stats, f"Stats API: HTTP {resp.status_code}"

        data = json.loads(resp.text[5:])

        if not data[16] or not data[16][8]:
            return stats, "Stats API: no stats returned (profile may be empty or private)"

        raw_stats: dict[str, int] = {sec[6]: sec[7] for sec in data[16][8][0]}
        _log(f"[gaia_enrichment] raw stats from API: {raw_stats}")

        stats.reviews_count = raw_stats.get("Reviews", 0)
        stats.ratings_count = raw_stats.get("Ratings", 0)
        stats.photos_count  = raw_stats.get("Photos", 0)
        return stats, ""

    except Exception as e:  # noqa: BLE001
        return stats, f"Stats API error: {e}"


# ─── Playwright renderer ──────────────────────────────────────────────────────

async def _render_page(url: str, cookies: dict[str, str], scrolls: int = 6) -> str:
    """Open a Maps contributor page in headless Chromium and return HTML."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_UA)

        await context.add_cookies([
            {"name": k, "value": v, "domain": ".google.com", "path": "/",
             "sameSite": "None", "secure": True}
            for k, v in cookies.items() if v
        ])

        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3_000)

        if "consent.google.com" in page.url or "Antes de ir" in await page.title():
            _log("[gaia_enrichment] consent screen — accepting")
            try:
                await page.locator(
                    "button:has-text('Aceptar todo'), "
                    "button:has-text('Accept all'), "
                    "button:has-text('Accepter tout'), "
                    "form[action*='consent.google.com/save'] button"
                ).first.click()
                await page.wait_for_timeout(3_000)
            except Exception as e:  # noqa: BLE001
                _log(f"[gaia_enrichment] could not dismiss consent: {e}")

        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)

        html = await page.content()
        await browser.close()

    return html


async def _fetch_photos_playwright(
    photos_url: str,
    cookies: dict[str, str],
) -> list[ContributorPhoto]:
    """Fetch contributor photos page and extract URLs via JavaScript.

    Google Maps renders contributor photos as CSS background-image on divs,
    not as <img> tags — so BeautifulSoup img-parsing yields nothing.
    We use page.evaluate() to read computed styles directly in the browser.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_UA)

        await context.add_cookies([
            {"name": k, "value": v, "domain": ".google.com", "path": "/",
             "sameSite": "None", "secure": True}
            for k, v in cookies.items() if v
        ])

        page = await context.new_page()
        await page.goto(photos_url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3_000)

        if "consent.google.com" in page.url or "Antes de ir" in await page.title():
            _log("[gaia_enrichment] consent screen on photos page — accepting")
            try:
                await page.locator(
                    "button:has-text('Aceptar todo'), "
                    "button:has-text('Accept all'), "
                    "button:has-text('Accepter tout'), "
                    "form[action*='consent.google.com/save'] button"
                ).first.click()
                await page.wait_for_timeout(3_000)
            except Exception:  # noqa: BLE001
                pass

        # Scroll aggressively to trigger lazy loading
        for _ in range(12):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(600)

        # Extract all googleusercontent URLs from:
        #   1. <img src="..."> and <img data-src="...">
        #   2. CSS background-image on any element
        #   3. inline style attributes
        raw_urls: list[dict] = await page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();

                function add(url, label) {
                    if (!url || seen.has(url)) return;
                    seen.add(url);
                    results.push({ url, label });
                }

                // <img> tags
                for (const img of document.querySelectorAll('img')) {
                    const src = img.src || img.getAttribute('data-src') || '';
                    if (src.includes('googleusercontent')) add(src, img.alt || '');
                }

                // CSS background-image (computed style)
                for (const el of document.querySelectorAll('*')) {
                    const bg = getComputedStyle(el).backgroundImage;
                    if (bg && bg.includes('googleusercontent')) {
                        const m = bg.match(/url[(]["']?([^"')]+)["']?[)]/);  // eslint-disable-line
                        if (m) {
                            const label = el.getAttribute('aria-label') || '';
                            add(m[1], label);
                        }
                    }
                }

                // Inline style background-image (catches server-rendered HTML)
                for (const el of document.querySelectorAll('[style*="googleusercontent"]')) {
                    const m = el.style.backgroundImage.match(/url[(]["']?([^"')]+)["']?[)]/);
                    if (m) add(m[1], el.getAttribute('aria-label') || '');
                }

                return results;
            }
        """)

        await browser.close()

    photos: list[ContributorPhoto] = []
    seen_base: set[str] = set()

    for item in raw_urls:
        url: str = item.get("url", "")
        label: str = item.get("label", "")

        # Skip profile avatars (/a/ path) and tiny icons
        if "/a/" in url:
            continue
        if re.search(r"=s\d{1,2}$", url):  # =s32, =s40 etc. — tiny icons
            continue

        # Strip size params to get highest resolution
        base = re.sub(r"=[^/]+$", "", url)
        if not base or base in seen_base:
            continue
        seen_base.add(base)

        place_name = label if label.lower() not in ("", "photo", "foto") else ""
        photos.append(ContributorPhoto(url=base, place_name=place_name))

    return photos[:60]


# ─── HTML parsers ─────────────────────────────────────────────────────────────

def _parse_profile(html: str) -> tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "", ""

    soup = BeautifulSoup(html, "html.parser")

    pic_url = ""
    pic_el = soup.find(
        "img",
        alt=lambda a: a and any(
            kw in a.lower()
            for kw in ("foto de perfil", "profile photo", "profile picture", "profilbild")
        ),
    )
    if pic_el:
        pic_url = pic_el.get("src", "") or ""

    name = ""
    name_el = soup.select_one(".fontHeadlineLarge")
    if name_el:
        name = name_el.get_text(strip=True)

    return name, pic_url


def _parse_local_guides_level(html: str) -> int:
    """Extract Local Guides level from page text (not available via API)."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        body = soup.get_text(" ")
    except ImportError:
        body = html

    m = re.search(
        r'(?:nivel|level|niveau|stufe|poziom)\s*[·•\-]?\s*(\d+)',
        body,
        re.IGNORECASE,
    )
    return int(m.group(1)) if m else 0


def _parse_reviews(html: str, source_url: str) -> list[Review]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _log("[gaia_enrichment] beautifulsoup4 not installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div[data-review-id][role='button']") or soup.select("div[data-review-id]")
    _log(f"[gaia_enrichment] found {len(blocks)} raw review block(s)")

    reviews: list[Review] = []
    for block in blocks[:50]:
        rev = _parse_review_block(block, source_url)
        if rev:
            reviews.append(rev)
    return reviews


def _parse_review_block(block: Any, source_url: str) -> Review | None:
    place_el = block.select_one(".d4r55, .fontTitleSmall")
    place = place_el.get_text(strip=True) if place_el else ""

    place_url = ""
    place_link = block.select_one("a[href*='/maps/place/'], a[data-href*='/maps/place/']")
    if place_link:
        href = place_link.get("href") or place_link.get("data-href") or ""
        place_url = href if href.startswith("http") else f"https://www.google.com{href}"

    rating = ""
    rating_el = block.select_one(".kvMYJc[aria-label]")
    if rating_el:
        parts = (rating_el.get("aria-label", "") or "").strip().split()
        if parts and parts[0].isdigit():
            rating = parts[0]

    text_el = block.select_one(".wiI7pd, .MyEned span")
    text = text_el.get_text(strip=True) if text_el else ""

    time_el = block.select_one(".rsqaWe")
    time_ago = time_el.get_text(strip=True) if time_el else ""

    if not place and not text:
        return None

    return Review(
        place=place, rating=rating, text=text,
        time_ago=time_ago, place_url=place_url, source_url=source_url,
    )
