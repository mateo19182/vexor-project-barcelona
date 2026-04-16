"""Final synthesis pass.

Aggregates every module's signals/facts/gaps, deduplicates, and produces
both the raw Dossier (for the LLM summary step) and the structured
EnrichedDossier (for the collector dashboard).

Cross-references findings: builds a subject profile from scattered signals,
extracts prioritized contact channels, categorizes intelligence items,
and separates real intelligence gaps from technical errors.
"""

from __future__ import annotations

import re

from app.models import (
    ContactChannel,
    Dossier,
    EnrichedDossier,
    IntelligenceItem,
    Signal,
    SubjectProfile,
)
from app.pipeline.base import Context, ModuleResult


# ---------------------------------------------------------------------------
# Signal deduplication
# ---------------------------------------------------------------------------


def _dedupe_signals(signals: list[Signal]) -> list[Signal]:
    """Keep one signal per `(kind, tag, value)`, picking the highest confidence.

    Value comparison is case-insensitive and trim-insensitive; two modules
    reporting "Barcelona, ES" and " barcelona, es " should collapse.
    """
    best: dict[tuple[str, str | None, str], Signal] = {}
    for s in signals:
        key = (s.kind, s.tag, s.value.strip().lower())
        existing = best.get(key)
        if existing is None or s.confidence > existing.confidence:
            best[key] = s
    return list(best.values())


def _is_sentinel(s: Signal) -> bool:
    """True if the signal is a scheduling sentinel, not real data."""
    return s.tag == "enrichment_ran"


def _clean_signals(signals: list[Signal]) -> list[Signal]:
    """Remove scheduling sentinels and dedupe."""
    return _dedupe_signals([s for s in signals if not _is_sentinel(s)])


# ---------------------------------------------------------------------------
# Subject profile assembly
# ---------------------------------------------------------------------------

_TECH_GAP_PATTERNS = [
    re.compile(r"osintgram", re.IGNORECASE),
    re.compile(r"not found at", re.IGNORECASE),
    re.compile(r"hikerapi", re.IGNORECASE),
    re.compile(r"could not parse slug", re.IGNORECASE),
    re.compile(r"venv/bin/python", re.IGNORECASE),
    re.compile(r"reverse-image search not attempted", re.IGNORECASE),
    re.compile(r"missing inputs \[", re.IGNORECASE),
    re.compile(r"skipped:", re.IGNORECASE),
    re.compile(r"returned ambiguous status", re.IGNORECASE),
    re.compile(r"API (key|error)", re.IGNORECASE),
]


def _is_technical_gap(gap: str) -> bool:
    """True if the gap describes a technical/infra issue, not an intel gap."""
    return any(p.search(gap) for p in _TECH_GAP_PATTERNS)


def _build_subject_profile(ctx: Context, signals: list[Signal]) -> SubjectProfile:
    """Assemble a subject profile from the case + accumulated signals."""
    case = ctx.case

    # Primary name from case signals
    name_sig = ctx.best("name")
    primary_name = name_sig.value if name_sig else ""

    # Aliases: other name signals that don't match the primary
    aliases: list[str] = []
    for s in ctx.all("name"):
        if s.value.strip().lower() != primary_name.strip().lower() and s.value not in aliases:
            aliases.append(s.value)

    # Location
    loc_sig = ctx.best("location")
    location = loc_sig.value if loc_sig else None

    # Phones
    phones: list[str] = []
    for s in ctx.all("contact", "phone"):
        v = s.value.strip()
        # Filter out IPs mistakenly tagged as phones
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", v):
            continue
        if v not in phones:
            phones.append(v)

    # Emails
    emails: list[str] = []
    for s in ctx.all("contact", "email"):
        v = s.value.strip()
        if v not in emails:
            emails.append(v)

    # Social handles
    social_tags = ("instagram", "twitter", "linkedin", "github", "facebook", "tiktok")
    social_handles: dict[str, str] = {}
    for tag in social_tags:
        sig = ctx.best("contact", tag)
        if sig:
            social_handles[tag] = sig.value

    return SubjectProfile(
        name=primary_name,
        aliases=aliases,
        location=location,
        country=case.country,
        phones=phones,
        emails=emails,
        social_handles=social_handles,
    )


