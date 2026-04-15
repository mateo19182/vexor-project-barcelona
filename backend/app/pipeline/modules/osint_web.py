"""OSINT web-research module.

Uses Claude with the server-side `web_search` and `web_fetch` tools to
investigate a debtor from public sources. Anthropic runs the agentic loop
server-side inside a single API call — we receive interleaved tool-use /
tool-result blocks and a final text block containing structured JSON.

Invariants (enforced by prompt + schema):
  * Every claim carries a source URL.
  * Nothing is inferred beyond the evidence — ambiguity goes in `gaps`.
  * "Found nothing" is a valid answer; we never fabricate.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import anthropic

from app.config import settings
from app.models import AttributedValue, ContextPatch, Fact, Signal, SocialLink
from app.pipeline.base import Context, ModuleResult


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
# Server-side tool loop cap — if Claude hits this, we resume once.
MAX_RESUMES = 2

SYSTEM_PROMPT = """You are an OSINT researcher. Your job is to build a public profile of ONE person using only open web sources.

Primary objectives — in order of priority:
1. Find all social media profiles (LinkedIn, Instagram, Twitter/X, Facebook, TikTok, YouTube, GitHub, etc.) that plausibly belong to this person.
2. Find general background: current location, employer, job title, business ownership, public bio.
3. Note any other publicly visible signals: lifestyle, travel, interests, media appearances, public records.

Output channels — use the right one:
- `social_links`: confirmed social/professional profiles (platform + URL + handle + confidence).
- `signals`: categorized observations. Prefer this over `facts` whenever the claim fits a kind:
    * location  — current/frequent residence (e.g. "Barcelona, ES")
    * employer  — company/organization affiliation
    * role      — job title / position
    * business  — ownership, directorship, self-employment
    * asset     — bank account, vehicle, property, crypto, etc.
    * lifestyle — travel, luxury goods, hobbies (hints at disposable income)
    * contact   — additional phone / email / handle discovered
    * affiliation — clubs, associations, education
    * risk_flag — data breach hit, legal trouble, sanctions
  Each signal has a short canonical `value` (not a sentence), a URL `source`, a `confidence`, and optional `notes`.
- `facts`: ONLY for one-off claims that don't map to any signal kind. Keep this list small.
- `gaps`: things you could not determine / ambiguities left unresolved.

Hard rules — non-negotiable:
1. Every claim you output MUST be backed by a specific URL you actually retrieved. Never state a fact without a source.
2. Do NOT infer, speculate, or generalize beyond the evidence. "Probably X" is not a fact.
3. Be HONEST about ambiguity. Common names are hard — if you cannot confidently attribute a profile to this specific person, flag it as uncertain in `gaps` rather than including it as a fact.
4. Prefer fewer well-sourced claims over many speculative ones.
5. Do NOT hallucinate URLs. Only cite URLs you retrieved with web_search or web_fetch.
6. Workflow: use web_search to locate candidate pages, then web_fetch to confirm the profile belongs to this person before citing it. Budget your tool calls; don't thrash.

