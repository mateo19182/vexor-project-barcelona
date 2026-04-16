"""Lead contact verification module.

Cross-references the lead's known email(s) and phone(s) against masked
versions returned by platform-check APIs (Twitter VU, Uber Hint) to assess
whether the lead's contact information is still current.

Produces a structured verification report with per-field verdicts and an
overall quality score.  This is the evaluator's answer to "is this lead
data still accurate?"
"""

from __future__ import annotations

import time

from app.enrichment.mask_matching import (
    MatchResult,
    match_email_mask,
    match_phone_mask,
)
from app.models import Signal
from app.pipeline.base import Context, ModuleResult


class LeadVerificationModule:
    name = "lead_verification"
    # Runs after at least one masked email exists (Twitter VU, Uber Hint).
    requires: tuple[tuple[str, str | None], ...] = (("contact", "email_masked"),)

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()

        # --- Collect inputs: known values from the ORIGINAL lead only ---
        # Only compare case_input signals — not emails/phones discovered by
        # other modules (e.g. breach hashes, IPs tagged as phone).
        input_emails = _unique_values([
            s for s in ctx.all("contact", "email")
            if s.source == "case_input" or s.source == "csv_import"
        ])
        input_phones = _unique_values([
            s for s in ctx.all("contact", "phone")
            if s.source == "case_input" or s.source == "csv_import"
        ])

        # --- Collect masks from platform checks ---
        email_masks = [
            (s.value, _platform_from_source(s.source))
            for s in ctx.all("contact", "email_masked")
            if s.value.strip()
        ]
        phone_masks = [
            (s.value, _platform_from_source(s.source))
            for s in ctx.all("contact", "phone_masked")
            if s.value.strip()
        ]
        phone_hints = [
            (s.value, _platform_from_source(s.source))
            for s in ctx.all("contact", "phone_hint")
            if s.value.strip()
        ]

        if not email_masks and not phone_masks and not phone_hints:
            return ModuleResult(
                name=self.name, status="ok",
                summary="No masked contact data available for verification.",
                gaps=["No platform returned masked contact data"],
                duration_s=time.monotonic() - t0,
            )

        # --- Run all comparisons ---
        checks: list[dict] = []
        all_results: list[MatchResult] = []

        # Email checks
        for email in input_emails:
            email_check = {
                "field": "email",
                "input": email,
                "matches": [],
                "verdict": "unverifiable",
            }
            for mask_val, platform in email_masks:
                r = match_email_mask(email, mask_val, platform)
                all_results.append(r)
                email_check["matches"].append({
                    "platform": platform,
                    "mask": mask_val,
                    "result": r.result,
                    "reason": r.reason,
                })
            email_check["verdict"] = _field_verdict(email_check["matches"])
            checks.append(email_check)

        # Phone checks (against both phone_masked and phone_hint)
        combined_phone_masks = phone_masks + phone_hints
        for phone in input_phones:
            phone_check = {
                "field": "phone",
                "input": phone,
                "matches": [],
                "verdict": "unverifiable",
            }
            for mask_val, platform in combined_phone_masks:
                r = match_phone_mask(phone, mask_val, platform)
                all_results.append(r)
                phone_check["matches"].append({
                    "platform": platform,
                    "mask": mask_val,
                    "result": r.result,
                    "reason": r.reason,
                })
            phone_check["verdict"] = _field_verdict(phone_check["matches"])
            checks.append(phone_check)

        # --- Cross-checks (email→phone and phone→email) ---
        cross_checks: list[dict] = []

        # If we looked up email on Uber and got a phone mask, compare it
        # against the lead's phones. This is already covered above.
        # But let's note which lookups enable cross-verification.
        for email in input_emails:
            for mask_val, platform in phone_masks:
                # phone mask came from email lookup on this platform
                for phone in input_phones:
                    r = match_phone_mask(phone, mask_val, platform)
                    cross_checks.append({
                        "description": (
                            f"{platform} looked up email '{email}' → "
                            f"phone mask '{mask_val}' vs lead phone '{phone}'"
                        ),
                        "result": r.result,
                        "reason": r.reason,
                    })

        for phone in input_phones:
            for mask_val, platform in email_masks:
                # Check if any email mask came from a phone lookup
                # (noted in the signal's notes field — we just compare all)
                for email in input_emails:
                    # Already covered in email checks above; just note it
                    pass

        # --- Compute overall quality ---
        quality, score = _overall_quality(checks, all_results)

        # --- Build summary ---
        summary_parts = []
        for c in checks:
            n_matches = len(c["matches"])
            if n_matches == 0:
                continue
            compatible = sum(1 for m in c["matches"] if m["result"] == "compatible")
            incompatible = sum(1 for m in c["matches"] if m["result"] == "incompatible")
            platforms = ", ".join(m["platform"] for m in c["matches"])
            if compatible and not incompatible:
                summary_parts.append(
                    f"{c['field']} verified across {compatible} platform(s) "
                    f"[{platforms}]"
                )
            elif incompatible and not compatible:
                summary_parts.append(
                    f"{c['field']} INCONSISTENT across {incompatible} "
                    f"platform(s) [{platforms}] — likely outdated or "
                    f"different {c['field']} used"
                )
            elif incompatible and compatible:
                summary_parts.append(
                    f"{c['field']} MIXED — matches on {compatible}, "
                    f"mismatches on {incompatible} platform(s) [{platforms}]"
                )
            else:
                summary_parts.append(
                    f"{c['field']} inconclusive ({n_matches} mask(s) checked)"
                )

        summary = (
            f"Lead quality: {quality.upper()} ({score:.0%}). "
            + "; ".join(summary_parts) + "."
            if summary_parts
            else f"Lead quality: {quality.upper()} ({score:.0%})."
        )

        # --- Emit signals for key findings ---
        signals: list[Signal] = []

        # A risk flag if any field is incompatible
        incompatible_fields = [
            c for c in checks if c["verdict"] == "likely_outdated"
        ]
        if incompatible_fields:
            fields_str = ", ".join(c["field"] for c in incompatible_fields)
            signals.append(Signal(
                kind="risk_flag",
                value=f"Contact data possibly outdated: {fields_str}",
                source=f"module:{self.name}",
                confidence=0.75,
                notes=(
                    f"Masked data from platform checks doesn't match the "
                    f"lead's {fields_str}. The person may have updated their "
                    f"contact info on those platforms."
                ),
            ))

        # Positive signal if verified
        verified_fields = [
            c for c in checks if c["verdict"] == "likely_current"
        ]
        if verified_fields:
            fields_str = ", ".join(c["field"] for c in verified_fields)
            signals.append(Signal(
                kind="contact",
                tag="verified",
                value=f"Verified: {fields_str}",
                source=f"module:{self.name}",
                confidence=0.85,
                notes=(
                    f"Lead's {fields_str} compatible with masked data from "
                    f"platform checks — contact info appears current."
                ),
            ))

        dur = time.monotonic() - t0
        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=signals,
            raw={
                "verification": {
                    "quality": quality,
                    "score": round(score, 3),
                    "summary": summary,
                    "checks": checks,
                    "cross_checks": cross_checks,
                    "input_emails": input_emails,
                    "input_phones": input_phones,
                    "masks_found": {
                        "email_masked": len(email_masks),
                        "phone_masked": len(phone_masks),
                        "phone_hint": len(phone_hints),
                    },
                },
            },
            duration_s=dur,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_values(signals: list[Signal]) -> list[str]:
    """Deduplicate signal values preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for s in signals:
        v = s.value.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def _platform_from_source(source: str) -> str:
    """Extract platform name from signal source like 'platform_check:twitter_vu'."""
    if ":" in source:
        return source.split(":", 1)[1]
    return source


def _field_verdict(matches: list[dict]) -> str:
    """Determine verdict for one field based on its mask matches."""
    if not matches:
        return "unverifiable"

    compatible = sum(1 for m in matches if m["result"] == "compatible")
    incompatible = sum(1 for m in matches if m["result"] == "incompatible")

    if incompatible > 0 and compatible == 0:
        return "likely_outdated"
    if incompatible > 0 and compatible > 0:
        return "mixed"  # some platforms match, some don't
    if compatible > 0:
        return "likely_current"
    return "inconclusive"


def _overall_quality(
    checks: list[dict],
    all_results: list[MatchResult],
) -> tuple[str, float]:
    """Compute overall quality grade and numeric score.

    Scoring:
      - Each compatible match: +1
      - Each incompatible match: -1.5 (mismatches weigh more)
      - Each inconclusive: 0

    Normalize to [0, 1] range. Grade thresholds:
      high:    >= 0.7
      medium:  >= 0.4
      low:     >= 0.0
      unknown: no data
    """
    if not all_results:
        return "unknown", 0.0

    total = len(all_results)
    compatible = sum(1 for r in all_results if r.result == "compatible")
    incompatible = sum(1 for r in all_results if r.result == "incompatible")

    # Raw score: compatible adds, incompatible subtracts more
    raw = compatible - (incompatible * 1.5)
    # Normalize: best case all compatible = 1.0, worst case all incompatible = 0.0
    max_possible = total
    score = max(0.0, min(1.0, (raw + total * 1.5) / (total * 2.5)))

    # Also factor in coverage: more verified fields = higher confidence
    fields_verified = sum(
        1 for c in checks if c["verdict"] == "likely_current"
    )
    fields_outdated = sum(
        1 for c in checks if c["verdict"] == "likely_outdated"
    )

    if fields_outdated > 0 and fields_verified == 0:
        return "low", score
    if fields_outdated > 0:
        return "medium", score
    if fields_verified >= 2:
        return "high", score
    if fields_verified == 1:
        return "medium", score
    return "unknown", score