# ---------------------------------------------------------------------------
# Contact channels
# ---------------------------------------------------------------------------


def _extract_contact_channels(ctx: Context, signals: list[Signal]) -> list[ContactChannel]:
    """Build prioritized contact channels from signals.

    Groups platform registration signals under the identifier they verify.
    """
    channels: list[ContactChannel] = []

    # Phone channels
    for s in ctx.all("contact", "phone"):
        v = s.value.strip()
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", v):
            continue
        verified: list[str] = []
        # Scan all signals for platform verifications of this phone
        for other in signals:
            if other.kind == "contact" and other.value and v in other.value:
                if other.notes and "registered" in other.notes.lower():
                    # Extract platform name from source
                    platform = _platform_from_source(other.source)
                    if platform and platform not in verified:
                        verified.append(platform)
            if other.tag in ("icloud", "uber") and other.value and v in other.value:
                tag_name = other.tag.capitalize()
                if tag_name not in verified:
                    verified.append(tag_name)
        channels.append(ContactChannel(
            channel="phone",
            value=v,
            verified_on=verified,
            confidence=s.confidence,
            notes=s.notes,
        ))

    # Email channels
    for s in ctx.all("contact", "email"):
        v = s.value.strip()
        verified = _find_platform_registrations(v, signals)
        channels.append(ContactChannel(
            channel="email",
            value=v,
            verified_on=verified,
            confidence=s.confidence,
            notes=s.notes,
        ))

    # Social handles as channels
    social_tags = ("instagram", "twitter", "linkedin", "github", "facebook", "tiktok")
    for tag in social_tags:
        sig = ctx.best("contact", tag)
        if sig:
            channels.append(ContactChannel(
                channel=tag,
                value=sig.value,
                verified_on=[tag.capitalize()],
                confidence=sig.confidence,
                notes=sig.notes,
            ))

    # Uber / iCloud / other platform-specific channels
    for tag in ("uber", "icloud"):
        sig = ctx.best("contact", tag)
        if sig and not any(c.value == sig.value for c in channels):
            channels.append(ContactChannel(
                channel=tag,
                value=sig.value,
                verified_on=[tag.capitalize()],
                confidence=sig.confidence,
                notes=sig.notes,
            ))

    # Sort: highest confidence first
    channels.sort(key=lambda c: c.confidence, reverse=True)
    return channels


def _platform_from_source(source: str) -> str | None:
    """Extract a human-readable platform name from a source string."""
    source_lower = source.lower()
    platforms = {
        "github": "GitHub",
        "twitter": "Twitter",
        "instagram": "Instagram",
        "linkedin": "LinkedIn",
        "icloud": "iCloud",
        "uber": "Uber",
        "google_gaia": "Google",
    }
    for key, name in platforms.items():
        if key in source_lower:
            return name
    return None


def _find_platform_registrations(identifier: str, signals: list[Signal]) -> list[str]:
    """Find all platforms where an identifier is confirmed registered."""
    platforms: list[str] = []
    ident_lower = identifier.lower()
    for s in signals:
        if s.kind != "contact":
            continue
        # Platform check signals mention the identifier in their value or notes
        val_lower = (s.value or "").lower()
        notes_lower = (s.notes or "").lower()
        if ident_lower not in val_lower and ident_lower not in notes_lower:
            continue
        if "registered" in notes_lower or "registered" in val_lower:
            p = _platform_from_source(s.source)
            if p and p not in platforms:
                platforms.append(p)
    # Also check for NoSINT-style platform signals
    for s in signals:
        if s.kind == "contact" and s.tag is None and s.notes and "nosint" in s.notes.lower():
            if s.value and "." in s.value:
                # Platform domain like "adobe.com", "kucoin.com"
                name = s.value.split(".")[0].capitalize()
                if name not in platforms:
                    platforms.append(name)
    return platforms


