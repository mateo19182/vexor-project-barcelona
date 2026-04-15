# osint_web — OSINT web research

`backend/app/pipeline/modules/osint_web.py`

## Overview

Builds a public profile of a debtor from open web sources. Supports two retrieval backends, selected automatically via environment:

| Backend | Activated when | How it works |
|---|---|---|
| **Exa** | `EXA_API_KEY` is set | Client-side tool loop: Claude emits `exa_search` tool calls; the module executes `exa.search_and_contents()` and posts results back as `tool_result` blocks. One tool handles both search and content extraction. |
| **Anthropic web tools** | `EXA_API_KEY` absent | Server-side: Anthropic runs the `web_search` + `web_fetch` agentic loop inside a single API call; the module resumes on `pause_turn`. |

The `raw.backend` field on the `ModuleResult` records which path ran (`"exa"` or `"anthropic_web"`).

```
requires: ("name",)
```

Runs in wave 1 (only needs `ctx.name`, always populated from the Case).

## What it finds

Priority order per the system prompt:

1. Social media profiles (LinkedIn, Instagram, Twitter/X, Facebook, TikTok, YouTube, GitHub, etc.)
2. Background: location, employer, job title, business ownership
3. Other signals: lifestyle, travel, interests, media appearances, public records

## Output

| Field | Type | Description |
|---|---|---|
| `social_links` | `list[SocialLink]` | Confirmed profiles with platform, URL, handle, confidence |
| `signals` | `list[Signal]` | Categorized observations (see kinds below) |
| `facts` | `list[Fact]` | One-off claims that don't fit a signal kind |
| `gaps` | `list[str]` | Things not determined or ambiguous |
| `ctx_patch` | `ContextPatch` | Promotes best LinkedIn URL and Instagram handle (≥0.6 confidence) for downstream modules |

### Signal kinds

`location`, `employer`, `role`, `business`, `asset`, `lifestyle`, `contact`, `affiliation`, `risk_flag`

## Hard rules (enforced by system prompt)

- Every claim must be backed by a URL the model actually retrieved.
- No inference beyond the evidence — ambiguity goes in `gaps`.
- "Found nothing" is a valid, explicit answer.
- Workflow: `web_search` to locate candidates, `web_fetch` to confirm attribution before citing.

## Agentic loop handling

Both backends run with `thinking: {"type": "adaptive"}` and a `json_schema` output constraint on the final text block.

**Exa path:** Standard client-side tool loop. Claude emits `tool_use` blocks with `exa_search`; the module executes Exa via `asyncio.to_thread` (sync SDK), posts `tool_result` blocks, and loops until `stop_reason != "tool_use"`. Loop cap: `MAX_EXA_ITERS=6`.

**Anthropic web path:** Server-side loop inside one API call. If Anthropic's iteration cap fires (`stop_reason=pause_turn`), the module replays and resumes — up to `MAX_RESUMES=1` time.

Model: `claude-sonnet-4-6`, `max_tokens=8000`.

## ctx_patch promotion

`_derive_ctx_patch` promotes the highest-confidence LinkedIn URL and Instagram handle to `Context` so downstream modules (a future LinkedIn enricher, `instagram`) can consume them in the next wave. Only promotes links with confidence ≥ 0.6.
