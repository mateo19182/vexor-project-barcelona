"""Wallapop marketplace enrichment module.

Searches Wallapop for active seller profiles matching the debtor's name.
Scores candidates by listing proximity to known address, then applies a
decisive phone signal:

  • Phone in listings = known phone  → confidence 0.92 (near-certain)
  • Phone in listings ≠ known phone  → heavy penalty (×0.20)
  • No phone found                   → location-only score

Requires: name
Enriched by (optional): address, phone

Emits:
  - asset     — items of value listed for sale
  - contact   — phone numbers extracted from listing descriptions
  - location  — city of the validated seller
  - risk_flag — high listing volume (>= 5 active items)
"""

from __future__ import annotations

import re

from app.config import settings
from app.enrichment.wallapop import _haversine_km, geocode_address, search_wallapop
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

# Candidates below this score are noted in gaps but not surfaced as signals.
_CONFIDENCE_THRESHOLD = 0.35

_ASSET_KEYWORDS = frozenset({
    "iphone", "macbook", "laptop", "portátil", "televisor", "tv", "monitor",
    "moto", "scooter", "bicicleta", "reloj", "watch", "coche", "cámara",
    "camera", "consola", "ps5", "ps4", "xbox", "airpods", "tablet", "ipad",
    "joya", "anillo", "sofá", "mueble", "dron", "drone", "gopro",
})


def _is_valuable(title: str, price: float | None) -> bool:
    tl = title.lower()
    return any(kw in tl for kw in _ASSET_KEYWORDS) or (price is not None and price >= 50)


class WallapopModule:
    name = "wallapop"
    requires = (("name", None),)

    async def run(self, ctx: Context) -> ModuleResult:
        name = ctx.name or ""
        phone = ctx.phone
        address = ctx.address

        facts: list[Fact] = []
        signals: list[Signal] = []
        gaps: list[str] = []

        # Geocode known address for proximity scoring
        lat: float | None = None
        lon: float | None = None
        if address:
            coords = await geocode_address(address, settings.nominatim_user_agent)
            if coords:
                lat, lon = coords
            else:
                gaps.append(
                    f"wallapop: could not geocode '{address}' — "
                    "searching without location filter (lower confidence)"
                )

        result = await search_wallapop(
            name=name,
            lat=lat,
            lon=lon,
            phone=phone,
        )

        if result["errors"]:
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=result["errors"],
            )

        all_matches = result["matches"]

        if not all_matches:
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary="No Wallapop listings found matching this debtor.",
                gaps=["wallapop: no candidates returned by search"],
            )

        confident = [m for m in all_matches if m["score"] >= _CONFIDENCE_THRESHOLD]

        if not confident:
            best = all_matches[0]
            reason = "; ".join(best["evidence"]) or "name match only"
            gaps.append(
                f"wallapop: {len(all_matches)} candidate(s) found but none validated "
                f"(best score {best['score']:.2f} — {reason})"
            )
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=f"Wallapop: {len(all_matches)} candidate(s), none validated.",
                gaps=gaps,
                raw={"matches": all_matches[:5]},
            )

        # Process top 2 validated matches
        for match in confident[:2]:
            seller = match["seller"]
            profile_url = seller["profile_url"]
            user_id = seller["user_id"]
            evidence_str = "; ".join(match["evidence"])

            facts.append(Fact(
                claim=(
                    f"Wallapop seller (user_id={user_id}) validated "
                    f"(score {match['score']:.2f}): {profile_url} — {evidence_str}"
                ),
                source=profile_url,
                confidence=match["score"],
            ))

            # Contact signals for every phone found in this seller's listings
            for found_phone in match["phones"]:
                signals.append(Signal(
                    kind="contact",
                    value=found_phone,
                    source=profile_url,
                    confidence=match["score"],
                    notes="Phone extracted from Wallapop listing description",
                ))

            # Location: use city from closest listing
            if match["min_km"] is not None:
                closest_item = min(
                    (i for i in match["items"] if i["location"]["latitude"] is not None),
                    key=lambda i: _haversine_km(
                        lat or 0, lon or 0,
                        i["location"]["latitude"], i["location"]["longitude"],
                    ),
                    default=None,
                )
                city = (closest_item or {}).get("location", {}).get("city") if closest_item else None
                location_value = city or f"{match['min_km']:.1f}km from known address"
                signals.append(Signal(
                    kind="location",
                    value=location_value,
                    source=profile_url,
                    confidence=min(match["score"], 0.70),
                    notes=f"Closest listing {match['min_km']:.1f}km from known address (Wallapop)",
                ))

            # Asset + risk signals from individual listings
            item_count = len(match["items"])
            for item in match["items"]:
                if _is_valuable(item["title"], item["price_eur"]):
                    price_str = f" — listed €{item['price_eur']:.0f}" if item["price_eur"] else ""
                    signals.append(Signal(
                        kind="asset",
                        value=f"{item['title']}{price_str}",
                        source=item["url"],
                        confidence=round(match["score"] * 0.9, 2),
                        notes="Item actively listed for sale on Wallapop",
                    ))

            if item_count >= 5:
                signals.append(Signal(
                    kind="risk_flag",
                    value=f"{item_count} active listings on Wallapop",
                    source=profile_url,
                    confidence=0.55,
                    notes="High listing volume may indicate asset liquidation",
                ))

            # Reviews: surface reputation and any useful comments
            reviews = match.get("reviews") or []
            if reviews:
                scores = [rv["scoring"] for rv in reviews if rv.get("scoring") is not None]
                avg_score = round(sum(scores) / len(scores), 1) if scores else None
                score_str = f", avg rating {avg_score}/100" if avg_score is not None else ""
                facts.append(Fact(
                    claim=(
                        f"Wallapop seller has {len(reviews)} review(s){score_str}. "
                        f"Shipping transactions: "
                        f"{sum(1 for rv in reviews if rv.get('is_shipping'))}."
                    ),
                    source=profile_url,
                    confidence=match["score"],
                ))
                for rv in reviews:
                    comment = rv.get("comments", "").strip()
                    if comment and len(comment) > 10:
                        facts.append(Fact(
                            claim=f"Wallapop review comment: \"{comment}\"",
                            source=profile_url,
                            confidence=round(match["score"] * 0.8, 2),
                        ))

        top = confident[0]
        summary = (
            f"Wallapop: seller (user_id={top['seller']['user_id']}) validated "
            f"(score {top['score']:.2f}, {len(top['items'])} listing(s)). "
            f"Evidence: {'; '.join(top['evidence'])}."
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            facts=facts,
            signals=signals,
            gaps=gaps,
            raw={"matches": confident},
        )
