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

    Identity fields (``name``, ``email``, …) hold the best-known value for
    each identifier and gate module scheduling via ``requires``.

    ``signals`` accumulates every structured observation from all modules
    that have already run. Any module can read prior modules' signals — e.g.
    a Companies-House lookup can check for ``employer`` signals from LinkedIn.

    ``identity_provenance`` keeps **all** proposals per identity field (not
    just the winner), so consumers can see every value that was ever proposed.
    """

    case: Case

    # --- Identity fields (best-known value, for module gating) ---
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    instagram_handle: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    gaia_id: str | None = None

    # --- Accumulated structured data from all modules ---
    signals: list[Signal] = Field(default_factory=list)

    # All proposals per identity field (keyed by field name). The primary
    # identity field holds the highest-confidence value; this list keeps
    # every proposal so consumers can see alternatives.
    identity_provenance: dict[str, list[AttributedValue]] = Field(
        default_factory=dict,
    )

    def best_signals(self, kind: str) -> list[Signal]:
        """Return signals of ``kind``, sorted by confidence descending."""
        return sorted(
            (s for s in self.signals if s.kind == kind),
            key=lambda s: s.confidence,
            reverse=True,
        )


_SEEDED_FIELDS = (
    "name",
    "email",
    "phone",
    "address",
    "instagram_handle",
    "twitter_handle",
    "gaia_id",
)


def context_from_case(case: Case) -> Context:
    """Seed the Context with whatever identity info the Case already carries.

    Identity fields get ``source="case_input"`` and ``confidence=1.0``.
    ``case.known_signals`` are injected into ``ctx.signals`` so every module
    sees them from wave 1.
    """
    ctx = Context(
        case=case,
        name=case.name,
        email=case.email,
        phone=case.phone,
        address=case.address,
        instagram_handle=case.instagram_handle,
        twitter_handle=case.twitter_handle,
        gaia_id=case.google_id,
        signals=list(case.known_signals),
    )
    for field in _SEEDED_FIELDS:
        val = getattr(ctx, field)
        if val:
            av = AttributedValue(value=val, source="case_input", confidence=1.0)
            ctx.identity_provenance.setdefault(field, []).append(av)
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
