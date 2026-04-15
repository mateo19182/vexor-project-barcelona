from typing import Any, Literal

from pydantic import BaseModel, Field


class Case(BaseModel):
    """One row of the Vexor starting dataset — the minimal info a servicer has."""

    case_id: str
    country: str = Field(description="ISO-2 country code, e.g. ES, PT, PL, FR")
    debt_eur: float
    debt_origin: str = Field(description="e.g. personal_loan, telecom, credit_card")
    debt_age_months: int
    call_attempts: int
    call_outcome: str = Field(description="e.g. not_debtor, busy, rings_out, voicemail")
    legal_asset_finding: str = Field(description="e.g. no_assets_found, bank_account")

    # Optional real-world hints the user may add for testing (name/phone/address).
    name: str | None = None
    phone: str | None = None
    address: str | None = None

    # Optional Instagram handle for the social-media enrichment step.
    # Resolution from name → handle is out of scope for this step.
    instagram_handle: str | None = None


class Fact(BaseModel):
    """A free-text claim extracted from enrichment, tied back to a source.

    Prefer `Signal` when the observation fits a known category — facts are
    for one-off claims that don't map to any `SignalKind`.
    """

    claim: str
    source: str = Field(description="IG post URL, image filename, or caption reference")
    confidence: float = Field(ge=0.0, le=1.0)


SignalKind = Literal[
    "location",      # current/frequent residence or region
    "employer",      # company or organization affiliation
    "role",          # job title / position
    "business",      # ownership / directorship / self-employment
    "asset",         # bank account, vehicle, property, crypto, etc.
    "lifestyle",     # travel, luxury goods, hobbies — hints at disposable income
    "contact",       # additional phone / email / handle discovered
    "affiliation",   # clubs, associations, education
    "risk_flag",     # data breach hit, criminal record, sanctions, etc.
]


class Signal(BaseModel):
    """A categorized observation. Same provenance contract as Fact, but
    carries a `kind` so synthesis can group, dedupe, and prioritize.
    """

    kind: SignalKind
    value: str = Field(description="Short canonical form, e.g. 'Barcelona, ES' or 'Acme Corp'.")
    source: str = Field(description="Full URL or reference backing the observation.")
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class AttributedValue(BaseModel):
    """A value written to Context, tagged with where it came from and how
    confident the writer is. The runner uses `confidence` to decide whether
    an incoming patch overwrites an existing entry.
    """

    value: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)


class SocialLink(BaseModel):
    """A confirmed (or candidate) social media / professional profile."""

    platform: str
    url: str
    handle: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class ContextPatch(BaseModel):
    """How a module proposes identity-field updates back to Context.

    Each field is optional; only non-None entries are applied. The runner
    merges by confidence — see `pipeline/runner.py::_apply_patch`.
    """

    name: AttributedValue | None = None
    email: AttributedValue | None = None
    phone: AttributedValue | None = None
    address: AttributedValue | None = None
    instagram_handle: AttributedValue | None = None
    linkedin_url: AttributedValue | None = None


class InstagramEnrichment(BaseModel):
    """Output of the Instagram OSINT enrichment step."""

    summary: str
    facts: list[Fact] = []
    gaps: list[str] = []
    raw_captions: list[str] = []
    profile_info: dict | None = None
    image_count: int = 0
    video_count: int = 0  # counted but not analyzed


class Dossier(BaseModel):
    """Synthesized final view across all modules — what a collector reads first."""

    summary: str
    facts: list[Fact] = []
    signals: list[Signal] = []
    gaps: list[str] = []


class ModuleResultView(BaseModel):
    """How a single module's output is surfaced in the API response.

    Mirrors `pipeline.base.ModuleResult` but is declared here so the HTTP
    schema doesn't depend on pipeline internals.
    """

    name: str
    status: str
    summary: str = ""
    social_links: list[SocialLink] = []
    facts: list[Fact] = []
    signals: list[Signal] = []
    gaps: list[str] = []
    raw: dict[str, Any] = Field(default_factory=dict)
    ctx_patch: ContextPatch = Field(default_factory=ContextPatch)
    duration_s: float = 0.0


EventKind = Literal[
    "pipeline_started",
    "pipeline_completed",
    "wave_started",
    "module_completed",
    "ctx_patch_applied",
    "ctx_patch_rejected",
]


class AuditEvent(BaseModel):
    """One structured event emitted by the pipeline orchestrator.

    Lives with the response so frontends / CLIs can render a timeline of the
    run without replaying stderr. `detail` carries event-specific fields
    (field name, confidence numbers, module names, etc.).
    """

    kind: EventKind
    elapsed_s: float = Field(description="Seconds since the pipeline started.")
    module: str | None = None
    wave: int | None = None
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class EnrichmentResponse(BaseModel):
    """Shape of the enriched profile. Grows as pipeline steps are added."""

    case_id: str
    status: str = "received"
    dossier: Dossier | None = None
    modules: list[ModuleResultView] = []
    audit_log: list[AuditEvent] = []
