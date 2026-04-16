"""Core abstractions for the enrichment pipeline.

Design in one sentence: each module declares what signal (kind, tag) pairs it
needs; the runner figures out what can run in parallel based on those
declarations. All structured data flows through signals — no separate identity
fields, no ContextPatch.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    Case,
    Fact,
    Signal,
    SocialLink,
)


class Context(BaseModel):
    """Mutable blackboard passed through the pipeline.

    All structured data lives in ``signals``. Modules read prior findings
    via ``best()`` / ``all()`` / ``has()`` and the runner gates scheduling
    via ``requires`` checked against these helpers.
    """

    case: Case
    signals: list[Signal] = Field(default_factory=list)

    def best(self, kind: str, tag: str | None = None) -> Signal | None:
        """Highest-confidence signal matching kind (and tag if given)."""
        matches = self.all(kind, tag)
        return matches[0] if matches else None

    def all(self, kind: str, tag: str | None = None) -> list[Signal]:
        """All signals matching kind+tag, sorted by confidence desc."""
        if tag is None:
            filtered = [s for s in self.signals if s.kind == kind]
        else:
            filtered = [s for s in self.signals if s.kind == kind and s.tag == tag]
        return sorted(filtered, key=lambda s: s.confidence, reverse=True)

    def has(self, kind: str, tag: str | None = None) -> bool:
        """True if at least one signal matches."""
        if tag is None:
            return any(s.kind == kind for s in self.signals)
        return any(s.kind == kind and s.tag == tag for s in self.signals)


def context_from_case(case: Case) -> Context:
    """Seed the Context with the Case's signals."""
    return Context(case=case, signals=list(case.signals))


class ModuleResult(BaseModel):
    """Standard return shape for every module.

    Two channels:
      * Structured — `social_links`, `signals`, `facts`. These carry typed,
        provenance-tagged data that synthesis and downstream modules consume
        programmatically.
      * Unstructured — `summary`, `gaps`, `raw`. Human-readable narrative
        plus a per-module escape hatch for debug exhaust.

    Keeping this uniform is what lets the runner, synthesis, and the API
    response treat every module identically — no special cases.
    """

    # Allow extra fields so that cached results from before the refactor
    # (which carried ctx_patch) still load without validation errors.
    model_config = ConfigDict(extra="ignore")

    name: str
    status: str  # "ok" | "skipped" | "error"
    summary: str = ""
    social_links: list[SocialLink] = []
    facts: list[Fact] = []
    signals: list[Signal] = []
    gaps: list[str] = []
    raw: dict[str, Any] = Field(default_factory=dict)
    duration_s: float = 0.0


@runtime_checkable
class Module(Protocol):
    """Anything with these attributes and an async `run` is a module.

    ``requires`` is a tuple of ``(kind, tag)`` pairs. The runner checks
    ``ctx.has(kind, tag)`` for each pair before scheduling the module.
    """

    name: str
    requires: tuple[tuple[str, str | None], ...]

    async def run(self, ctx: Context) -> ModuleResult: ...
