"""Instagram OSINT module — thin wrapper around the existing enricher."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.enrichment.image_store import copy_image, get_photos_dir
from app.enrichment.instagram import enrich_instagram
from app.models import Signal
from app.pipeline.base import Context, ModuleResult


class InstagramModule:
    name = "instagram"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "instagram"),)

    async def run(self, ctx: Context) -> ModuleResult:
        sig = ctx.best("contact", "instagram")
        handle = (sig.value if sig else "").strip().lstrip("@")
        ig = await enrich_instagram(handle=handle, case_id=ctx.case.case_id)

        # Copy downloaded images to centralized photos dir
        osintgram_dir = Path(settings.osintgram_output_dir).resolve() / handle
        copied: list[Path] = []
        if osintgram_dir.is_dir():
            ig_photos = get_photos_dir(ctx.case.case_id, "instagram")
            for f in sorted(osintgram_dir.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    copy_image(f, ig_photos / f.name)
                    copied.append(f)

        # Emit contact:photo so vision_batch is scheduled if we have images.
        signals: list[Signal] = []
        if copied:
            signals.append(Signal(
                kind="contact", tag="photo",
                value=f"instagram/{copied[0].name}",
                source=f"https://www.instagram.com/{handle}/",
                confidence=0.80,
                notes=f"{len(copied)} Instagram photo(s) copied to photos dir",
            ))

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=ig.summary,
            signals=signals,
            facts=ig.facts,
            gaps=ig.gaps,
            raw={
                "profile_info": ig.profile_info,
                "raw_captions": ig.raw_captions,
                "image_count": ig.image_count,
                "video_count": ig.video_count,
            },
        )
