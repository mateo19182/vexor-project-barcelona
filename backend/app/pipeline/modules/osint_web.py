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

import asyncio
import json
import sys
from typing import Any

import anthropic

from app.config import settings
from app.models import AttributedValue, ContextPatch, Fact, Signal, SocialLink
from app.pipeline.base import Context, ModuleResult

# `exa_py` is only imported when EXA_API_KEY is set. We import lazily inside
# the Exa helper so the module still works without the dep installed.


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000
# Server-side tool loop cap — resume at most once.
MAX_RESUMES = 1
# Client-side Exa tool loop cap — bound cost if Claude keeps calling search.
MAX_EXA_ITERS = 6
# Per-result text truncation sent back in tool_result content, to cap token spend.
EXA_RESULT_TEXT_CHARS = 2000


EXA_TOOLS: list[dict[str, Any]] = [
    {
        "name": "exa_search",
        "description": (
            "Search the public web and retrieve the most relevant URLs with "
            "extracted page text and highlights. Use this as your single "
            "research primitive — one call handles both finding pages and "
            "reading their content. Be specific in queries; include identity "
            "anchors (city, employer, email-domain) when disambiguating a "
            "common name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to perform.",
                },
            },
            "required": ["query"],
        },
    }
]

SYSTEM_PROMPT = """You are an OSINT researcher. Build a public profile of ONE specific person using only open web sources.

Primary objectives — in order of priority:
1. Find social media / professional profiles (LinkedIn, Instagram, Twitter/X, Facebook, GitHub, etc.) that BELONG TO THIS EXACT PERSON.
2. Find background confirmed for this person: current location, employer, job title, business ownership.
3. Note other publicly visible signals about this person: lifestyle, travel, interests, media appearances, public records.

Output channels — use the right one:
- `social_links`: profiles CONFIRMED to belong to the subject (not a namesake).
- `signals`: categorized observations about the subject only:
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
- `facts`: ONLY for one-off claims that don't map to any signal kind. Keep small.
- `gaps`: things you could not determine / ambiguities left unresolved.

Hard rules — non-negotiable:
1. Every claim MUST be backed by a specific URL you actually retrieved. No source = not included.
2. Do NOT infer, speculate, or generalize beyond the evidence.
3. IDENTITY STRICT MATCH: if you find a person who COULD be the subject but you cannot confirm it using the provided identifiers (email, phone, address), OMIT them from ALL output fields — including `summary`. Use `gaps` to note the unresolved ambiguity. Never mention other individuals in the output.
4. `summary` must describe ONLY confirmed findings about the subject. If nothing confirmed was found, write "No confirmed public profiles found for [name] matching the provided identifiers."
5. Prefer 2–3 well-confirmed facts over many speculative ones. Stop early if you have confirmed what you need.
6. Do NOT hallucinate URLs. Only cite URLs from web_search or web_fetch results.
7. Workflow: search → fetch to confirm identity → output only if confirmed. Budget tool calls; stop as soon as you have enough.

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
        "=== SUBJECT ===",
        f"Name: {ctx.name}",
        f"Country: {case.country}",
    ]
    if ctx.email:
        lines.append(f"Email (confirmed): {ctx.email}")
    if ctx.phone:
        lines.append(f"Phone: {ctx.phone}")
    if ctx.address:
        lines.append(f"Address: {ctx.address}")
    if ctx.instagram_handle:
        lines.append(f"Known Instagram: @{ctx.instagram_handle}")
    if ctx.linkedin_url:
        lines.append(f"Known LinkedIn: {ctx.linkedin_url}")

    lines.extend(
        [
            "",
            "=== TASK ===",
            "Find social media profiles and public background for THIS specific person.",
            "Use the email/phone/address above as identity anchors — a profile must match at least one to be included.",
            "If the name is common and you cannot confirm a profile belongs to this person, omit it and note the ambiguity in gaps.",
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


def _format_exa_result(res: Any) -> str:
    """Serialize an Exa `search_and_contents` response into a compact JSON
    string for a `tool_result` block. Truncates each result's `text` so a
    single search doesn't blow the context window.
    """
    out: list[dict[str, Any]] = []
    for r in getattr(res, "results", []) or []:
        text = getattr(r, "text", "") or ""
        out.append(
            {
                "url": getattr(r, "url", "") or "",
                "title": getattr(r, "title", "") or "",
                "published": getattr(r, "published_date", None),
                "author": getattr(r, "author", None),
                "highlights": getattr(r, "highlights", None),
                "text": text[:EXA_RESULT_TEXT_CHARS],
            }
        )
    return json.dumps({"results": out}, ensure_ascii=False)


async def _run_anthropic_web_tools(
    client: anthropic.AsyncAnthropic, ctx: Context
) -> tuple[str, list[str], list[str], str | None]:
    """Drive the investigation using Anthropic's server-side web_search +
    web_fetch tools. Anthropic runs the agentic loop server-side; we only
    replay on `stop_reason=pause_turn`.
    """
    tools = [
        {"type": "web_search_20250305", "name": "web_search"},
        {"type": "web_fetch_20250910", "name": "web_fetch"},
    ]

    user_prompt = _build_user_prompt(ctx)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

    all_blocks: list[Any] = []
    stop_reason: str | None = None

    for attempt in range(MAX_RESUMES + 1):
        async with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        ) as stream:
            response = await stream.get_final_message()

        all_blocks.extend(response.content)
        stop_reason = response.stop_reason
        _log(
            f"[osint_web/anthropic] attempt {attempt + 1}: stop_reason={stop_reason}, "
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
    queries, urls = _extract_tool_trace(all_blocks)
    return final_text, queries, urls, stop_reason


async def _run_exa_tool(
    anthropic_client: anthropic.AsyncAnthropic,
    exa_client: Any,
    ctx: Context,
) -> tuple[str, list[str], list[str], str | None]:
    """Drive the investigation using Exa as a client-side tool. One tool —
    `exa_search` via `search_and_contents` — serves as both search and fetch
    (Exa returns extracted page text alongside URLs). We run a standard
    Anthropic client-side tool loop: while stop_reason=tool_use, execute Exa
    and post a tool_result block; stop when Claude produces its final text.
    """
    user_prompt = _build_user_prompt(ctx)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]

    all_blocks: list[Any] = []
    queries: list[str] = []
    urls: list[str] = []
    stop_reason: str | None = None

    for attempt in range(MAX_EXA_ITERS):
        async with anthropic_client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=EXA_TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        ) as stream:
            response = await stream.get_final_message()

        all_blocks.extend(response.content)
        stop_reason = response.stop_reason
        _log(
            f"[osint_web/exa] attempt {attempt + 1}: stop_reason={stop_reason}, "
            f"{len(response.content)} block(s)"
        )

        if stop_reason != "tool_use":
            break

        # Execute every exa_search tool_use in this turn and collect tool_results.
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if getattr(block, "name", None) != "exa_search":
                continue
            tool_input = getattr(block, "input", {}) or {}
            query = str(tool_input.get("query", "")).strip()
            queries.append(query)
            try:
                # exa_py is synchronous; offload to a thread so we don't
                # block the event loop (other modules may run concurrently).
                exa_result = await asyncio.to_thread(
                    exa_client.search_and_contents,
                    query=query,
                    type="auto",
                    highlights=True,
                )
                for r in getattr(exa_result, "results", []) or []:
                    u = getattr(r, "url", None)
                    if u:
                        urls.append(u)
                content_str = _format_exa_result(exa_result)
                _log(
                    f"[osint_web/exa] search q={query!r} → "
                    f"{len(getattr(exa_result, 'results', []) or [])} result(s)"
                )
            except Exception as e:  # noqa: BLE001 — surface to Claude via tool_result
                _log(f"[osint_web/exa] search q={query!r} errored: {e}")
                content_str = json.dumps({"error": str(e)})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content_str,
                }
            )

        if not tool_results:
            # stop_reason==tool_use but no exa_search blocks — stop defensively.
            break

        # Preserve response.content verbatim — thinking blocks are signed and
        # must round-trip unmodified when tools are enabled.
        messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ]

    final_text = _last_text_block(all_blocks)
    return final_text, queries, urls, stop_reason


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

        backend = "exa" if settings.exa_api_key else "anthropic_web"
        _log(
            f"[osint_web] investigating '{ctx.name}' "
            f"(country={ctx.case.country}, backend={backend})"
        )

        anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        if backend == "exa":
            try:
                from exa_py import Exa
            except ImportError:
                return ModuleResult(
                    name=self.name,
                    status="error",
                    gaps=[
                        "EXA_API_KEY is set but the `exa_py` package is not installed. "
                        "Run `uv sync` in backend/."
                    ],
                )
            exa_client = Exa(api_key=settings.exa_api_key)
            final_text, queries, urls, stop_reason = await _run_exa_tool(
                anthropic_client, exa_client, ctx
            )
        else:
            final_text, queries, urls, stop_reason = await _run_anthropic_web_tools(
                anthropic_client, ctx
            )

        parsed = _loose_json(final_text)

        if not isinstance(parsed, dict):
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=[
                    f"OSINT final block was not JSON (stop_reason={stop_reason}); "
                    f"made {len(queries)} search(es), fetched {len(urls)} URL(s)"
                ],
                raw={
                    "backend": backend,
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
            f"[osint_web] done (backend={backend}): {len(social_links)} link(s), "
            f"{len(signals)} signal(s), {len(facts)} fact(s), {len(gaps)} gap(s), "
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
                "backend": backend,
                "search_queries": queries,
                "fetched_urls": urls,
                "stop_reason": stop_reason,
            },
        )
