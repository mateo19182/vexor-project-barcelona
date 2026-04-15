# Pipeline Architecture

How enrichment modules are scheduled, how they share data, and what they emit.

---

## Mental model

The pipeline is built around three ideas:

1. **A shared blackboard (`Context`)** — modules discover identity fields (LinkedIn URL, new emails, Instagram handle...) and write them back for later modules to consume. Writes are typed, confidence-tagged, and non-destructive: a downstream patch can only overwrite an existing field if its confidence is at least as high.

2. **A two-channel output per module (`ModuleResult`)** — every module produces both *structured* output (typed signals, facts, social links, identity patches) consumed programmatically by synthesis and other modules, and *unstructured* output (prose summary, gaps) consumed by the LLM synthesis step and the human reader.

3. **Dependency-ordered wave scheduling** — modules declare which Context fields they need (`requires`). The runner groups modules into waves based on what's currently available on the blackboard, runs each wave concurrently, merges the resulting patches, and advances to the next wave. This gives you parallelism within a wave and correct ordering across waves without any explicit graph wiring.

```
Case (user input)
  │
  ▼
Context  ◄──────────────────────────────────────────────────────────┐
(blackboard, seeded from case)                                      │
  │                                                                 │
  ▼                                                                 │
Runner (wave scheduler)                                   ctx_patch (typed, confidence-tagged)
  │                                                                 │
  ├─ wave 1 ──► [ModuleA, ModuleB]  ──► ModuleResult ──────────────┤
  │                  (concurrent)          (structured + unstructured)
  │                                                                 │
  ├─ wave 2 ──► [ModuleC]           ──► ModuleResult ──────────────┤
  │             (unblocked by wave 1 patches)
  │
  ▼
Synthesis ──► Dossier ──► LlmSummary ──► EnrichmentResponse
```

---

## Context: the shared blackboard

`pipeline/base.py::Context` is the central data structure the runner threads through every module. It has two parts.

### Identity fields (read side)

Flat string fields that modules read directly:

| Field | Set by |
|---|---|
| `name` | Case input, or promoted by any module |
| `email` | Case input, or promoted by any module |
| `phone` | Case input, or promoted by any module |
| `address` | Case input, or promoted by any module |
| `instagram_handle` | Case input, or promoted by any module |
| `linkedin_url` | Discovered — not in the Case; must be promoted by a module |

The `case` field holds the original immutable `Case` object. If a module needs a field from the original input (debt amount, call outcome, etc.) it reads `ctx.case.debt_eur`, not `ctx`.

### Seeding from the Case

`context_from_case()` copies whatever identity fields the Case already provides onto the Context, tagging each with `source="case_input"` and `confidence=1.0`. That confidence ceiling matters: a module-produced patch must also carry `confidence=1.0` to overwrite a user-supplied value — in practice this means user data is treated as ground truth.

### `identity_provenance` (write audit)

Every identity field that has ever been written has a matching entry in `ctx.identity_provenance: dict[str, AttributedValue]`. An `AttributedValue` records `value`, `source` (URL or reference), and `confidence`. This is what makes every resolved field fully auditable — you can always see which module last wrote it and why.

### Writes: `ContextPatch`

Modules never mutate `Context` directly. To propose an update they populate a `ContextPatch` on their `ModuleResult`:

```python
return ModuleResult(
    ...
    ctx_patch=ContextPatch(
        linkedin_url=AttributedValue(
            value="https://linkedin.com/in/janedoe",
            source="https://linkedin.com/in/janedoe",
            confidence=0.85,
        ),
    ),
)
```

The runner applies each field with the **confidence-beats rule** (`runner.py::_apply_patch`):

> An incoming patch for a field is applied iff `incoming.confidence >= existing.confidence`. Ties go to the new writer (later modules typically have more evidence). Both applied and rejected patches are recorded in the audit log.

This matters for three reasons:

- **No silent overwrites.** If two modules disagree on a LinkedIn URL, the one with higher confidence wins and the loser is logged — nothing is silently discarded.
- **Traceable identity.** Every resolved identity field carries a source and confidence score.
- **DAG unblocks naturally.** A downstream module that `requires` a field sees the best version found so far, without any explicit dependency declaration between the two modules.

---

## Module output: `ModuleResult`

Every module — whether it succeeds, errors, or is skipped — returns the same `ModuleResult` shape. This uniformity is what lets the runner, synthesis, and the API response treat all modules identically.

