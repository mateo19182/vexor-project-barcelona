# image_search — reverse image OSINT

`backend/app/pipeline/modules/image_search.py`

## Overview

Uses the subject's Instagram profile picture as a visual fingerprint to surface candidate accounts on other platforms (LinkedIn, X/Twitter, Facebook, GitHub, TikTok, Threads, Reddit, YouTube, Pinterest, Medium, Substack, …). Flow:

1. Resolve `ctx.instagram_handle` → profile-pic URL via the hikerapi `/v1/user/by/username` endpoint.
2. Send that URL to SerpAPI's `google_lens` engine (reverse image search).
3. Classify each `visual_matches[]` entry by domain → platform lookup; extract a handle from the URL path when a conservative regex matches.

```
requires: ("instagram_handle",)
```

Runs in wave ≥2 (same dependency class as `instagram`). The runner schedules it after any wave-1 resolver that might populate the handle.

## Identity-verification caveat

There is **no** same-person check on the matches. Two different people who look alike, or a subject who uses a stock photo, will both produce noisy matches. Everything emitted is therefore:

- hard-capped at `confidence=0.3` on `social_links`, `0.2` on `facts`;
- tagged by an invariant gap line: *"Visual-match results are not identity-verified; manual or LLM same-person check required before trusting any discovered profile."*

Treat every entry as a lead to verify, not ground truth.

## What it finds

| Shape | Source |
|---|---|
| Candidate account on a known platform | Visual match whose domain is in the platform lookup table |
| Other web appearance (blog, news, directory) | Visual match on an un-recognised domain |

## Output

| Field | Type | Description |
|---|---|---|
| `social_links` | `list[SocialLink]` | One per platform-match. `platform`, `url`, optional `handle` parsed from path, `confidence=0.3`. |
| `facts` | `list[Fact]` | One per non-platform match. `claim="Profile picture also appears on: <title>"`, `source=match.url`, `confidence=0.2`. |
| `signals` | `list[Signal]` | Empty. Categorisation of page content needs an LLM pass that this module intentionally skips. |
| `gaps` | `list[str]` | Always contains the identity-unverified warning. Additionally: "No visual matches found" if zero; "Failed to resolve Instagram profile picture URL…" if hikerapi step fails. |
| `ctx_patch` | `ContextPatch` | Always empty — we never promote an unverified match to an identity field. |
| `raw` | `dict` | `provider`, `handle`, `image_url`, `visual_match_count`, `platform_breakdown`, `raw_matches[]`. |

### Recognised platforms

LinkedIn, Twitter (twitter.com + x.com), Facebook (facebook.com + fb.com), Instagram, Threads, TikTok, GitHub, YouTube, Reddit, Pinterest, Medium, Substack, About.me, Behance, Dribbble, Stack Overflow, Quora. Hostname match is suffix-based, so `www.` / `m.` prefixes resolve correctly.

### Handle extraction

Conservative regexes on the URL path only — misparsed handles are worse than no handle. Supported: `linkedin.com/in/<handle>`, `github.com/<handle>`, `x.com/<handle>` (reserved routes filtered), `tiktok.com/@<handle>`, `instagram.com/<handle>`, `medium.com/@<handle>`, `threads.net/@<handle>`, `behance.net/<handle>`, `dribbble.com/<handle>`. Anything else → `handle=None`.

## Hard rules (enforced by parser)

1. Every `SocialLink` and `Fact` carries the match URL as `source`. SerpAPI entries without a `link` field are dropped.
2. `confidence ≤ 0.3` on `social_links`, `≤ 0.2` on `facts` — identity is unverified.
3. The self-match (`instagram.com/<same_handle>`) is filtered out.
4. Zero matches → `status="ok"`, empty outputs, explicit gap.
5. `ctx_patch` is always empty.

## Skips / errors

| Situation | Status | Summary |
|---|---|---|
| `SERPAPI_API_KEY` unset | `skipped` | "Reverse-image search disabled (SERPAPI_API_KEY not set)." |
| `HIKERAPI_TOKEN` unset | `skipped` | "Reverse-image search disabled (HIKERAPI_TOKEN not set)." |
| hikerapi did not return a profile pic URL | `ok` | Empty outputs, gap explains the lookup failed. |
| SerpAPI HTTP / JSON error | `error` | Gap records the status code or exception type. |

## Model

None — no LLM involved. Pure HTTP + regex.

Provider keys: `SERPAPI_API_KEY`, `HIKERAPI_TOKEN` (reused from the Instagram module).
