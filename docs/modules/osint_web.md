# osint_web — OSINT web research

`backend/app/pipeline/modules/osint_web.py`

## Overview

Uses Claude with server-side `web_search` and `web_fetch` tools to build a public profile of a debtor from open web sources. Anthropic runs the agentic search loop server-side inside a single API call; this module receives the interleaved tool-use/result blocks and a final JSON text block.

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

The model runs with `thinking: {"type": "adaptive"}` and a `json_schema` output constraint. If Anthropic's server-side iteration cap fires (`stop_reason=pause_turn`), the module replays the conversation and resumes — up to `MAX_RESUMES=2` times.

Model: `claude-sonnet-4-6`, `max_tokens=16000`.

## ctx_patch promotion

`_derive_ctx_patch` promotes the highest-confidence LinkedIn URL and Instagram handle to `Context` so downstream modules (a future LinkedIn enricher, `instagram`) can consume them in the next wave. Only promotes links with confidence ≥ 0.6.
