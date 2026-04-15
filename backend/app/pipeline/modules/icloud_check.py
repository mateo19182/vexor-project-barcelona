"""iCloud registration-check module.

Unlike the Instagram/Twitter checkers, the iCloud upstream accepts either an
email OR a phone number as the `w` field. If both are on the Context we
check both and merge the results — a single registered identifier is enough
to surface an iCloud contact signal.

Requires none of the canonical identity fields strictly (the runner's
`requires` is AND-only), but self-skips if neither email nor phone is set.
"""

from __future__ import annotations

import asyncio
import time

from app.config import settings
from app.enrichment.platform_check import build_module_result, check_platform
from app.models import Signal
from app.pipeline.base import Context, ModuleResult


class ICloudCheckModule:
    name = "icloud_check"
    # Empty because the upstream takes email OR phone — we self-skip below.
    requires: tuple[str, ...] = ()

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()

        if not (settings.icloud_check_port and settings.icloud_check_api_key):
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["icloud_check: missing port/api_key settings"],
                duration_s=time.monotonic() - t0,
            )

        identifiers: list[str] = [v for v in (ctx.email, ctx.phone) if v]
        if not identifiers:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["icloud_check: neither email nor phone on context"],
                duration_s=time.monotonic() - t0,
            )

        results = await asyncio.gather(
            *(
                check_platform(
                    platform="icloud",
                    host=settings.platform_check_host,
                    port=settings.icloud_check_port,
                    api_key=settings.icloud_check_api_key,
                    identifier=ident,
                    proxy=settings.platform_check_proxy,
                )
                for ident in identifiers
            )
        )

        bundles = [
            build_module_result(
                module_name=self.name, platform_label="iCloud", result=r
            )
            for r in results
        ]

        # Merge: status priority ok > no_data > error > skipped.
        signals: list[Signal] = []
        gaps: list[str] = []
        raw_per_id = []
        statuses = []
        summaries = []
        for b in bundles:
            signals.extend(b.get("signals", []))
            gaps.extend(b.get("gaps", []))
            raw_per_id.append(b.get("raw", {}))
            statuses.append(b.get("status", "error"))
            summaries.append(b.get("summary", ""))

        priority = {"ok": 0, "no_data": 1, "error": 2, "skipped": 3}
        final_status = min(statuses, key=lambda s: priority.get(s, 99))

        return ModuleResult(
            name=self.name,
            status=final_status,
            summary=" | ".join(s for s in summaries if s),
            signals=signals,
            gaps=gaps,
            raw={"checks": raw_per_id},
            duration_s=time.monotonic() - t0,
        )
