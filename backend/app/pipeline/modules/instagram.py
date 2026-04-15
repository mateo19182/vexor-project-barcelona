"""Instagram OSINT module — thin wrapper around the existing enricher."""

from __future__ import annotations

from app.enrichment.instagram import enrich_instagram
from app.pipeline.base import Context, ModuleResult


class InstagramModule:
    name = "instagram"
    requires: tuple[str, ...] = ("instagram_handle",)

    async def run(self, ctx: Context) -> ModuleResult:
        # Honor any handle a resolver module placed on the context, falling
        # back to whatever the Case originally carried.
        case = ctx.case.model_copy(
            update={"instagram_handle": ctx.instagram_handle}
        )
        ig = await enrich_instagram(case)
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
