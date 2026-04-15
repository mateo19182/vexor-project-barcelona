"""Twitter/X registration-check module.

Asks the upstream platform-check VM whether `ctx.email` is tied to a
Twitter/X account.
"""

from __future__ import annotations

import time

from app.config import settings
from app.enrichment.platform_check import build_module_result, check_platform
from app.pipeline.base import Context, ModuleResult


class TwitterCheckModule:
    name = "twitter_check"
    requires: tuple[str, ...] = ("email",)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        if not (settings.twitter_check_port and settings.twitter_check_api_key):
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["twitter_check: missing port/api_key settings"],
                duration_s=time.monotonic() - t0,
            )

        result = await check_platform(
            platform="twitter",
            host=settings.platform_check_host,
            port=settings.twitter_check_port,
            api_key=settings.twitter_check_api_key,
            identifier=ctx.email,
            proxy=settings.platform_check_proxy,
        )
        bundle = build_module_result(
            module_name=self.name,
            platform_label="Twitter",
            result=result,
        )
        return ModuleResult(
            name=self.name,
            duration_s=time.monotonic() - t0,
            **bundle,
        )
