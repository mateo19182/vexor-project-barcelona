"""Google Maps reviews enricher.

Scrapes all public reviews left by a Google account holder given their Gaia ID.

Returns a structured list of reviews — each with place name, rating, text,
relative time, and source URL — ready to be consumed by the pipeline module.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_MAPS_CONTRIB = "https://www.google.com/maps/contrib/{gaia_id}/reviews"


class Review(BaseModel):
    place: str
    rating: str        # "4" / "5" etc., empty if not found
    text: str
    time_ago: str      # "hace 3 meses", "2 months ago", etc.
    place_url: str     # Google Maps URL of the reviewed place
    source_url: str    # Contributor review page URL


class ReviewsEnrichment(BaseModel):
    gaia_id: str
    profile_url: str
    name: str = ""
    profile_pic_url: str = ""
    reviews: list[Review] = []
    total_found: int = 0
    gaps: list[str] = []


async def fetch_reviews(
    gaia_id: str,
    cookies: dict[str, str],
) -> ReviewsEnrichment:
    """Fetch and parse all public Google Maps reviews for the given Gaia ID."""
    profile_url = _MAPS_CONTRIB.format(gaia_id=gaia_id)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ReviewsEnrichment(
            gaia_id=gaia_id,
            profile_url=profile_url,
            gaps=["playwright not installed — run: uv add playwright && uv run playwright install chromium"],
        )

    _log(f"[google_maps_reviews] scraping {profile_url}")

    try:
        html = await _render_page(profile_url, cookies)
    except Exception as e:  # noqa: BLE001
        return ReviewsEnrichment(
            gaia_id=gaia_id,
            profile_url=profile_url,
            gaps=[f"Page render failed: {e}"],
        )

    reviews = _parse(html, profile_url)
    name, profile_pic_url = _parse_profile(html)
    _log(f"[google_maps_reviews] found {len(reviews)} review(s) — name={name!r}")

    return ReviewsEnrichment(
        gaia_id=gaia_id,
        profile_url=profile_url,
        name=name,
        profile_pic_url=profile_pic_url,
        reviews=reviews,
        total_found=len(reviews),
        gaps=[] if reviews else ["No public reviews found on the contributor page"],
    )


async def _render_page(url: str, cookies: dict[str, str]) -> str:
    """Open the Maps contributor page in a headless browser and return HTML."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_UA)

        # Inject Google session cookies so the page loads as authenticated
        await context.add_cookies([
            {
                "name": k,
                "value": v,
                "domain": ".google.com",
                "path": "/",
                "sameSite": "None",
                "secure": True,
            }
            for k, v in cookies.items()
            if v
        ])

        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3_000)

        # Dismiss Google consent screen if it appears
        if "consent.google.com" in page.url or "Antes de ir" in await page.title():
            _log("[google_maps_reviews] consent screen detected — accepting")
            try:
                accept = page.locator(
                    "button:has-text('Aceptar todo'), "
                    "button:has-text('Accept all'), "
                    "button:has-text('Accepter tout'), "
                    "form[action*='consent.google.com/save'] button"
                ).first
                await accept.click()
                await page.wait_for_timeout(3_000)
            except Exception as e:  # noqa: BLE001
                _log(f"[google_maps_reviews] could not dismiss consent: {e}")

        # Scroll down to trigger lazy-loaded review cards
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(1_000)

        html = await page.content()
        await browser.close()

    return html


def _parse(html: str, source_url: str) -> list[Review]:
    """Parse review cards from the rendered HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _log("[google_maps_reviews] beautifulsoup4 not installed")
        return []

    soup = BeautifulSoup(html, "html.parser")

    # Select only the outer card (role=button) — the inner div also has
    # data-review-id and would duplicate every review.
    blocks = soup.select("div[data-review-id][role='button']")

    # Fallback: any data-review-id block
    if not blocks:
        blocks = soup.select("div[data-review-id]")

    _log(f"[google_maps_reviews] found {len(blocks)} raw block(s) in HTML")

    reviews: list[Review] = []
    for block in blocks[:50]:
        review = _parse_block(block, source_url)
        if review:
            reviews.append(review)

    return reviews


def _parse_block(block: Any, source_url: str) -> Review | None:
    """Extract structured data from a single review card.

    Selectors validated against the HTML structure returned by Google Maps
    contributor pages (April 2025).
    """
    # Place name — .d4r55 is the title div inside each card
    place_el = block.select_one(".d4r55, .fontTitleSmall")
    place = place_el.get_text(strip=True) if place_el else ""

    # Place URL — card itself is a button; look for an <a> with /maps/place/
    place_url = ""
    place_link = block.select_one("a[href*='/maps/place/'], a[data-href*='/maps/place/']")
    if place_link:
        href = place_link.get("href") or place_link.get("data-href") or ""
        place_url = href if href.startswith("http") else f"https://www.google.com{href}"

    # Star rating — aria-label="5 estrellas" on .kvMYJc span
    rating = ""
    rating_el = block.select_one(".kvMYJc[aria-label]")
    if rating_el:
        aria = rating_el.get("aria-label", "") or ""
        parts = aria.strip().split()
        if parts and parts[0].isdigit():
            rating = parts[0]

    # Review text — .wiI7pd is the inner span with the actual text
    text_el = block.select_one(".wiI7pd, .MyEned span")
    text = text_el.get_text(strip=True) if text_el else ""

    # Relative time — .rsqaWe holds "Hace 8 años", "2 months ago", etc.
    time_el = block.select_one(".rsqaWe")
    time_ago = time_el.get_text(strip=True) if time_el else ""

    if not place and not text:
        return None

    return Review(
        place=place,
        rating=rating,
        text=text,
        time_ago=time_ago,
        place_url=place_url,
        source_url=source_url,
    )


def _parse_profile(html: str) -> tuple[str, str]:
    """Extract the contributor's display name and profile picture URL.

    Returns (name, profile_pic_url). Empty strings if not found.

    Selectors validated against Google Maps contributor pages (April 2025):
      - Name:  button.fontHeadlineLarge inside .BZZkgb (next to profile pic)
      - Photo: img[alt='Foto de perfil'] / img[alt='Profile photo'] inside .Gmmhvf
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "", ""

    soup = BeautifulSoup(html, "html.parser")

    # Profile picture — Google Maps uses a consistent alt text across locales
    pic_url = ""
    pic_el = soup.find(
        "img",
        alt=lambda a: a and any(
            kw in a.lower() for kw in ("foto de perfil", "profile photo", "profile picture", "profilbild")
        ),
    )
    if pic_el:
        src = pic_el.get("src", "") or ""
        # Upgrade to a larger resolution by replacing the size suffix
        if "=w" in src:
            pic_url = src.split("=w")[0] + "=w400-h400-p-rp-mo-br100"
        else:
            pic_url = src

    # Display name — .fontHeadlineLarge button sits next to the profile pic
    name = ""
    name_el = soup.select_one(".fontHeadlineLarge")
    if name_el:
        name = name_el.get_text(strip=True)

    return name, pic_url
