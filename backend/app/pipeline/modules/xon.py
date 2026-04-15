"""XposedOrNot (XON) breach-lookup module.

Queries https://api.xposedornot.com (free, no auth) for:
  1. breach-analytics — rich per-breach detail, pastes, password risk, exposed types
  2. check-email     — lightweight fallback list if analytics returns no data

Surfaces two categories of signal:
  * contact   — every breach domain is a service the debtor registered on
  * risk_flag — plaintext/sensitive breach, paste exposure, or dangerous data types

No ctx_patch: breach data doesn't yield new identity fields worth merging.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

_BASE = "https://api.xposedornot.com/v1"
_HEADERS = {"User-Agent": "VexorEnrichmentPipeline/1.0"}
_TIMEOUT = 15.0
_SOURCE_PREFIX = "https://xposedornot.com/xposed/#"

_SENSITIVE_DATA_TYPES = {
    "social security numbers",
    "credit cards",
    "bank account numbers",
    "passport numbers",
    "driver's licence numbers",
    "health records",
    "tax records",
}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def _get(client: httpx.AsyncClient, url: str) -> tuple[int, Any]:
    try:
        r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 429:
            retry_after = int(r.headers.get("retry-after", "1"))
            await asyncio.sleep(min(retry_after, 5))
            r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code == 200:
            return 200, r.json()
        return r.status_code, None
    except Exception as exc:
        return -1, str(exc)


class XposedOrNotModule:
    name = "xon"
    requires: tuple[str, ...] = ("email",)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()
        email = ctx.email
        enc = quote(email, safe="")

        async with httpx.AsyncClient() as client:
            analytics_status, analytics = await _get(
                client, f"{_BASE}/breach-analytics?email={enc}"
            )
            # Only call check-email if analytics found nothing (404) or errored
            if analytics_status not in (200,):
                check_status, check = await _get(
                    client, f"{_BASE}/check-email/{enc}"
                )
            else:
                check_status, check = 0, None

        signals: list[Signal] = []
        facts: list[Fact] = []
        gaps: list[str] = []
        raw: dict[str, Any] = {
            "analytics_status": analytics_status,
            "analytics": analytics,
            "check_status": check_status,
            "check": check,
        }

        # ── no breach data at all ──────────────────────────────────────────
        if analytics_status == 404 and check_status in (404, 0, -1):
            gaps.append("No breach records found for this email on XposedOrNot")
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"No breach records found for {email} on XposedOrNot.",
                gaps=gaps,
                raw=raw,
                duration_s=time.monotonic() - t0,
            )

        if analytics_status == -1:
            err_msg = analytics if isinstance(analytics, str) else "request failed"
            gaps.append(f"XposedOrNot API error: {err_msg}")
            return ModuleResult(
                name=self.name,
                status="error",
                summary=f"XposedOrNot lookup failed for {email}.",
                gaps=gaps,
                raw=raw,
                duration_s=time.monotonic() - t0,
            )

        # ── parse analytics response ───────────────────────────────────────
        source_url = f"{_SOURCE_PREFIX}{enc}"

        if analytics_status == 200 and analytics:
            signals, facts, gaps = _parse_analytics(analytics, email, source_url)
        elif check_status == 200 and check:
            signals, facts, gaps = _parse_check(check, email, source_url)
        else:
            gaps.append("XposedOrNot returned an unexpected response; see raw for details")

        breach_count = len([s for s in signals if s.kind == "contact"])
        risk_count = len([s for s in signals if s.kind == "risk_flag"])

        summary_parts = []
        if breach_count:
            summary_parts.append(
                f"Email found in {breach_count} breach(es); "
                f"registered on: {', '.join(s.value for s in signals if s.kind == 'contact')[:120]}"
            )
        if risk_count:
            summary_parts.append(f"{risk_count} risk flag(s) raised (plaintext passwords, sensitive data, or pastes)")
        if facts:
            summary_parts.append(facts[0].claim)

        summary = " | ".join(summary_parts) if summary_parts else f"Breach data retrieved for {email}."

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=signals,
            facts=facts,
            gaps=gaps,
            raw=raw,
            duration_s=time.monotonic() - t0,
        )


# ── response parsers ───────────────────────────────────────────────────────────

def _parse_analytics(
    data: dict[str, Any], email: str, source_url: str
) -> tuple[list[Signal], list[Fact], list[str]]:
    """Parse the /v1/breach-analytics response.

    Real response shape (verified against live API):
      ExposedBreaches.breaches_details  — list of breach dicts
      BreachesSummary.site              — semicolon-separated breach names
      PastesSummary.cnt                 — paste count
      BreachMetrics.passwords_strength  — [{"PlainText": N, "EasyToCrack": N, ...}]
      BreachMetrics.risk                — [{"risk_label": "High", "risk_score": 68}]

    Each breach dict:
      breach, domain, industry, password_risk, references, xposed_data (semicolon str),
      xposed_date (year), xposed_records, added (ISO), details (text), verified, searchable
    """
    signals: list[Signal] = []
    facts: list[Fact] = []
    gaps: list[str] = []

    exposed = data.get("ExposedBreaches") or {}
    breach_list: list[dict] = []
    if isinstance(exposed, dict):
        breach_list = exposed.get("breaches_details") or []
    elif isinstance(exposed, list):
        breach_list = exposed

    years: list[str] = []
    all_exposed_types: set[str] = set()

    for breach in breach_list:
        if not isinstance(breach, dict):
            continue

        name = breach.get("breach") or ""
        domain = (breach.get("domain") or "").strip()
        year = breach.get("xposed_date") or ""
        password_risk = (breach.get("password_risk") or "").lower()
        ref_url = (breach.get("references") or "").strip() or source_url
        xposed_data_raw: str = breach.get("xposed_data") or ""
        exposed_types = [t.strip() for t in xposed_data_raw.split(";") if t.strip()]

        if year:
            years.append(year)

        # contact signal — service the debtor registered on
        label = domain if domain else name
        if label:
            year_note = f"breach year: {year}" if year else "year unknown"
            signals.append(Signal(
                kind="contact",
                value=label,
                source=ref_url,
                confidence=0.85,
                notes=f"Account registered on {label} ({year_note}). Data exposed: {', '.join(exposed_types) or 'unknown'}",
            ))

        # risk_flag — password stored as plaintext or easy-to-crack
        if password_risk in ("plaintext", "easytocrack"):
            signals.append(Signal(
                kind="risk_flag",
                value=f"Password exposed as {password_risk} in {name} breach",
                source=ref_url,
                confidence=0.9,
            ))

        # risk_flag — sensitive data types in the breach
        lower_types = {t.lower() for t in exposed_types}
        for dangerous in _SENSITIVE_DATA_TYPES:
            if dangerous in lower_types:
                signals.append(Signal(
                    kind="risk_flag",
                    value=f"{dangerous.capitalize()} exposed in {name} breach",
                    source=ref_url,
                    confidence=0.85,
                ))

        all_exposed_types.update(exposed_types)

    # Pastes
    pastes = data.get("PastesSummary") or {}
    paste_count = int(pastes.get("cnt") or 0) if isinstance(pastes, dict) else 0
    if paste_count:
        signals.append(Signal(
            kind="risk_flag",
            value=f"Email found in {paste_count} paste dump(s)",
            source=source_url,
            confidence=0.8,
            notes="Paste dumps often appear on Pastebin, Pastie, etc.",
        ))

    # Summary facts
    if breach_list:
        years_sorted = sorted(y for y in years if y)
        date_range = ""
        if years_sorted:
            date_range = f"; earliest {years_sorted[0]}, latest {years_sorted[-1]}"
        facts.append(Fact(
            claim=f"Email found in {len(breach_list)} breach(es){date_range}",
            source=source_url,
            confidence=0.95,
        ))

    if all_exposed_types:
        facts.append(Fact(
            claim=f"Exposed data types across all breaches: {', '.join(sorted(all_exposed_types))}",
            source=source_url,
            confidence=0.9,
        ))

    # Overall risk score from BreachMetrics
    metrics = data.get("BreachMetrics") or {}
    if isinstance(metrics, dict):
        risk_list = metrics.get("risk") or []
        if risk_list and isinstance(risk_list, list):
            risk = risk_list[0]
            label = risk.get("risk_label") or ""
            score = risk.get("risk_score") or 0
            if label:
                facts.append(Fact(
                    claim=f"Overall breach risk score: {label} ({score}/100)",
                    source=source_url,
                    confidence=0.85,
                ))

        pwd_list = metrics.get("passwords_strength") or []
        if pwd_list and isinstance(pwd_list, list):
            pwd = pwd_list[0]
            plaintext = int(pwd.get("PlainText") or 0)
            easy = int(pwd.get("EasyToCrack") or 0)
            total_weak = plaintext + easy
            if total_weak:
                facts.append(Fact(
                    claim=f"{total_weak} exposed password(s) are plaintext or easy-to-crack ({plaintext} plaintext, {easy} weak hash)",
                    source=source_url,
                    confidence=0.9,
                ))

    if not breach_list:
        gaps.append("breach-analytics returned 200 but contained no breach detail")

    return signals, facts, gaps


def _parse_check(
    data: dict[str, Any], email: str, source_url: str
) -> tuple[list[Signal], list[Fact], list[str]]:
    """Fallback parser for the lightweight check-email endpoint."""
    signals: list[Signal] = []
    facts: list[Fact] = []
    gaps: list[str] = []

    breach_names: list[str] = data.get("breaches") or data.get("Breaches") or []
    if not breach_names:
        gaps.append("check-email returned no breach names")
        return signals, facts, gaps

    for name in breach_names:
        signals.append(Signal(
            kind="contact",
            value=name,
            source=source_url,
            confidence=0.75,
            notes=f"Email registered on {name} (breach detected; no detail available from fallback endpoint)",
        ))

    facts.append(Fact(
        claim=f"Email found in {len(breach_names)} breach(es): {', '.join(breach_names)}",
        source=source_url,
        confidence=0.9,
    ))
    gaps.append("Full breach detail unavailable — only breach-analytics endpoint provides domain, date, and data-class breakdown")

    return signals, facts, gaps
