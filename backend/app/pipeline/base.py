"""Core abstractions for the enrichment pipeline.

Design in one sentence: each module declares what it needs (`requires`) and
may optionally write back to a shared `Context` via a typed `ContextPatch`;
the runner figures out what can run in parallel based on those declarations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models import (
    AttributedValue,
    Case,
    ContextPatch,
    Fact,
    Signal,
    SocialLink,
)


class Context(BaseModel):
    """Mutable blackboard passed through the pipeline.

    Modules READ identity fields directly (e.g. `ctx.name`). Modules WRITE
    via `ModuleResult.ctx_patch`; the runner merges those patches with a
    confidence-beats rule and records provenance in `identity_provenance`.
    """

    case: Case
    # Identity fields — extend as new resolvers/enrichers need them.
    # Keep these in sync with `ContextPatch` in app/models.py.
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    instagram_handle: str | None = None
    linkedin_url: str | None = None
    # Provenance of each identity field, keyed by field name. Populated as
    # modules write patches; the case seed lands with source="case_input".
    identity_provenance: dict[str, AttributedValue] = Field(default_factory=dict)


def context_from_case(case: Case) -> Context:
    """Seed the Context with whatever identity info the Case already carries.

    Seeded fields get `source="case_input"` and `confidence=1.0` — the user
    supplied them, so downstream patches have to beat 1.0 to overwrite.
    """
    ctx = Context(
        case=case,
        name=case.name,
        phone=case.phone,
        address=case.address,
        instagram_handle=case.instagram_handle,
    )
    for field in ("name", "phone", "address", "instagram_handle"):
        val = getattr(ctx, field)
        if val:
            ctx.identity_provenance[field] = AttributedValue(
                value=val, source="case_input", confidence=1.0
            )
    return ctx


class ModuleResult(BaseModel):
    """Standard return shape for every module.

    Two channels:
      * Structured — `social_links`, `signals`, `facts`, `ctx_patch`. These
        carry typed, provenance-tagged data that synthesis and downstream
        modules consume programmatically.
      * Unstructured — `summary`, `gaps`, `raw`. Human-readable narrative
        plus a per-module escape hatch for debug exhaust.

    Keeping this uniform is what lets the runner, synthesis, and the API
    response treat every module identically — no special cases.
    """

    name: str
    status: str  # "ok" | "skipped" | "error"
    summary: str = ""
    social_links: list[SocialLink] = []
    facts: list[Fact] = []
    signals: list[Signal] = []
    gaps: list[str] = []
    raw: dict[str, Any] = Field(default_factory=dict)
    # Identity-field writes proposed back to Context. The runner merges with
    # a confidence-beats rule — see pipeline/runner.py.
    ctx_patch: ContextPatch = Field(default_factory=ContextPatch)
    duration_s: float = 0.0


@runtime_checkable
class Module(Protocol):
    """Anything with these attributes and an async `run` is a module.

    Modules are registered as *instances* (not classes) so they can carry
    their own config — see `app/pipeline/modules/__init__.py`.
    """

    name: str
    requires: tuple[str, ...]

    async def run(self, ctx: Context) -> ModuleResult: ...
