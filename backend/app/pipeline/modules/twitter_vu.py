"""Twitter VU (valid user) enrichment module.

Checks whether a Twitter/X username is a valid account via the upstream
platform-check VM.  On REGISTERED, extracts: display name, masked email,
phone country code, and profile picture URL.
"""

from __future__ import annotations

import time

from app.config import settings
from app.enrichment.platform_check import check_platform
from app.models import Signal, SocialLink
from app.pipeline.base import Context, ModuleResult


class TwitterVuModule:
    name = "twitter_vu"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "twitter"),)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        if not (settings.twitter_vu_port and settings.twitter_vu_api_key):
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["twitter_vu: missing port/api_key settings"],
                duration_s=time.monotonic() - t0,
            )

        handle_sig = ctx.best("contact", "twitter")
        handle = handle_sig.value if handle_sig else ""
        # Strip leading @ if present
        handle = handle.lstrip("@")

        result = await check_platform(
            platform="twitter_vu",
            host=settings.platform_check_host,
            port=settings.twitter_vu_port,
            api_key=settings.twitter_vu_api_key,
            identifier=handle,
            proxy=settings.platform_check_proxy,
        )

        dur = time.monotonic() - t0
        raw = {
            "identifier": handle,
            "status_raw": result.status_raw,
            "http_status": result.http_status,
            "data": result.data,
            "error": result.error,
        }

        if result.error:
            return ModuleResult(
                name=self.name, status="error",
                summary=f"Twitter VU check failed: {result.error}",
                gaps=[result.error], raw=raw, duration_s=dur,
            )

        if result.registered is not True:
            return ModuleResult(
                name=self.name, status="ok",
                summary=f"@{handle} is NOT a valid Twitter/X user.",
                raw=raw, duration_s=dur,
            )

        # REGISTERED — extract rich data
        signals: list[Signal] = []
        social_links: list[SocialLink] = []
        d = result.data or {}

        name = d.get("name", "")
        masked_email = d.get("email", "")
        phone_code = d.get("phone", "")
        avatar = d.get("avatar", "")

        if name:
            signals.append(Signal(
                kind="name", value=name,
                source=f"platform_check:{self.name}",
                confidence=0.80,
                notes=f"Display name from Twitter/X profile @{handle}",
            ))

        if masked_email:
            signals.append(Signal(
                kind="contact", tag="email_masked",
                value=masked_email,
                source=f"platform_check:{self.name}",
                confidence=0.85,
                notes=f"Masked email associated with @{handle}",
            ))

        if phone_code:
            signals.append(Signal(
                kind="contact", tag="phone_hint",
                value=phone_code,
                source=f"platform_check:{self.name}",
                confidence=0.70,
                notes=f"Phone country code for @{handle}",
            ))

        if avatar:
            signals.append(Signal(
                kind="contact", tag="photo",
                value=avatar,
                source=f"platform_check:{self.name}",
                confidence=0.90,
                notes=f"Twitter/X profile picture for @{handle}",
            ))

        social_links.append(SocialLink(
            platform="twitter",
            url=f"https://x.com/{handle}",
            handle=handle,
            confidence=0.95,
        ))

        parts = [f"@{handle} is a valid Twitter/X user"]
        if name:
            parts.append(f"name={name}")
        if masked_email:
            parts.append(f"email={masked_email}")
        if phone_code:
            parts.append(f"phone_cc={phone_code}")

        return ModuleResult(
            name=self.name, status="ok",
            summary="; ".join(parts) + ".",
            signals=signals, social_links=social_links,
            raw=raw, duration_s=dur,
        )