There are two distinct output channels. It's important to keep them separate.

### Structured channel (machine-consumed)

| Field | Type | Who consumes it |
|---|---|---|
| `signals` | `list[Signal]` | Synthesis (deduplicated, ranked, fed to the Dossier) |
| `facts` | `list[Fact]` | Synthesis (concatenated into the Dossier as free-form claims) |
| `social_links` | `list[SocialLink]` | Synthesis and any module that needs confirmed profiles |
| `ctx_patch` | `ContextPatch` | Runner (merged into Context after each wave) |

Every entry in these lists must carry a `source` (URL or explicit reference) and a `confidence` in `[0, 1]`. Nothing goes in here without provenance.

### Unstructured channel (human/LLM-consumed)

| Field | Type | Who consumes it |
|---|---|---|
| `summary` | `str` | Synthesis concatenates `ok`-module summaries into the Dossier prose |
| `gaps` | `list[str]` | Synthesis collects all gaps; the collector reads them to know what couldn't be verified |
| `raw` | `dict[str, Any]` | Debug exhaust only — tool traces, API response counts. Never read by other code |

`gaps` is first-class output, not an error state. A module that found nothing should explain what it tried and why it came up empty. "No Instagram posts found — profile may be private" is a useful gap.

### Bookkeeping fields

- `name` — matches the module's `name` attribute; used in logs and the API response.
- `status` — `"ok"` (ran and returned data), `"error"` (raised or returned an error), `"skipped"` (requirements not met).
- `duration_s` — set by the runner from wall-clock; don't set this yourself.

### The Signal taxonomy

`SignalKind` lives in `app/models.py`. Prefer `Signal` over `Fact` when any kind applies — structured signals are deduplicated and ranked by synthesis; free-form facts are not.

| Kind | Example `value` |
|---|---|
| `location` | `"Barcelona, ES"` |
| `employer` | `"Acme Corp"` |
| `role` | `"Senior Engineer"` |
| `business` | `"Director of Foo SL"` |
| `asset` | `"BMW X5 (plate 1234ABC)"` |
| `lifestyle` | `"Monthly ski trips to Andorra"` |
| `contact` | `"alt email: jd@personal.com"` |
| `affiliation` | `"UPC Barcelona alum"` |
| `risk_flag` | `"Email in HaveIBeenPwned breach (LinkedIn 2021)"` |

Non-negotiable signal rules:
- `value` is a short canonical form — not a sentence. Put context in `notes`.
- Every signal carries a `source` (URL or reference) and a `confidence` in `[0, 1]`.
- If nothing fits a kind, use `Fact` (free-text claim). Still sourced, still scored.

`SocialLink` is separate from `Signal` because it has its own schema (platform, url, handle) and is consumed specifically by social-media enrichers.

---

## How dependencies work

### `requires` references Context fields, not module names

A module's `requires` is a tuple of **Context field names** that must be truthy before the module can run:

```python
class LinkedInModule:
    name = "linkedin"
    requires = ("linkedin_url",)          # waits for ctx.linkedin_url to be set

class OsintWebModule:
    name = "osint_web"
    requires = ("name",)                  # needs ctx.name — provided by the case seed
```

This means dependencies are implicit: `linkedin` doesn't declare "I depend on `osint_web`" — it declares "I need `linkedin_url`". Any module that promotes `linkedin_url` onto the Context will unblock it. This keeps modules decoupled; they don't need to know who produces a field, only that the field exists.

### Wave scheduling

The runner (`pipeline/runner.py::run_pipeline`) executes modules in waves:

```
wave 1: every module whose `requires` are already satisfied on Context
        → these run concurrently via asyncio.gather
        → ctx_patches are merged into Context after the wave completes

wave 2: every module newly unblocked by wave-1 patches
        → same concurrency, same merge

…repeat until all modules have a result or no module can advance
```

If a module's requirements are never met (no module in any prior wave promoted the needed field), it ends as `status="skipped"` with an explicit `gaps` entry listing what was missing. Nothing is silently dropped.

### Worked example

```
REGISTRY = [OsintWebModule, LinkedInModule, InstagramModule]

  OsintWebModule    requires=("name",)               # case provides this
  LinkedInModule    requires=("linkedin_url",)        # osint_web may promote this
  InstagramModule   requires=("instagram_handle",)    # case provides or osint_web promotes

wave 1: [osint_web, instagram]
  osint_web finds a LinkedIn profile at confidence 0.85
    → ctx_patch.linkedin_url applied to Context

wave 2: [linkedin]   ← unblocked by the osint_web patch
```

