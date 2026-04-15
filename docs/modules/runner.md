# runner — Wave-based scheduler

`backend/app/pipeline/runner.py`

## Overview

Orchestrates pipeline execution using a **wave model**: each wave runs all modules whose `requires` are satisfied concurrently, merges their `ctx_patch` writes back into `Context`, then checks whether newly resolved identity fields unlock additional modules for the next wave.

## How waves work

```
pending = all modules

while pending:
    ready = [m for m in pending if all ctx[req] is set for req in m.requires]
    if not ready:
        emit remaining as status="skipped"
        break
    wave_results = await asyncio.gather(*[run(m) for m in ready])
    for each result:
        merge ctx_patch into ctx   ← may unblock next-wave modules
        append result
```

This means `osint_web` (requires `name`) runs in wave 1. If it discovers an Instagram handle and writes it to `ctx_patch`, the `instagram` module (requires `instagram_handle`) becomes ready and runs in wave 2 — even if the Case didn't supply a handle.

## ctx_patch merge rule

`_apply_patch` applies a confidence-beats rule per field:

- If no existing entry → write unconditionally.
- If incoming confidence **≥** existing → overwrite (ties go to the newer writer).
- If incoming confidence **<** existing → reject and record a `ctx_patch_rejected` audit event.

Every field touched (applied or rejected) is recorded in the `AuditLog`.

## Error handling

`_run_one` wraps each module invocation in a `try/except`. If a module raises, it gets `status="error"` with the exception in `gaps` — one bad module never poisons the rest of the pipeline.

## Skipped modules

If a module's `requires` are never filled (e.g. no Instagram handle found and none in the Case), it exits with `status="skipped"` and `gaps=["skipped: missing inputs [...]"]`.