Output ONLY the structured JSON in the format requested. No preamble, no commentary."""


SIGNAL_KINDS: tuple[str, ...] = (
    "location",
    "employer",
    "role",
    "business",
    "asset",
    "lifestyle",
    "contact",
    "affiliation",
    "risk_flag",
)


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-4 sentence factual summary of what public OSINT revealed about this person.",
        },
        "social_links": {
            "type": "array",
            "description": "Social media and professional profiles confirmed to belong to this person.",
            "items": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "Platform name, e.g. LinkedIn, Instagram, Twitter, Facebook, GitHub.",
                    },
                    "url": {"type": "string", "description": "Full profile URL."},
                    "handle": {
                        "type": "string",
                        "description": "Username or handle, if visible.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "0-1 confidence this profile belongs to the subject.",
                    },
                },
                "required": ["platform", "url", "confidence"],
                "additionalProperties": False,
            },
        },
        "signals": {
            "type": "array",
            "description": (
                "Categorized observations. Prefer these over `facts` whenever "
                "the claim fits a kind. `value` should be short and canonical "
                "(e.g. 'Barcelona, ES', not a sentence)."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(SIGNAL_KINDS)},
                    "value": {"type": "string"},
                    "source": {
                        "type": "string",
                        "description": "Full URL backing this observation.",
                    },
                    "confidence": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["kind", "value", "source", "confidence"],
                "additionalProperties": False,
            },
        },
        "facts": {
            "type": "array",
            "description": "One-off claims that don't map to any signal kind. Keep small.",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source": {
                        "type": "string",
                        "description": "Full URL of the page that backs this claim.",
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["claim", "source", "confidence"],
                "additionalProperties": False,
            },
        },
        "gaps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things we could not determine or ambiguities left unresolved.",
        },
    },
    "required": ["summary", "social_links", "signals", "facts", "gaps"],
    "additionalProperties": False,
}


def _build_user_prompt(ctx: Context) -> str:
    case = ctx.case
    lines = [
        f"Subject: {ctx.name}",
        f"Country: {case.country}",
    ]
    if ctx.phone:
        lines.append(f"Phone (may be stale): {ctx.phone}")
    if ctx.address:
        lines.append(f"Address (may be stale): {ctx.address}")
    if ctx.email:
        lines.append(f"Email: {ctx.email}")
    if ctx.instagram_handle:
        lines.append(f"Known Instagram: @{ctx.instagram_handle}")
    if ctx.linkedin_url:
        lines.append(f"Known LinkedIn: {ctx.linkedin_url}")

    lines.extend(
        [
            "",
            "Goal: find all social media profiles and build a general public profile for this person.",
            "Use the identifiers above to disambiguate if the name is common.",
            "Investigate via web_search + web_fetch. Return the structured JSON.",
        ]
    )
    return "\n".join(lines)


def _parse_social_links(raw_links: Any) -> list[SocialLink]:
    out: list[SocialLink] = []
    if not isinstance(raw_links, list):
        return out
    for raw in raw_links:
        if not isinstance(raw, dict):
            continue
        platform = str(raw.get("platform", "")).strip()
        url = str(raw.get("url", "")).strip()
        if not platform or not url:
            continue
        handle = str(raw.get("handle", "")).strip() or None
        try:
            confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(
            SocialLink(
                platform=platform,
                url=url,
                handle=handle,
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return out


def _parse_facts(raw_facts: Any) -> list[Fact]:
    out: list[Fact] = []
    if not isinstance(raw_facts, list):
        return out
    for raw in raw_facts:
        if not isinstance(raw, dict):
            continue
        claim = str(raw.get("claim", "")).strip()
        source = str(raw.get("source", "")).strip()
        if not claim or not source:
            continue
        try:
            confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(Fact(claim=claim, source=source, confidence=max(0.0, min(1.0, confidence))))
    return out


def _parse_signals(raw_signals: Any) -> list[Signal]:
    out: list[Signal] = []
    if not isinstance(raw_signals, list):
        return out
    for raw in raw_signals:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "")).strip()
        value = str(raw.get("value", "")).strip()
        source = str(raw.get("source", "")).strip()
        if kind not in SIGNAL_KINDS or not value or not source:
            continue
        try:
            confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        notes = str(raw.get("notes", "")).strip() or None
        out.append(
            Signal(
                kind=kind,  # type: ignore[arg-type]  # validated against SIGNAL_KINDS
                value=value,
                source=source,
                confidence=max(0.0, min(1.0, confidence)),
                notes=notes,
            )
        )
    return out


def _derive_ctx_patch(social_links: list[SocialLink]) -> ContextPatch:
    """Promote the highest-confidence LinkedIn / Instagram finds to the
    shared Context so downstream modules (a dedicated LinkedIn enricher, the
    Instagram OSINT step) can pick them up in the next wave.

    Only promotes links with confidence >= 0.6 to avoid spreading noise.
    """
    patch = ContextPatch()

    def best(platform: str) -> SocialLink | None:
        candidates = [
            sl
            for sl in social_links
            if sl.platform.strip().lower() == platform and sl.confidence >= 0.6
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda sl: sl.confidence)

    li = best("linkedin")
    if li is not None:
        patch.linkedin_url = AttributedValue(
            value=li.url, source=li.url, confidence=li.confidence
        )

    ig = best("instagram")
    if ig is not None and ig.handle:
        patch.instagram_handle = AttributedValue(
            value=ig.handle.lstrip("@"),
            source=ig.url,
            confidence=ig.confidence,
        )

    return patch


def _extract_tool_trace(blocks: list[Any]) -> tuple[list[str], list[str]]:
    """Pull the actual web_search queries and web_fetch URLs Claude issued."""
    queries: list[str] = []
    urls: list[str] = []
    for b in blocks:
        if getattr(b, "type", None) != "server_tool_use":
            continue
        tool_name = getattr(b, "name", "")
        inp = getattr(b, "input", {}) or {}
        if tool_name == "web_search":
            q = inp.get("query")
            if q:
                queries.append(str(q))
        elif tool_name == "web_fetch":
            u = inp.get("url")
            if u:
                urls.append(str(u))
    return queries, urls


def _last_text_block(blocks: list[Any]) -> str:
    """Return the final text block — the structured JSON lives there."""
    for b in reversed(blocks):
        if getattr(b, "type", None) == "text":
            return getattr(b, "text", "") or ""
    return ""


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


class OsintWebModule:
    name = "osint_web"
    requires: tuple[str, ...] = ("name",)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.anthropic_api_key:
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=["anthropic_api_key is not configured"],
            )

        _log(f"[osint_web] investigating '{ctx.name}' (country={ctx.case.country})")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        tools = [
            {"type": "web_search_20250305", "name": "web_search"},
            {"type": "web_fetch_20250910", "name": "web_fetch"},
        ]

        user_prompt = _build_user_prompt(ctx)
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

        all_blocks: list[Any] = []
        stop_reason: str | None = None

        # Server-tool loop: one request usually suffices. If Anthropic's
        # server-side iteration cap is hit (stop_reason=pause_turn), resend
        # to resume — per the SDK docs, no extra "continue" user message.
        for attempt in range(MAX_RESUMES + 1):
            async with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
                },
            ) as stream:
                response = await stream.get_final_message()

            all_blocks.extend(response.content)
            stop_reason = response.stop_reason
            _log(
                f"[osint_web] attempt {attempt + 1}: stop_reason={stop_reason}, "
                f"{len(response.content)} block(s)"
            )
            if stop_reason != "pause_turn":
                break
            # Resume: replay the same user message with the assistant turn appended.
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response.content},
            ]

        final_text = _last_text_block(all_blocks)
        parsed = _loose_json(final_text)
        queries, urls = _extract_tool_trace(all_blocks)

        if not isinstance(parsed, dict):
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=[
                    f"OSINT final block was not JSON (stop_reason={stop_reason}); "
                    f"made {len(queries)} search(es), fetched {len(urls)} URL(s)"
                ],
                raw={
                    "final_text": final_text,
                    "search_queries": queries,
                    "fetched_urls": urls,
                    "stop_reason": stop_reason,
                },
            )

        summary = str(parsed.get("summary") or "").strip()
        social_links = _parse_social_links(parsed.get("social_links"))
        signals = _parse_signals(parsed.get("signals"))
        facts = _parse_facts(parsed.get("facts"))
        gaps = [str(g) for g in (parsed.get("gaps") or []) if g]
        ctx_patch = _derive_ctx_patch(social_links)

        _log(
            f"[osint_web] done: {len(social_links)} link(s), {len(signals)} signal(s), "
            f"{len(facts)} fact(s), {len(gaps)} gap(s), "
            f"{len(queries)} search(es), {len(urls)} fetch(es)"
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            social_links=social_links,
            signals=signals,
            facts=facts,
            gaps=gaps,
            ctx_patch=ctx_patch,
            raw={
                "model": MODEL,
                "search_queries": queries,
                "fetched_urls": urls,
                "stop_reason": stop_reason,
            },
        )
