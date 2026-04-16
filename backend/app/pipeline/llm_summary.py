"""LLM summary generator.

Runs AFTER `synthesize()` — reads the finished Dossier plus the raw case
context and asks Claude to produce a structured factual briefing a human
debt collector reads before placing a call.

This is not a pipeline module (it depends on results, not Context), so it
sits alongside `synthesis.py` rather than in `pipeline/modules/`.

Invariants:
  * Summary contains only facts present in the Dossier — no invention.
  * Signals with low confidence or unresolved gaps are dropped, not hedged.
  * We never tell the voice agent how to behave — we only hand it context.
  * Contradictions between sources are flagged explicitly.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import anthropic

from app.config import settings
from app.models import Dossier, LlmSummary
from app.pipeline.base import Context

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


SYSTEM_PROMPT = """You condense a debtor enrichment dossier into a structured factual briefing for a human debt collector.

You are NOT coaching the collector. Do NOT suggest phrasing, openings, strategy, tone, or what to avoid. Only report verified facts organized for quick consumption.

Rules:
1. Use only facts present in the dossier input. Do not invent or infer.
2. Drop low-confidence or contradictory items silently. Do not hedge ("possibly", "maybe").
3. Prefer canonical values ("Barcelona, ES", "Acme Corp", "€1,240 personal loan, 31 months old").
4. `executive_brief`: 3-5 lines of prose. Cover: who is this person, what the debt looks like, and the most important findings. A collector reads this in 10 seconds to decide their approach. Length scales with richness — a thin dossier gets a short brief.
5. `approach_context`: lifestyle indicators, economic signals, conversational entry points drawn from confirmed data. E.g. "Google Maps reviews suggest familiarity with Barcelona restaurant scene" or "registered on KuCoin (crypto exchange)". Only include if there are real signals — leave empty for thin dossiers.
6. `confidence_level`: "high" if we have employment + location + multiple verified contacts, "moderate" if we have some contacts and partial profile, "low" if mostly just case data and platform registrations.
7. `key_facts`: short bullets — one confirmed fact per bullet. Omit anything speculative.
8. `unanswered_questions`: the 3-5 most important questions a collector would want answered that the enrichment could NOT resolve. E.g. "Current employer unknown", "No confirmed social media presence", "Relationship to Mio Interiors SL unclear".
9. CRITICAL: Flag contradictions between sources explicitly in the brief (e.g. "Twitter @pedroca shows display name 'Pedroca Monteiro' which does not match subject name").
10. CRITICAL: Never mention other individuals found during research unless they are directly relevant to the subject's profile.
11. Always include the case facts (debt amount, origin, age, country, prior call attempts/outcome, legal asset finding) even if enrichment found nothing.

