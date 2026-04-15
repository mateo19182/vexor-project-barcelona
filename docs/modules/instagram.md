# instagram — Instagram OSINT

`backend/app/pipeline/modules/instagram.py`

## Overview

Thin adapter that wraps the existing `enrich_instagram` enricher and maps its output into the standard `ModuleResult` shape.

```
requires: ("instagram_handle",)
```

Runs in wave 2+ — it needs `ctx.instagram_handle`, which is either supplied in the original Case or promoted by `osint_web` via `ctx_patch` after wave 1.

## Behavior

1. Takes `ctx.instagram_handle` (preferring whatever a resolver already wrote to Context over the raw Case field).
2. Calls `enrich_instagram(case)` from `app.enrichment.instagram`.
3. Maps the result into `ModuleResult`:

| ModuleResult field | Source |
|---|---|
| `summary` | `ig.summary` |
| `facts` | `ig.facts` |
| `gaps` | `ig.gaps` |
| `raw` | `profile_info`, `raw_captions`, `image_count`, `video_count` |

## Notes

- Does not produce `signals` or `social_links` directly — those come from `osint_web`.
- Does not write a `ctx_patch` — Instagram data doesn't resolve new identity fields.
- If `instagram_handle` is never populated (no handle in Case, none found by osint_web), the runner skips this module and records a gap.
