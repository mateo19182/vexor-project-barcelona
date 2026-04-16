from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SignalKind = Literal[
    "name",          # subject's name
    "address",       # physical address
    "location",      # current/frequent residence or region
    "employer",      # company or organization affiliation
    "role",          # job title / position
    "business",      # ownership / directorship / self-employment
    "asset",         # bank account, vehicle, property, crypto, etc.
    "lifestyle",     # travel, luxury goods, hobbies — hints at disposable income
    "contact",       # email, phone, handles — use tag to distinguish
    "affiliation",   # clubs, associations, education
    "risk_flag",     # data breach hit, criminal record, sanctions, etc.
]


class Signal(BaseModel):
    """A categorized observation — the single structured data type.

    Every structured finding flows through signals. They accumulate on
    Context so any module can read prior modules' findings. Synthesis
    dedupes by ``(kind, tag, value.lower())``.

    ``value`` should be short and canonical (e.g. ``"Barcelona, ES"``,
    ``"Acme Corp"``). Extra detail goes in ``notes``.

    ``tag`` distinguishes signals within a kind — e.g. ``contact``
    signals use tag to separate email / phone / instagram / linkedin /
    twitter / gaia_id / etc. Most other kinds don't need a tag.
    """

    kind: SignalKind
    value: str = Field(description="Short canonical form, e.g. 'Barcelona, ES' or 'Acme Corp'.")
    source: str = Field(description="Full URL or reference backing the observation.")
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None
    tag: str | None = None


class Case(BaseModel):
    """One row of the Vexor starting dataset — the minimal info a servicer has."""

    case_id: str
    country: str | None = Field(default=None, description="ISO-2 country code, e.g. ES, PT, PL, FR")
    debt_eur: float | None = None
    debt_origin: str | None = Field(default=None, description="e.g. personal_loan, telecom, credit_card")
    debt_age_months: int | None = None
    call_attempts: int | None = None
    call_outcome: str | None = Field(default=None, description="e.g. not_debtor, busy, rings_out, voicemail")
    legal_asset_finding: str | None = Field(default=None, description="e.g. no_assets_found, bank_account")

    # Everything the caller knows about the subject — structured.
    signals: list[Signal] = Field(
        default_factory=list,
        description=(
            "All structured data about the subject arrives as signals. "
            'E.g. [{"kind": "name", "value": "Maria Lopez", '
            '"source": "case_input", "confidence": 1.0}]'
        ),
    )

    # Everything the caller knows — unstructured.
    context: str | None = Field(
        default=None,
        description=(
            "Free-form notes / unstructured context about the debtor. "
            "E.g. 'Debtor mentioned having family in Malaga during the last call.'"
        ),
    )

    # Property metadata (not a signal, used by the property module directly).
    property_sqm: float | None = Field(
        default=None,
        description="Superficie construida aproximada en m2 (si se conoce)",
    )
    property_typology: str | None = Field(
        default=None,
        description="piso, casa, local, etc. — solo metadato; no cambia el modelo aun",
    )


class Fact(BaseModel):
    """A free-text claim extracted from enrichment, tied back to a source.

    Prefer `Signal` when the observation fits a known category — facts are
    for one-off claims that don't map to any `SignalKind`.
    """

    claim: str
    source: str = Field(description="IG post URL, image filename, or caption reference")
    confidence: float = Field(ge=0.0, le=1.0)


class SocialLink(BaseModel):
    """A confirmed (or candidate) social media / professional profile."""

    platform: str
    url: str
    handle: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


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


class LlmSummary(BaseModel):
    """LLM-generated factual summary of the dossier for downstream consumers.

    Just the relevant verified info about the debtor and the case, pulled
    from the full Dossier and condensed by the LLM. No call coaching, no
    suggested phrasing — only facts a consumer (e.g. the voice agent) reads
    as context.
    """

    summary: str = Field(
        description=(
            "Prose summary of who this person is and what the case looks "
            "like — only verified, sourced info. Length scales with dossier "
            "richness."
        )
    )
    key_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Short bullets of concrete facts: debt amount/origin/age, "
            "current location, employer, known handles, prior call history. "
            "One fact per bullet."
        ),
    )


EventKind = Literal[
    "pipeline_started",
    "pipeline_completed",
    "wave_started",
    "module_completed",
    "module_cache_hit",
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
    llm_summary: LlmSummary | None = None
    modules: list[Any] = []
    audit_log: list[AuditEvent] = []
