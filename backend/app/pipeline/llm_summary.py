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
from typing import Any

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
3. Prefer canonical values ("Barcelona, ES", "Acme Corp", "€1,240 personal loan, 31 months old").
4. `summary`: prose, neutral tone. Cover debtor identity, location, employment/role, lifestyle, and any risk/asset findings that are CONFIRMED for this specific person. Length scales with richness — a thin dossier gets a short summary. Do not pad with speculation, caveats, or information about other people.
5. `key_facts`: short bullets — one confirmed fact per bullet. Omit anything speculative or unconfirmed.
6. Always include the case facts (debt amount, origin, age, country, prior call attempts/outcome, legal asset finding) even if enrichment found nothing.
7. CRITICAL: Never mention other individuals found during research. Only report on the subject.

Output ONLY the structured JSON requested."""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Factual prose summary of debtor + case, length scaled to dossier richness.",
        },
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short bullets — one concrete verified fact each.",
        },
    },
    "required": ["summary", "key_facts"],
    "additionalProperties": False,
}


def _build_user_prompt(ctx: Context, dossier: Dossier) -> str:
    case = ctx.case
    lines = [
        "=== CASE ===",
        f"case_id: {case.case_id}",
        f"country: {case.country}",
        f"debt: €{case.debt_eur:.2f} ({case.debt_origin}, {case.debt_age_months} months old)",
        f"call_history: {case.call_attempts} attempt(s), last outcome: {case.call_outcome}",
        f"legal_asset_finding: {case.legal_asset_finding}",
    ]
    if ctx.name:
        lines.append(f"name: {ctx.name}")
    if ctx.phone:
        lines.append(f"phone: {ctx.phone}")
    if ctx.email:
        lines.append(f"email: {ctx.email}")
    if ctx.address:
        lines.append(f"address: {ctx.address}")
    if ctx.instagram_handle:
        lines.append(f"instagram: @{ctx.instagram_handle}")
    if ctx.linkedin_url:
        lines.append(f"linkedin: {ctx.linkedin_url}")

    lines.append("")
    lines.append("=== DOSSIER ===")
    lines.append(f"summary: {dossier.summary}")

    if dossier.signals:
        lines.append("")
        lines.append("signals:")
        for s in dossier.signals:
            note = f" — {s.notes}" if s.notes else ""
            lines.append(
                f"  [{s.kind}] {s.value} (conf={s.confidence:.2f}){note}"
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
    lines.append("Produce the summary JSON now. Facts only — no coaching.")
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
