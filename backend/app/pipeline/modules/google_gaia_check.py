"""Google Gaia ID check module.

Asks the upstream platform-check VM whether the subject's email is tied to a
Google account.  On REGISTERED, extracts the Gaia ID from the response data.
"""

from __future__ import annotations

import time

from app.config import settings
from app.enrichment.platform_check import check_platform
from app.models import Signal
from app.pipeline.base import Context, ModuleResult


class GoogleGaiaCheckModule:
    name = "google_gaia_check"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "email"),)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        if not (settings.google_gaia_check_port and settings.google_gaia_check_api_key):
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["google_gaia_check: missing port/api_key settings"],
                duration_s=time.monotonic() - t0,
            )

        email_sig = ctx.best("contact", "email")
        email = email_sig.value if email_sig else ""

        result = await check_platform(
            platform="google_gaia",
            host=settings.platform_check_host,
            port=settings.google_gaia_check_port,
            api_key=settings.google_gaia_check_api_key,
            identifier=email,
            proxy=settings.platform_check_proxy,
        )

        dur = time.monotonic() - t0
        raw = {
            "identifier": email,
            "status_raw": result.status_raw,
            "http_status": result.http_status,
            "data": result.data,
            "error": result.error,
        }

        if result.error:
            return ModuleResult(
                name=self.name, status="error",
                summary=f"Google Gaia check failed: {result.error}",
                gaps=[result.error], raw=raw, duration_s=dur,
            )

        if result.registered is not True:
            return ModuleResult(
                name=self.name, status="ok",
                summary=f"{email} is NOT registered on Google.",
                raw=raw, duration_s=dur,
            )

        # REGISTERED — extract gaiaId from data
        signals: list[Signal] = []
        d = result.data or {}
        gaia_id = d.get("gaiaId", "")

        if gaia_id:
            signals.append(Signal(
                kind="contact", tag="gaia_id",
                value=str(gaia_id),
                source=f"platform_check:{self.name}",
                confidence=1.0,
                notes=f"Google account registered to {email}",
            ))

        return ModuleResult(
            name=self.name, status="ok",
            summary=f"{email} -> Google Gaia ID {gaia_id}" if gaia_id else f"{email} registered on Google (no Gaia ID in response)",
            signals=signals, raw=raw, duration_s=dur,
        )