# ---------------------------------------------------------------------------
# Intelligence categorization
# ---------------------------------------------------------------------------

_KIND_TO_CATEGORY: dict[str, str] = {
    "name": "identity",
    "address": "location",
    "location": "location",
    "employer": "employment",
    "role": "employment",
    "business": "employment",
    "asset": "financial",
    "lifestyle": "lifestyle",
    "affiliation": "identity",
    "risk_flag": "risk",
}

# Tags on contact signals that are already handled as channels, skip them
_CHANNEL_TAGS = {
    "phone", "email", "instagram", "twitter", "linkedin", "github",
    "facebook", "tiktok", "uber", "icloud", "enrichment_ran", "gaia_id",
    "email_masked", "photo",
}


def _categorize_intelligence(
    signals: list[Signal], results: list[ModuleResult]
) -> list[IntelligenceItem]:
    """Turn signals and facts into categorized intelligence items."""
    items: list[IntelligenceItem] = []
    seen: set[str] = set()

    for s in signals:
        # Skip contact signals already handled as channels
        if s.kind == "contact" and s.tag in _CHANNEL_TAGS:
            continue
        # Skip contact signals that are just platform registrations
        if s.kind == "contact" and s.tag is None:
            if s.notes and ("nosint" in s.notes.lower() or "sentinel" in s.notes.lower()):
                continue
            if s.value and ("registered" in s.value.lower() or "account" in s.value.lower()):
                continue

        category = _KIND_TO_CATEGORY.get(s.kind, "digital")
        finding = s.value
        if s.notes:
            finding = f"{s.value} — {s.notes}"

        dedup_key = f"{category}:{s.value.strip().lower()}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Is this actionable for a collector?
        actionable = category in ("location", "employment", "financial") and s.confidence >= 0.7

        items.append(IntelligenceItem(
            category=category,
            finding=finding,
            source=s.source,
            confidence=s.confidence,
            actionable=actionable,
        ))

    # Add facts as intelligence items (they don't overlap with signals per convention)
    for r in results:
        for f in r.facts:
            dedup_key = f"fact:{f.claim.strip().lower()}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Categorize facts by keyword heuristic
            cat = "digital"
            claim_lower = f.claim.lower()
            if "breach" in claim_lower or "leak" in claim_lower or "password" in claim_lower:
                cat = "risk"
            elif "platform" in claim_lower or "registered" in claim_lower:
                cat = "digital"
            elif "google maps" in claim_lower or "contributor" in claim_lower:
                cat = "lifestyle"

            items.append(IntelligenceItem(
                category=cat,
                finding=f.claim,
                source=f.source,
                confidence=f.confidence,
                actionable=False,
            ))

    # Sort: actionable first, then by confidence desc
    items.sort(key=lambda x: (not x.actionable, -x.confidence))
    return items


# ---------------------------------------------------------------------------
# Risk flags + platform registrations
# ---------------------------------------------------------------------------


def _extract_risk_flags(signals: list[Signal]) -> list[str]:
    """Collect deduplicated risk flag descriptions."""
    flags: list[str] = []
    for s in signals:
        if s.kind != "risk_flag":
            continue
        desc = s.value
        if s.notes:
            desc = f"{s.value} ({s.notes})"
        if desc not in flags:
            flags.append(desc)
    return flags


def _extract_platform_registrations(signals: list[Signal]) -> list[str]:
    """List platforms where the subject is confirmed registered."""
    platforms: list[str] = []
    for s in signals:
        if s.kind != "contact":
            continue
        # Platform check signals
        if s.notes and "registered" in s.notes.lower():
            p = _platform_from_source(s.source)
            if p and p not in platforms:
                platforms.append(p)
        # NoSINT platform hits
        if s.tag is None and s.notes and "nosint" in s.notes.lower():
            if s.value and "." in s.value:
                name = s.value.split(".")[0].capitalize()
                if name not in platforms:
                    platforms.append(name)
    return platforms