If `osint_web` had found nothing, `linkedin` would end as `skipped` with `gaps=["skipped: missing inputs [linkedin_url]"]`.

---

## Synthesis

`pipeline/synthesis.py::synthesize()` aggregates all `ModuleResult`s into a `Dossier`:

- **`signals`** — deduplicated by `(kind, value.strip().lower())`, keeping the highest-confidence instance per pair. Two modules reporting `"Barcelona, ES"` collapse to one signal.
- **`facts`** — concatenated as-is.
- **`gaps`** — concatenated as-is.
- **`summary`** — joined from each `ok`-module's `summary` field.

The synthesis output feeds the `LlmSummary` step, which condenses the Dossier into a prose summary and key-fact bullets a downstream consumer (e.g. a voice agent) can read as context.

---

## Audit log

Every run produces `audit_log: list[AuditEvent]` on the `EnrichmentResponse`. The runner emits events through `AuditLog.record()` (`pipeline/audit.py`); each call appends a typed event and streams a formatted line to stderr so live progress is visible during development.

| Kind | When | Key `detail` fields |
|---|---|---|
| `pipeline_started` | Entry to `run_pipeline` | `modules` |
| `wave_started` | Each wave | `modules` |
| `module_completed` | Per-module outcome | `status`, `duration_s`, `signals`, `facts`, `gaps` |
| `module_cache_hit` | Module served from cache | `status`, `signals`, `facts`, `gaps`, `cached_duration_s` |
| `ctx_patch_applied` | A patch field won | `field`, `value`, `source`, `confidence` |
| `ctx_patch_rejected` | A patch field lost | `field`, `existing_confidence`, `incoming_confidence` |
| `pipeline_completed` | Exit from `run_pipeline` | `ok`, `error`, `skipped` |

Every event carries `elapsed_s`, `module` (nullable), `wave` (nullable), and a human-readable `message`.

---

## Module caching

When `logs_dir` is provided, `run_pipeline` persists each `ok` or `no_data` result to `{logs_dir}/{case_id}/cache/{module_name}.json`. On subsequent runs the cached result is loaded and `run()` is skipped — but the `ctx_patch` from the cached result is still applied, so downstream modules see the same context they would after a live run.

Pass `fresh=True` to bypass the cache for all modules, or `fresh={"module_name"}` to bypass it for specific ones.

---

## Adding a new module — checklist

1. Create `app/pipeline/modules/<name>.py` with a class satisfying the `Module` protocol.
2. Declare `requires` as a tuple of Context field names. Only list fields you actually read — over-declaring keeps the module permanently skipped.
3. In `run()`:
   - **Success** → `ModuleResult(status="ok", ...)`. Populate `signals` for anything categorizable; fall back to `facts` for one-offs. Every claim needs a `source` and a `confidence`.
   - **Expected failure** (missing key, private profile, 404) → `ModuleResult(status="error", gaps=[...])`. Don't raise — exceptions are for unexpected errors.
   - **Discovered identity data** (LinkedIn URL, confirmed email) → populate `ctx_patch` with an `AttributedValue`. This is how you unblock downstream modules.
4. Register the instance in `app/pipeline/modules/__init__.py::REGISTRY`.

The runner handles scheduling, concurrency, timing, exception isolation, caching, and provenance logging. Modules do none of that.

---

## Quick reference — where things live

| Thing | File |
|---|---|
| `Case`, `Signal`, `Fact`, `SocialLink`, `AttributedValue`, `ContextPatch`, `Dossier`, `LlmSummary`, `AuditEvent` | `app/models.py` |
| `Context`, `context_from_case`, `ModuleResult`, `Module` protocol | `app/pipeline/base.py` |
| Wave scheduler, `_apply_patch` | `app/pipeline/runner.py` |
| Dossier aggregation + signal dedup | `app/pipeline/synthesis.py` |
| `AuditLog`, `render_summary` | `app/pipeline/audit.py` |
| Module registry | `app/pipeline/modules/__init__.py` |
| Module implementations | `app/pipeline/modules/<name>.py` |
| HTTP entry point | `app/main.py` |
| CLI entry point | `app/cli.py` |
