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

    kind: SignalKind = Field(description="Category of the observation (name, address, contact, etc.)")
    value: str = Field(description="Short canonical form, e.g. 'Barcelona, ES' or 'Acme Corp'.")
    source: str = Field(description="Full URL or reference backing the observation.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0 per the project rubric")
    notes: str | None = Field(default=None, description="Additional detail that doesn't fit in value")
    tag: str | None = Field(default=None, description="Sub-category within kind, e.g. 'email' or 'linkedin' for contact signals")


class Case(BaseModel):
    """One row of the Vexor starting dataset — the minimal info a servicer has."""

    model_config = {"json_schema_extra": {"examples": [{
        "case_id": "DEMO-001",
        "country": "ES",
        "debt_eur": 4500.0,
        "debt_origin": "personal_loan",
        "debt_age_months": 18,
        "call_attempts": 3,
        "call_outcome": "voicemail",
        "signals": [
            {"kind": "name", "value": "Maria Lopez Garcia", "source": "case_input", "confidence": 1.0},
            {"kind": "contact", "tag": "email", "value": "maria.lopez@gmail.com", "source": "case_input", "confidence": 1.0},
        ],
        "context": "Debtor mentioned family in Malaga during last call",
    }]}}

    case_id: str = Field(description="Unique identifier for this debtor case")
    country: str | None = Field(default=None, description="ISO-2 country code, e.g. ES, PT, PL, FR")
    debt_eur: float | None = Field(default=None, description="Outstanding debt amount in euros")
    debt_origin: str | None = Field(default=None, description="e.g. personal_loan, telecom, credit_card")
    debt_age_months: int | None = Field(default=None, description="Age of the debt in months")
    call_attempts: int | None = Field(default=None, description="Number of collection call attempts")
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

    claim: str = Field(description="Free-text factual claim")
    source: str = Field(description="IG post URL, image filename, or caption reference")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")


class SocialLink(BaseModel):
    """A confirmed (or candidate) social media / professional profile."""

    platform: str = Field(description="Social media platform name (instagram, linkedin, twitter, etc.)")
    url: str = Field(description="Full URL to the profile")
    handle: str | None = Field(default=None, description="Username or handle on the platform")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that this profile belongs to the subject")


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

    Structured for a human collector: executive brief, approach context,
    confidence assessment, key facts, and unanswered questions.
    """

    executive_brief: str = Field(
        description=(
            "3-5 lines: who this person is, what the debt looks like, "
            "and what we know. Readable in 10 seconds."
        )
    )
    approach_context: str = Field(
        default="",
        description=(
            "Relevant context for the call: lifestyle indicators, economic "
            "signals, conversational entry points. Facts only."
        ),
    )
    confidence_level: str = Field(
        default="low",
        description="How much we actually know: high, moderate, or low.",
    )
    key_facts: list[str] = Field(
        default_factory=list,
        description=(
            "Short bullets of concrete facts: debt amount/origin/age, "
            "current location, employer, known handles, prior call history. "
            "One fact per bullet."
        ),
    )
    unanswered_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Key questions a collector would want answered that the "
            "enrichment could not resolve."
        ),
    )

    # Backward compat: expose a flat `summary` for anything that reads it.
    @property
    def summary(self) -> str:
        return self.executive_brief


# ---------------------------------------------------------------------------
# Enriched Dossier — structured output for the collector dashboard
# ---------------------------------------------------------------------------


class SubjectProfile(BaseModel):
    """Confirmed identity of the subject, assembled from signals."""

    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    location: str | None = None
    country: str | None = None
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    social_handles: dict[str, str] = Field(
        default_factory=dict,
        description="platform -> handle, e.g. {'github': 'pedroko22'}",
    )


class ContactChannel(BaseModel):
    """A prioritized contact channel for the collector."""

    channel: str = Field(description="phone, email, instagram, twitter, etc.")
    value: str
    verified_on: list[str] = Field(
        default_factory=list,
        description="Platforms where this identifier is confirmed registered.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class IntelligenceItem(BaseModel):
    """A categorized intelligence finding."""

    category: str = Field(
        description="identity, location, employment, lifestyle, financial, digital, risk"
    )
    finding: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    actionable: bool = Field(
        default=False,
        description="Whether the collector can act on this finding.",
    )


class EnrichedDossier(BaseModel):
    """What the collector sees — prioritized and actionable.

    Replaces the flat Dossier as the primary frontend payload. The raw
    Dossier is still kept internally for the LLM summary step.
    """

    subject: SubjectProfile
    case_summary: str = Field(description="2-3 lines: debt + history snapshot.")
    digital_footprint: str = Field(
        default="minimal",
        description="minimal, moderate, or extensive.",
    )
    contact_channels: list[ContactChannel] = Field(default_factory=list)
    intelligence: list[IntelligenceItem] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    platform_registrations: list[str] = Field(
        default_factory=list,
        description="Platforms the subject is confirmed registered on.",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Intelligence gaps — what we couldn't find out.",
    )
    technical_issues: list[str] = Field(
        default_factory=list,
        description="Infra / module errors — not shown prominently.",
    )
    module_coverage: dict[str, str] = Field(
        default_factory=dict,
        description="module_name -> status (ok/error/skipped/no_data).",
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


class LeadVerification(BaseModel):
    """Structured assessment of whether the lead's contact data is current.

    Built by comparing known emails/phones against masked versions returned
    by platform-check APIs (Twitter VU, Uber Hint).
    """

    quality: str = Field(
        description="Overall quality grade: high, medium, low, unknown"
    )
    score: float = Field(
        ge=0.0, le=1.0,
        description="Numeric quality score (0–1)",
    )
    summary: str = Field(description="Human-readable verification summary")
    checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-field verification: each entry has field, input, matches "
            "(platform + mask + result + reason), and verdict"
        ),
    )
    cross_checks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Cross-channel verifications (email→phone, phone→email)",
    )


class EnrichmentResponse(BaseModel):
    """Shape of the enriched profile. Grows as pipeline steps are added."""

    case_id: str = Field(description="Case identifier from the input")
    status: str = Field(default="received", description="Pipeline result: received, enriched, or no_data")
    dossier: Dossier | None = None
    enriched_dossier: EnrichedDossier | None = None
    llm_summary: LlmSummary | None = None
    lead_verification: LeadVerification | None = None
    modules: list[Any] = Field(default_factory=list, description="Per-module results with signals, facts, and metadata")
    audit_log: list[AuditEvent] = Field(default_factory=list)


class CsvBatchResponse(BaseModel):
    """Response from batch CSV enrichment."""

    total: int = Field(description="Number of rows processed")
    results: list[EnrichmentResponse] = Field(description="Enrichment results, one per CSV row")
