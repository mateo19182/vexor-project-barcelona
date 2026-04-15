# Pipeline Architecture

How enrichment modules are scheduled, how they share data, and what they emit.

```
Case (user input)
  │
  ▼
Context (shared blackboard, seeded from case)
  │                                   ▲
  ▼                                   │
Runner (wave scheduler)         ctx_patch (typed, confidence-tagged)
  │                                   │
  ├─► Module A ──► ModuleResult ──────┤
  ├─► Module B ──► ModuleResult ──────┤
  └─► Module C ──► ModuleResult ──────┘
          │
          ▼
    Synthesis  ──► Dossier  ──► EnrichmentResponse
```

There are two distinct data channels and it's important to keep them straight:

1. **Shared state** — the `Context` blackboard. Modules read identity fields (`ctx.name`, `ctx.linkedin_url`, …). Modules write via a typed `ContextPatch` with source + confidence. The runner applies patches with a confidence-beats rule.
2. **Per-module output** — a `ModuleResult` with structured signals (consumed programmatically) and unstructured prose (consumed by synthesis / the human reader).

---

## Context: the shared blackboard

`pipeline/base.py::Context` carries:

| Field | Purpose |
|---|---|
| `case` | The original immutable `Case`. |
| `name`, `email`, `phone`, `address`, `instagram_handle`, `linkedin_url` | Identity fields. Flat strings, read directly. |
| `identity_provenance` | `dict[str, AttributedValue]` — records who last wrote each identity field (source + confidence). |

Seeded fields from the Case land with `source="case_input"`, `confidence=1.0`. That means a patch must beat 1.0 to overwrite user-supplied data — effectively: it can't, unless explicitly set to 1.0 as well.

### Writes: `ContextPatch`

Modules never mutate Context directly. They return a `ContextPatch` on their `ModuleResult`:

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

The runner applies each field with this rule, in `runner.py::_apply_patch`:

> An incoming entry overwrites the existing one iff its `confidence >= existing.confidence`. Ties go to the new writer (later modules tend to carry more evidence). Provenance is always updated.

Why this matters:

- **No silent overwrites.** Two modules finding different LinkedIn URLs won't clobber each other; the stronger one wins and the loser is logged.
- **Auditable identity.** Every resolved field carries where it came from and how sure we were.
- **DAG unblocks naturally.** Downstream modules that `require` a field see the best version found so far.

---

## Module output: `ModuleResult`

Every module — success or failure — returns the same shape. Two channels:

### Structured (programmatic)

| Field | Type | Purpose |
|---|---|---|
| `social_links` | `list[SocialLink]` | Platform + URL + handle + confidence for each confirmed/candidate profile. |
| `signals` | `list[Signal]` | Categorized observations, each with a `kind`. Synthesis can group, dedupe, and prioritize. |
| `facts` | `list[Fact]` | Free-text claims that don't fit a signal kind. Keep small. |
| `ctx_patch` | `ContextPatch` | Identity-field updates for downstream modules. |

### Unstructured (prose)

| Field | Type | Purpose |
|---|---|---|
| `summary` | `str` | 1–4 sentence narrative of what this module found. Fed to the synthesis summary. |
| `gaps` | `list[str]` | What couldn't be determined, caveats, ambiguities left unresolved. |
| `raw` | `dict[str, Any]` | Module-specific debug exhaust (tool traces, counts, IDs). Never read by other code — kept for traceability. |

Plus bookkeeping: `name`, `status` (`ok` / `skipped` / `error`), `duration_s` (set by the runner).

### The Signal taxonomy

`SignalKind` lives in `app/models.py`. Prefer `Signal` over `Fact` whenever any kind applies:

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

Rules, non-negotiable:

- Every signal has a `source` (URL or explicit reference) and a `confidence` in `[0, 1]`.
- `value` is a short canonical form, not a sentence. Put context in `notes`.
- If nothing fits, use `Fact` (free-text claim). Still sourced, still scored.

`SocialLink` is kept separate from `Signal` because it has its own shape (platform, url, handle) and is consumed specifically by social-media enrichers.

---

## Modules and the DAG

### Module contract

Anything with these attributes is a module (`pipeline/base.py::Module`):

```python
class MyModule:
    name: str                   # unique identifier; appears in logs + API response
    requires: tuple[str, ...]   # Context field names that must be truthy before run
    async def run(self, ctx: Context) -> ModuleResult: ...
```

Register an **instance** (not the class — modules may carry config) by appending to `REGISTRY` in `app/pipeline/modules/__init__.py`.

### Wave scheduling

`requires` declares an implicit DAG over Context fields. The runner (`pipeline/runner.py`) executes **waves**:

```
wave 1: run every module whose `requires` are already satisfied
        (by the case-input seeding)
        — all run concurrently via asyncio.gather
wave 2: merge ctx_patches from wave 1; run every module newly unblocked
…
wave N: repeat until either all modules have run, or no module can advance
```

Three per-module outcomes:

| `status` | When | Result shape |
|---|---|---|
| `ok` | `run()` returned normally | Full result. |
| `error` | `run()` raised | Exception type + message in `gaps`. One bad module never poisons the pipeline. |
| `skipped` | No wave ever satisfied its `requires` | `gaps` lists the missing inputs. |

### Worked example

```
REGISTRY = [OsintWebModule, LinkedInModule, InstagramModule]
  OsintWebModule   requires=("name",)           # case provides this
  LinkedInModule   requires=("linkedin_url",)   # osint_web promotes this
  InstagramModule  requires=("instagram_handle",) # case provides or osint_web promotes

wave 1: [osint_web, instagram]   # LinkedIn blocked: no linkedin_url yet
        osint_web finds a LinkedIn profile @ 0.85 confidence
          → ctx_patch.linkedin_url is merged into Context
wave 2: [linkedin]
```

If `osint_web` hadn't found a LinkedIn, `linkedin` would end wave 2 as `skipped` with `gaps=["skipped: missing inputs [linkedin_url]"]`. No silent drop.

---

## Audit log

Every run produces a structured `audit_log: list[AuditEvent]` that ships with `EnrichmentResponse`. The runner records events through `AuditLog.record(...)` (see `pipeline/audit.py`); each call appends a typed event AND streams a formatted line to stderr so dev progress is visible live.

Event kinds (`models.py::EventKind`):

| Kind | When | Key `detail` fields |
|---|---|---|
| `pipeline_started` | Entry to `run_pipeline` | `modules` |
| `wave_started` | Each concurrent wave | `modules` |
| `module_completed` | Per-module outcome | `status`, `duration_s`, `signals`, `facts`, `gaps` |
| `ctx_patch_applied` | A patch field won | `field`, `value`, `source`, `confidence` |
| `ctx_patch_rejected` | A patch field lost to higher existing confidence | `field`, `existing_confidence`, `incoming_confidence` |
| `pipeline_completed` | Exit from `run_pipeline` | `ok`, `error`, `skipped` |

Every event also carries `elapsed_s` (seconds since pipeline start), `module` (nullable), `wave` (nullable), and a human-readable `message`. The CLI renders a compact `render_summary()` block to stderr at end-of-run; consumers of the API can render the full timeline from `response.audit_log`.

## Synthesis

`pipeline/synthesis.py::synthesize()` aggregates all `ModuleResult`s into a `Dossier`:

- `summary` — joined from each `ok` module's `summary`.
- `signals` — deduped by `(kind, value.strip().lower())`, keeping the highest-confidence instance.
- `facts` — concatenated as-is.
- `gaps` — concatenated as-is.

This is a stub; once more modules land it becomes an LLM call that cross-references findings (contradiction flagging, collector-relevance ranking).

---

## Adding a new module — checklist

1. Create `app/pipeline/modules/<name>.py` with a class that satisfies the `Module` protocol.
2. Declare `requires` — the minimum identity fields you actually need. Less is more: over-declaring keeps the module permanently skipped.
3. In `run()`:
   - **Success** → `ModuleResult(status="ok", ...)`. Populate `signals` for anything categorizable; fall back to `facts` only for one-offs. Every claim carries a `source` and a `confidence`.
   - **Expected failure** (missing API key, private profile, HTTP 404) → `ModuleResult(status="error", gaps=[...])`. Don't raise.
   - **Unexpected exceptions** → just let them propagate; the runner catches them and marks the module `error`.
   - If you discovered anything downstream modules could use (a LinkedIn URL, a confirmed email) → populate `ctx_patch` with an `AttributedValue`.
4. Register the instance in `app/pipeline/modules/__init__.py::REGISTRY`.

The runner handles scheduling, concurrency, timing, exception isolation, and provenance logging. You don't.

---

## Quick reference — where things live

| Thing | File |
|---|---|
| `Case`, `Signal`, `Fact`, `SocialLink`, `AttributedValue`, `ContextPatch`, `Dossier`, `AuditEvent` | `app/models.py` |
| `Context`, `ModuleResult`, `Module` protocol | `app/pipeline/base.py` |
| Wave scheduler, `_apply_patch` | `app/pipeline/runner.py` |
| Dossier aggregation + dedup | `app/pipeline/synthesis.py` |
| `AuditLog`, `render_summary` | `app/pipeline/audit.py` |
| Module registry | `app/pipeline/modules/__init__.py` |
| Module implementations | `app/pipeline/modules/<name>.py` |
| HTTP entry point | `app/main.py` |
| CLI entry point | `app/cli.py` (registered as `enrich` in `pyproject.toml`) |
