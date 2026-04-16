"""Google Maps Reviews module.

Input  → ctx.gaia_id  (set directly via Case.google_id in the case seed)
Output → raw JSON list of reviews + lifestyle signals

Each review: { place, rating, text, time_ago, place_url, source_url }
"""

from __future__ import annotations

import json
import sys

from app.config import settings
from app.enrichment.google_maps_reviews import fetch_reviews
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
        _log(f"[google_maps_reviews] cannot parse GOOGLE_SESSION_COOKIES: {e}")
    return None


class GoogleMapsReviewsModule:
    name = "google_maps_reviews"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "gaia_id"),)

    async def run(self, ctx: Context) -> ModuleResult:
        gaia_sig = ctx.best("contact", "gaia_id")
        gaia_id = gaia_sig.value if gaia_sig else ""

        cookies = _load_cookies()
        if cookies is None:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["GOOGLE_SESSION_COOKIES not set in .env"],
            )

        _log(f"[google_maps_reviews] fetching reviews for {gaia_id}")
        enrichment = await fetch_reviews(gaia_id, cookies)

        if not enrichment.reviews:
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=f"No public Google Maps reviews for Gaia ID {gaia_id}.",
                gaps=enrichment.gaps,
                raw=enrichment.model_dump(),
            )

        signals: list[Signal] = []
        facts: list[Fact] = []

        for rev in enrichment.reviews:
            if rev.place:
                # Canonical short value: just the place name.
                # Rating + time context goes in notes for synthesis.
                note_parts: list[str] = []
                if rev.rating:
                    note_parts.append(f"{rev.rating}★")
                if rev.time_ago:
                    note_parts.append(rev.time_ago)
                if rev.text:
                    note_parts.append(rev.text[:200])
                signals.append(Signal(
                    kind="lifestyle",
                    value=rev.place,
                    source=rev.place_url or enrichment.profile_url,
                    confidence=0.85,
                    notes=" — ".join(note_parts) if note_parts else None,
                ))
            elif rev.text:
                facts.append(Fact(
                    claim=f"Google Maps review: {rev.text[:350]}",
                    source=enrichment.profile_url,
                    confidence=0.80,
                ))

        places = [r.place for r in enrichment.reviews if r.place]
        summary = f"Found {enrichment.total_found} Google Maps review(s) for Gaia ID {gaia_id}."
        if places:
            summary += f" Places: {', '.join(places[:6])}."

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=signals,
            facts=facts,
            gaps=enrichment.gaps,
            raw=enrichment.model_dump(),
        )
