"""Batch vision analysis module.

Runs AFTER all image-producing modules (instagram, gaia_enrichment,
twitter_vu, image_search) have completed. Collects every image from the
centralized photos/{case_id}/ tree and sends them through the vision AI
for a unified analysis.

Wave scheduling: requires a signal that only exists after wave 1+ modules
have had a chance to deposit images. We use ("name", None) as the trigger —
every pipeline has a name signal from the case input, so this always runs,
but it runs in the same wave as other wave-1 modules. To push it later we
declare NO requires and let the runner schedule it in wave 1, but we
self-delay by checking if the photos dir has content.

Actually — simplest approach: require nothing, always run, but produce
useful output only when photos exist. The runner schedules it in wave 1
alongside everything else, and since image downloads happen during module
execution (not after), by the time vision_batch runs the photos may not
be there yet.

Better approach: we declare a synthetic dependency. But that's overengineering.

Simplest correct approach: run in the LAST wave by requiring a signal that
only late modules produce. We use ("lifestyle", None) — gaia_enrichment and
instagram both emit lifestyle signals. If neither ran, vision_batch skips
gracefully (no photos anyway).
"""

from __future__ import annotations

import sys
import time

from app.enrichment.image_store import list_all_images
from app.enrichment.vision import analyze_images
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult


def _log(msg: str) -> None:
    print(f"[vision_batch] {msg}", file=sys.stderr, flush=True)


MAX_IMAGES = 20  # cap to control cost/latency


class VisionBatchModule:
    name = "vision_batch"
    # Run after modules that produce lifestyle signals (gaia, instagram).
    # This pushes us to wave 2+ so photos are already downloaded.
    # Require contact:photo so we run AFTER twitter_vu/gaia deposit images.
    # If no photo signal exists, the runner skips us (no images anyway).
    requires: tuple[tuple[str, str | None], ...] = (("contact", "photo"),)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        case_id = ctx.case.case_id

        all_images = list_all_images(case_id)
        if not all_images:
            return ModuleResult(
                name=self.name,
                status="ok",
                summary="No images collected for batch vision analysis.",
                gaps=["No images found in photos directory"],
                duration_s=time.monotonic() - t0,
            )

        # Cap and log
        if len(all_images) > MAX_IMAGES:
            _log(f"capping {len(all_images)} images to {MAX_IMAGES}")
            all_images = all_images[:MAX_IMAGES]

        _log(f"analyzing {len(all_images)} image(s) across platforms")
        platforms = set()
        for _, label in all_images:
            platforms.add(label.split("/")[0])
        _log(f"platforms represented: {', '.join(sorted(platforms))}")

        # Build subject from case name
        name_sig = ctx.best("name")
        subject_name = name_sig.value if name_sig else case_id
        subject = f"OSINT subject {subject_name}"

        summary, facts, gaps = await analyze_images(
            images=all_images,
            subject=subject,
        )

        # Convert vision facts to signals where appropriate
        signals: list[Signal] = []
        kept_facts: list[Fact] = []
        for fact in facts:
            # Vision facts about locations/lifestyle become signals
            claim_lower = fact.claim.lower()
            if any(kw in claim_lower for kw in ("location", "city", "country", "lives in", "based in")):
                signals.append(Signal(
                    kind="location",
                    value=fact.claim,
                    source=f"vision_batch:{fact.source}",
                    confidence=min(fact.confidence, 0.40),
                    notes="Inferred from visual analysis of collected photos",
                ))
            elif any(kw in claim_lower for kw in ("car", "vehicle", "house", "property", "watch", "luxury")):
                signals.append(Signal(
                    kind="asset",
                    value=fact.claim,
                    source=f"vision_batch:{fact.source}",
                    confidence=min(fact.confidence, 0.35),
                    notes="Inferred from visual analysis of collected photos",
                ))
            elif any(kw in claim_lower for kw in ("lifestyle", "travel", "restaurant", "sport", "hobby")):
                signals.append(Signal(
                    kind="lifestyle",
                    value=fact.claim,
                    source=f"vision_batch:{fact.source}",
                    confidence=min(fact.confidence, 0.40),
                    notes="Inferred from visual analysis of collected photos",
                ))
            else:
                kept_facts.append(fact)

        dur = time.monotonic() - t0
        _log(
            f"done in {dur:.1f}s: {len(signals)} signal(s), "
            f"{len(kept_facts)} fact(s), {len(gaps)} gap(s) "
            f"from {len(all_images)} image(s)"
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary or f"Batch vision analysis of {len(all_images)} images.",
            signals=signals,
            facts=kept_facts,
            gaps=gaps,
            raw={
                "image_count": len(all_images),
                "platforms": sorted(platforms),
                "images_analyzed": [label for _, label in all_images],
            },
            duration_s=dur,
        )
