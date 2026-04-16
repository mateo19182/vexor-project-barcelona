"""LLM summary generator.

Runs AFTER `synthesize()` — reads the finished Dossier plus the raw case
context and asks Claude to produce a factual summary the downstream voice
agent can consume before placing the call.

This is not a pipeline module (it depends on results, not Context), so it
sits alongside `synthesis.py` rather than in `pipeline/modules/`.

Invariants:
  * Summary contains only facts present in the Dossier — no invention.
  * Signals with low confidence or unresolved gaps are dropped, not hedged.
  * We never tell the voice agent how to behave — we only hand it context.
"""

from __future__ import annotations

import json
import sys

import anthropic

from app.config import settings
from app.models import Dossier, LlmSummary
from app.pipeline.base import Context

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


SYSTEM_PROMPT = """You condense a debtor enrichment dossier into a factual summary for a downstream voice agent.

You are NOT coaching the voice agent. Do NOT suggest phrasing, openings, strategy, tone, or what to avoid. Only report verified facts.

Rules:
1. Use only facts present in the dossier input. Do not invent or infer.
2. Drop low-confidence or contradictory items silently. Do not hedge ("possibly", "maybe").
3. Prefer canonical values ("Barcelona, ES", "Acme Corp", "\u20ac1,240 personal loan, 31 months old").
4. `summary`: prose, neutral tone. Cover debtor identity, location, employment/role, lifestyle, and any risk/asset findings that are CONFIRMED for this specific person. Length scales with richness \u2014 a thin dossier gets a short summary. Do not pad with speculation, caveats, or information about other people.
5. `key_facts`: short bullets \u2014 one confirmed fact per bullet. Omit anything speculative or unconfirmed.
6. Always include the case facts (debt amount, origin, age, country, prior call attempts/outcome, legal asset finding) even if enrichment found nothing.
7. CRITICAL: Never mention other individuals found during research. Only report on the subject.

Respond with a JSON object with exactly two keys: "summary" (string) and "key_facts" (array of strings). Output ONLY the JSON — no markdown fences, no other text."""


def _build_user_prompt(ctx: Context, dossier: Dossier) -> str:
    case = ctx.case
    lines = [
        "=== CASE ===",
        f"case_id: {case.case_id}",
        f"country: {case.country or 'unknown'}",
        f"debt: {f'\u20ac{case.debt_eur:.2f}' if case.debt_eur is not None else 'unknown'} ({case.debt_origin or 'unknown'}, {case.debt_age_months or 'unknown'} months old)",
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

    # Surface high-confidence structured signals accumulated on Context
    # so the LLM has confirmed profile data to work with.
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

    # Unstructured context from the caller — free-form notes about the debtor
    # that should inform the summary but aren't structured data.
    if case.context:
        lines.append("")
        lines.append("=== CALLER NOTES ===")
        lines.append(case.context)

    lines.append("")
    lines.append("=== DOSSIER ===")
    lines.append(f"summary: {dossier.summary}")

    if dossier.signals:
        lines.append("")
        lines.append("signals:")
        for s in dossier.signals:
            tag_str = f"/{s.tag}" if s.tag else ""
            note = f" \u2014 {s.notes}" if s.notes else ""
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
        lines.append("gaps (do NOT include in output):")
        for g in dossier.gaps:
            lines.append(f"  - {g}")

    lines.append("")
    lines.append("Produce the summary JSON now. Facts only \u2014 no coaching.")
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
    """Run the LLM over the finished Dossier and return a factual summary.

    Returns None if the API key is missing or the model fails to return
    valid JSON \u2014 the caller treats it as optional, the pipeline is not
    broken by a failed summary.
    """
    if not settings.anthropic_api_key:
        _log("[llm_summary] skipped \u2014 anthropic_api_key not configured")
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

    summary = str(parsed.get("summary") or "").strip()
    key_facts = [
        str(f).strip()
        for f in (parsed.get("key_facts") or [])
        if str(f).strip()
    ]

    if not summary:
        _log("[llm_summary] empty summary")
        return None

    _log(f"[llm_summary] done: {len(key_facts)} key fact(s)")
    return LlmSummary(summary=summary, key_facts=key_facts)
