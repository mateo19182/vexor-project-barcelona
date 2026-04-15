"""Core abstractions for the enrichment pipeline.

Design in one sentence: each module declares what it needs (`requires`) and
may optionally write back to a shared `Context`; the runner figures out what
can run in parallel based on those declarations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models import Case, Fact, SocialLink


class Context(BaseModel):
    """Mutable blackboard passed through the pipeline.

    Modules READ fields from this object and WRITE back via
    `ModuleResult.ctx_updates`. Identity fields start as whatever the Case
    provided and may be filled in by later resolver modules.
    """

    case: Case
    # Identity fields — extend as new resolvers/enrichers need them.
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    instagram_handle: str | None = None
    linkedin_url: str | None = None


def context_from_case(case: Case) -> Context:
    """Seed the Context with whatever identity info the Case already carries."""
    return Context(
        case=case,
        name=case.name,
        phone=case.phone,
        address=case.address,
        instagram_handle=case.instagram_handle,
    )


class ModuleResult(BaseModel):
    """Standard return shape for every module.

    Keeping this uniform is what lets the runner, synthesis, and the API
    response treat every module identically — no special cases.
    """

    name: str
    status: str  # "ok" | "skipped" | "error"
    summary: str = ""
    social_links: list[SocialLink] = []
    facts: list[Fact] = []
    gaps: list[str] = []
    raw: dict[str, Any] = Field(default_factory=dict)
    # Keys merged back into Context so downstream modules can depend on them.
    ctx_updates: dict[str, Any] = Field(default_factory=dict)
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
