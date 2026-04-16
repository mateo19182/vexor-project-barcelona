"""GAIA enrichment module.

Input  -> contact:gaia_id signal
Output -> contributor stats, public reviews, public photos + lifestyle signals

Runs in wave 2+ — after google_id emits the gaia_id signal.
"""

from __future__ import annotations

import json
import sys

from app.config import settings
from app.enrichment.gaia_enrichment import fetch_gaia
from app.enrichment.image_store import download_image, get_photos_dir
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult


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
        _log(f"[gaia_enrichment] cannot parse GOOGLE_SESSION_COOKIES: {e}")
    return None


class GaiaEnrichmentModule:
    name = "gaia_enrichment"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "gaia_id"),)

    async def run(self, ctx: Context) -> ModuleResult:
        gaia_sig = ctx.best("contact", "gaia_id")
        gaia_id = gaia_sig.value if gaia_sig else ""

        cookies = _load_cookies() or {}

        _log(f"[gaia_enrichment] running for gaia_id={gaia_id}")
        enrichment = await fetch_gaia(gaia_id, cookies)

        signals: list[Signal] = []
        facts: list[Fact] = []

        # -- Review signals --
        for rev in enrichment.reviews:
            label = rev.place or "Unknown place"
            if rev.rating:
                label += f" ({rev.rating}\u2605)"
            if rev.time_ago:
                label += f" \u2014 {rev.time_ago}"

            if rev.place:
                signals.append(Signal(
                    kind="lifestyle",
                    value=f"Google Maps review: {label}",
                    source=rev.place_url or enrichment.profile_url,
                    confidence=0.85,
                    notes=rev.text[:250] if rev.text else None,
                ))
            elif rev.text:
                facts.append(Fact(
                    claim=f"Google Maps review: {rev.text[:350]}",
                    source=enrichment.profile_url,
                    confidence=0.80,
                ))

        # -- Photo signals + downloads --
        photos_dir = get_photos_dir(ctx.case.case_id, "google_maps")
        for idx, photo in enumerate(enrichment.photos):
            label = photo.place_name or "unknown location"
            signals.append(Signal(
                kind="lifestyle",
                value=f"Google Maps photo uploaded \u2014 {label}",
                source=photo.url,
                confidence=0.75,
                notes=None,
            ))
            # Download to centralized photos dir
            fname = f"gaia_{gaia_id}_{idx:03d}.jpg"
            await download_image(photo.url, photos_dir / fname)

        # Download profile pic if available — also emit contact:photo so
        # vision_batch's scheduling requirement is satisfied.
        if enrichment.profile_pic_url:
            await download_image(
                enrichment.profile_pic_url,
                photos_dir / f"gaia_{gaia_id}_profile.jpg",
            )
            signals.append(Signal(
                kind="contact", tag="photo",
                value=enrichment.profile_pic_url,
                source=enrichment.profile_url,
                confidence=0.90,
                notes=f"Google profile picture for Gaia ID {gaia_id}",
            ))

        # -- Stats facts --
        s = enrichment.stats
        if s.reviews_count or s.ratings_count or s.photos_count:
            parts: list[str] = []
            if s.reviews_count:
                parts.append(f"{s.reviews_count} reviews")
            if s.ratings_count:
                parts.append(f"{s.ratings_count} ratings")
            if s.photos_count:
                parts.append(f"{s.photos_count} photos")
            if s.local_guides_level:
                parts.append(f"Local Guides level {s.local_guides_level}")
            facts.append(Fact(
                claim=f"Google Maps contributor stats: {', '.join(parts)}",
                source=enrichment.profile_url,
                confidence=0.90,
            ))

        # -- Summary --
        summary_parts = [f"GAIA enrichment for {gaia_id}."]
        if enrichment.name:
            summary_parts.append(f"Name: {enrichment.name}.")
        if s.reviews_count or s.ratings_count or s.photos_count:
            summary_parts.append(
                f"Contributor: {s.reviews_count} reviews, {s.ratings_count} ratings, {s.photos_count} photos"
                + (f", Local Guides level {s.local_guides_level}" if s.local_guides_level else "")
                + "."
            )
        if enrichment.reviews:
            places = [r.place for r in enrichment.reviews if r.place]
            summary_parts.append(f"Reviewed places: {', '.join(places[:6])}.")
        if enrichment.photos:
            summary_parts.append(f"Found {len(enrichment.photos)} public photo(s).")

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=" ".join(summary_parts),
            signals=signals,
            facts=facts,
            gaps=enrichment.gaps,
            raw=enrichment.model_dump(),
        )
