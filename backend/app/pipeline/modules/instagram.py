"""Instagram OSINT module — thin wrapper around the existing enricher."""

from __future__ import annotations

from app.enrichment.instagram import enrich_instagram
from app.pipeline.base import Context, ModuleResult


class InstagramModule:
    name = "instagram"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "instagram"),)

    async def run(self, ctx: Context) -> ModuleResult:
        sig = ctx.best("contact", "instagram")
        handle = (sig.value if sig else "").strip().lstrip("@")
        ig = await enrich_instagram(handle=handle, case_id=ctx.case.case_id)
        return ModuleResult(
            name=self.name,
            status="ok",
            summary=ig.summary,
            facts=ig.facts,
            gaps=ig.gaps,
            raw={
                "profile_info": ig.profile_info,
                "raw_captions": ig.raw_captions,
                "image_count": ig.image_count,
                "video_count": ig.video_count,
            },
        )
