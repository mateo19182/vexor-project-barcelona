# base — Core abstractions

`backend/app/pipeline/base.py`

## Overview

Defines the three fundamental types that every module in the pipeline depends on: `Context`, `ModuleResult`, and the `Module` protocol.

## Context

A mutable blackboard that flows through the entire pipeline run.

```python
class Context(BaseModel):
    case: Case                          # original input
    name, email, phone, address,        # identity fields
    instagram_handle, linkedin_url      # resolved progressively
    identity_provenance: dict[str, AttributedValue]  # who wrote what
```

Modules **read** identity fields directly (e.g. `ctx.name`). They **write** via `ModuleResult.ctx_patch`; the runner merges patches with a confidence-beats rule. The case seed lands with `source="case_input"` and `confidence=1.0` — a downstream patch must beat 1.0 to overwrite.

`context_from_case(case)` seeds a fresh Context from the input Case.

## ModuleResult

Standard return shape for every module. Two output channels:

| Channel | Fields | Purpose |
|---|---|---|
| Structured | `social_links`, `signals`, `facts`, `ctx_patch` | Typed, provenance-tagged data for downstream modules and synthesis |
| Unstructured | `summary`, `gaps`, `raw` | Human-readable narrative + debug exhaust |

`status` is one of `"ok"`, `"skipped"`, or `"error"`.

## Module protocol

```python
class Module(Protocol):
    name: str
    requires: tuple[str, ...]
    async def run(self, ctx: Context) -> ModuleResult: ...
```

Modules are registered as **instances** (not classes) so they can carry their own config. `requires` declares which `Context` fields the module needs — the runner uses this for wave scheduling.