# ---------------------------------------------------------------------------
# Digital footprint assessment
# ---------------------------------------------------------------------------


def _assess_footprint(signals: list[Signal], results: list[ModuleResult]) -> str:
    """Estimate the digital footprint: minimal, moderate, or extensive."""
    contact_count = sum(1 for s in signals if s.kind == "contact" and not _is_sentinel(s))
    lifestyle_count = sum(1 for s in signals if s.kind == "lifestyle")
    ok_modules = sum(1 for r in results if r.status == "ok")

    score = contact_count + lifestyle_count * 2 + ok_modules
    if score >= 15:
        return "extensive"
    if score >= 6:
        return "moderate"
    return "minimal"


# ---------------------------------------------------------------------------
# Case summary
# ---------------------------------------------------------------------------


def _build_case_summary(ctx: Context) -> str:
    """Build a 2-3 line case snapshot from the Case object."""
    case = ctx.case
    parts: list[str] = []

    if case.debt_eur is not None:
        debt = f"€{case.debt_eur:,.2f}"
        origin = case.debt_origin or "unknown origin"
        age = f"{case.debt_age_months} months" if case.debt_age_months else "unknown age"
        parts.append(f"Debt: {debt} ({origin}, {age})")

    if case.call_attempts is not None:
        outcome = case.call_outcome or "unknown"
        parts.append(f"Call history: {case.call_attempts} attempt(s), last outcome: {outcome}")

    if case.legal_asset_finding:
        parts.append(f"Legal asset finding: {case.legal_asset_finding}")

    if not parts:
        parts.append("No case metadata provided.")

    return ". ".join(parts) + "."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def synthesize(ctx: Context, results: list[ModuleResult]) -> Dossier:
    """Produce the raw Dossier — used by llm_summary.py and kept on the response."""
    all_facts = [f for r in results for f in r.facts]
    all_signals = _dedupe_signals([s for r in results for s in r.signals])
    all_gaps = [g for r in results for g in r.gaps]

    summary_parts = [r.summary for r in results if r.status == "ok" and r.summary]
    if summary_parts:
        summary = " ".join(summary_parts)
    else:
        summary = f"No enrichment data recovered for case {ctx.case.case_id}."

    return Dossier(
        summary=summary, facts=all_facts, signals=all_signals, gaps=all_gaps
    )


async def build_enriched_dossier(
    ctx: Context, results: list[ModuleResult]
) -> EnrichedDossier:
    """Produce the structured EnrichedDossier for the collector dashboard.

    Called after synthesize() — reads from ctx.signals (accumulated by the
    runner) and the per-module results.
    """
    signals = _clean_signals([s for r in results for s in r.signals])

    subject = _build_subject_profile(ctx, signals)
    channels = _extract_contact_channels(ctx, signals)
    intelligence = _categorize_intelligence(signals, results)
    risk_flags = _extract_risk_flags(signals)
    platform_regs = _extract_platform_registrations(signals)
    case_summary = _build_case_summary(ctx)
    footprint = _assess_footprint(signals, results)

    # Separate gaps
    all_gaps = [g for r in results for g in r.gaps]
    intel_gaps = [g for g in all_gaps if not _is_technical_gap(g)]
    tech_issues = [g for g in all_gaps if _is_technical_gap(g)]

    # Module coverage
    coverage = {r.name: r.status for r in results}

    return EnrichedDossier(
        subject=subject,
        case_summary=case_summary,
        digital_footprint=footprint,
        contact_channels=channels,
        intelligence=intelligence,
        risk_flags=risk_flags,
        platform_registrations=platform_regs,
        gaps=intel_gaps,
        technical_issues=tech_issues,
        module_coverage=coverage,
    )
