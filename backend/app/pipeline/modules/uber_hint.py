"""Uber Hint module (VM & VN — validated masks).

Checks whether an email or phone is registered with Uber via the upstream
platform-check VM.  On REGISTERED, extracts cross-channel masked contact info
(email lookup returns phone mask, phone lookup returns email mask).
"""

from __future__ import annotations

import time

from app.config import settings
from app.enrichment.platform_check import check_platform
from app.models import Signal
from app.pipeline.base import Context, ModuleResult


class UberHintModule:
    name = "uber_hint"
    requires: tuple[tuple[str, str | None], ...] = ()  # needs email OR phone

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        if not (settings.uber_hint_port and settings.uber_hint_api_key):
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["uber_hint: missing port/api_key settings"],
                duration_s=time.monotonic() - t0,
            )

        # Try email first, then phone
        email_sig = ctx.best("contact", "email")
        phone_sig = ctx.best("contact", "phone")

        if not email_sig and not phone_sig:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["uber_hint: no email or phone signal available"],
                duration_s=time.monotonic() - t0,
            )

        all_signals: list[Signal] = []
        all_raw: dict = {}
        summaries: list[str] = []

        # Check email if available
        if email_sig:
            email = email_sig.value
            r = await self._check(email, "email")
            all_raw["email_lookup"] = r["raw"]
            if r["signals"]:
                all_signals.extend(r["signals"])
            summaries.append(r["summary"])

        # Check phone if available
        if phone_sig:
            phone = phone_sig.value
            r = await self._check(phone, "phone")
            all_raw["phone_lookup"] = r["raw"]
            if r["signals"]:
                all_signals.extend(r["signals"])
            summaries.append(r["summary"])

        status = "ok" if all_signals else "ok"
        return ModuleResult(
            name=self.name, status=status,
            summary=" | ".join(summaries),
            signals=all_signals, raw=all_raw,
            duration_s=time.monotonic() - t0,
        )

    async def _check(self, identifier: str, id_type: str) -> dict:
        result = await check_platform(
            platform="uber_hint",
            host=settings.platform_check_host,
            port=settings.uber_hint_port,
            api_key=settings.uber_hint_api_key,
            identifier=identifier,
            proxy=settings.platform_check_proxy,
        )

        raw = {
            "identifier": identifier,
            "id_type": id_type,
            "status_raw": result.status_raw,
            "data": result.data,
            "error": result.error,
        }

        if result.error:
            return {"signals": [], "raw": raw, "summary": f"Uber check failed for {identifier}: {result.error}"}

        if result.registered is not True:
            return {"signals": [], "raw": raw, "summary": f"{identifier} is NOT registered on Uber."}

        # REGISTERED — extract cross-channel masks
        signals: list[Signal] = []
        d = result.data or {}
        phone_mask = d.get("phoneMask", "")
        email_mask = d.get("emailMask", "")

        signals.append(Signal(
            kind="contact", tag="uber",
            value=f"Uber account registered to {identifier}",
            source=f"platform_check:{self.name}",
            confidence=0.85,
        ))

        if phone_mask:
            signals.append(Signal(
                kind="contact", tag="phone_masked",
                value=phone_mask,
                source=f"platform_check:{self.name}",
                confidence=0.80,
                notes=f"Masked phone from Uber (looked up via {id_type}: {identifier})",
            ))

        if email_mask:
            signals.append(Signal(
                kind="contact", tag="email_masked",
                value=email_mask,
                source=f"platform_check:{self.name}",
                confidence=0.80,
                notes=f"Masked email from Uber (looked up via {id_type}: {identifier})",
            ))

        parts = [f"{identifier} registered on Uber"]
        if phone_mask:
            parts.append(f"phone={phone_mask}")
        if email_mask:
            parts.append(f"email={email_mask}")

        return {"signals": signals, "raw": raw, "summary": "; ".join(parts)}