Output ONLY the structured JSON requested."""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_brief": {
            "type": "string",
            "description": (
                "3-5 lines: who this person is, what the debt looks like, "
                "key findings. Readable in 10 seconds."
            ),
        },
        "approach_context": {
            "type": "string",
            "description": (
                "Lifestyle/economic signals and conversational entry points. "
                "Empty string if dossier is thin."
            ),
        },
        "confidence_level": {
            "type": "string",
            "enum": ["high", "moderate", "low"],
            "description": "How much we actually know about this person.",
        },
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short bullets — one concrete verified fact each.",
        },
        "unanswered_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-5 key questions the collector would want answered that "
                "enrichment could not resolve."
            ),
        },
    },
    "required": [
        "executive_brief",
        "approach_context",
        "confidence_level",
        "key_facts",
        "unanswered_questions",
    ],
    "additionalProperties": False,
}


def _build_user_prompt(ctx: Context, dossier: Dossier) -> str:
    case = ctx.case
    lines = [
        "=== CASE ===",
        f"case_id: {case.case_id}",
        f"country: {case.country or 'unknown'}",
        f"debt: {f'€{case.debt_eur:.2f}' if case.debt_eur is not None else 'unknown'} ({case.debt_origin or 'unknown'}, {case.debt_age_months or 'unknown'} months old)",
        f"call_history: {case.call_attempts if case.call_attempts is not None else 'unknown'} attempt(s), last outcome: {case.call_outcome or 'unknown'}",
        f"legal_asset_finding: {case.legal_asset_finding or 'unknown'}",
    ]

    # Surface identity signals from Context
    name_sig = ctx.best("name")
    if name_sig:
        lines.append(f"name: {name_sig.value}")

    phone_sig = ctx.best("contact", "phone")
    if phone_sig:
        lines.append(f"phone: {phone_sig.value}")

    email_sig = ctx.best("contact", "email")
    if email_sig:
        lines.append(f"email: {email_sig.value}")

    address_sig = ctx.best("address")
    if address_sig:
        lines.append(f"address: {address_sig.value}")

    ig_sig = ctx.best("contact", "instagram")
    if ig_sig:
        lines.append(f"instagram: @{ig_sig.value}")

    li_sig = ctx.best("contact", "linkedin")
    if li_sig:
        lines.append(f"linkedin: {li_sig.value}")

    tw_sig = ctx.best("contact", "twitter")
    if tw_sig:
        lines.append(f"twitter: @{tw_sig.value}")

    # Verified contact channels — platforms where identifiers are confirmed
    verified_lines: list[str] = []
    for s in ctx.all("contact"):
        if s.tag == "enrichment_ran":
            continue  # skip scheduling sentinels
        if s.notes and "registered" in s.notes.lower():
            verified_lines.append(f"  {s.value} — {s.notes} (src={s.source})")
        if s.tag in ("uber", "icloud") and s.confidence >= 0.7:
            verified_lines.append(f"  {s.tag}: {s.value} (conf={s.confidence:.2f}, src={s.source})")
    if verified_lines:
        lines.append("")
        lines.append("=== VERIFIED CHANNELS ===")
        lines.extend(verified_lines)

    # Surface high-confidence structured signals accumulated on Context
    profile_kinds = ("employer", "role", "location", "business")
    profile_lines: list[str] = []
    for kind in profile_kinds:
        for s in ctx.all(kind):
            if s.confidence >= 0.70:
                profile_lines.append(f"{s.kind}: {s.value} (conf={s.confidence:.2f}, src={s.source})")
    if profile_lines:
        lines.append("")
        lines.append("=== CONFIRMED PROFILE ===")
        lines.extend(profile_lines)

    # Lifestyle signals — give the LLM context for approach_context
    lifestyle_lines: list[str] = []
    for s in ctx.all("lifestyle"):
        if s.confidence >= 0.60:
            note = f" — {s.notes}" if s.notes else ""
            lifestyle_lines.append(f"  {s.value}{note} (conf={s.confidence:.2f})")
    if lifestyle_lines:
        lines.append("")
        lines.append("=== LIFESTYLE SIGNALS ===")
        lines.extend(lifestyle_lines)

    # Risk flags
    risk_lines: list[str] = []
    for s in ctx.all("risk_flag"):
        note = f" — {s.notes}" if s.notes else ""
        risk_lines.append(f"  {s.value}{note} (conf={s.confidence:.2f}, src={s.source})")
    if risk_lines:
        lines.append("")
        lines.append("=== RISK FLAGS ===")
        lines.extend(risk_lines)

    # Unstructured context from the caller
    if case.context:
        lines.append("")
        lines.append("=== CALLER NOTES ===")
        lines.append(case.context)

    lines.append("")
    lines.append("=== DOSSIER ===")
    # Don't send the raw concatenated summary — send structured signal data instead
    if dossier.signals:
        lines.append("")
        lines.append("signals:")
        for s in dossier.signals:
            # Filter sentinels
            if s.tag == "enrichment_ran":
                continue
            tag_str = f"/{s.tag}" if s.tag else ""
            note = f" — {s.notes}" if s.notes else ""
            lines.append(
                f"  [{s.kind}{tag_str}] {s.value} (conf={s.confidence:.2f}){note}"
            )

    if dossier.facts:
        lines.append("")
        lines.append("facts:")
        for f in dossier.facts:
            lines.append(f"  - {f.claim} (conf={f.confidence:.2f})")

    if dossier.gaps:
        lines.append("")
        lines.append("gaps (use these to inform unanswered_questions):")
        for g in dossier.gaps:
            lines.append(f"  - {g}")

    lines.append("")
    lines.append("Produce the briefing JSON now. Facts only — no coaching.")
    return "\n".join(lines)


def _loose_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


async def generate_llm_summary(
    ctx: Context, dossier: Dossier
) -> LlmSummary | None:
    """Run the LLM over the finished Dossier and return a structured briefing.

    Returns None if the API key is missing or the model fails to return
    valid JSON — the caller treats it as optional, the pipeline is not
    broken by a failed summary.
    """
    if not settings.anthropic_api_key:
        _log("[llm_summary] skipped — anthropic_api_key not configured")
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_prompt = _build_user_prompt(ctx, dossier)

    _log(f"[llm_summary] summarizing dossier for case {ctx.case.case_id}")

    try:
        response = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
            },
        )
    except anthropic.APIError as e:
        _log(f"[llm_summary] API error: {e}")
        return None

    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            break

    parsed = _loose_json(text)
    if not isinstance(parsed, dict):
        _log("[llm_summary] final block was not JSON")
        return None

    executive_brief = str(parsed.get("executive_brief") or "").strip()
    if not executive_brief:
        _log("[llm_summary] empty executive_brief")
        return None

    approach_context = str(parsed.get("approach_context") or "").strip()
    confidence_level = str(parsed.get("confidence_level") or "low").strip()
    if confidence_level not in ("high", "moderate", "low"):
        confidence_level = "low"

    key_facts = [
        str(f).strip()
        for f in (parsed.get("key_facts") or [])
        if str(f).strip()
    ]
    unanswered = [
        str(q).strip()
        for q in (parsed.get("unanswered_questions") or [])
        if str(q).strip()
    ]

    _log(
        f"[llm_summary] done: confidence={confidence_level}, "
        f"{len(key_facts)} fact(s), {len(unanswered)} question(s)"
    )
    return LlmSummary(
        executive_brief=executive_brief,
        approach_context=approach_context,
        confidence_level=confidence_level,
        key_facts=key_facts,
        unanswered_questions=unanswered,
    )
