from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Case(BaseModel):
    """One row of the Vexor starting dataset — the minimal info a servicer has."""

    model_config = ConfigDict(populate_by_name=True)

    case_id: str
    country: str = Field(description="ISO-2 country code, e.g. ES, PT, PL, FR")
    debt_eur: float
    debt_origin: str = Field(description="e.g. personal_loan, telecom, credit_card")
    debt_age_months: int
    call_attempts: int
    call_outcome: str = Field(description="e.g. not_debtor, busy, rings_out, voicemail")
    legal_asset_finding: str = Field(description="e.g. no_assets_found, bank_account")

    # Optional real-world hints the user may add for testing.
    # Accepts both canonical field names and common CSV/API aliases.
    name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("name", "full_name"),
    )
    phone: str | None = Field(
        default=None,
        validation_alias=AliasChoices("phone", "phone_number"),
    )
    address: str | None = None
    email: str | None = None
    tax_id: str | None = None

    # Optional Instagram handle for the social-media enrichment step.
    # Resolution from name → handle is out of scope for this step.
    instagram_handle: str | None = None

    # Optional — mejora la estimación de valor total si hay banda €/m²
    property_sqm: float | None = Field(
        default=None,
        description="Superficie construida aproximada en m² (si se conoce)",
    )
    property_typology: str | None = Field(
        default=None,
        description="piso, casa, local, etc. — solo metadato; no cambia el modelo aún",
    )


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


class SourceCitation(BaseModel):
    title: str
    url: str
    retrieved_at: str = Field(description="ISO-8601 UTC instant of fetch")
    note: str | None = None


class GeocodeHit(BaseModel):
    display_name: str | None = None
    lat: str | None = None
    lon: str | None = None
    road: str | None = None
    house_number: str | None = None
    postcode: str | None = None
    suburb: str | None = None
    city_district: str | None = None
    city: str | None = None
    state: str | None = None
    country_code: str | None = None
    nominatim_place_id: int | None = None
    licence: str | None = None


class MoneyBand(BaseModel):
    min_eur: float
    max_eur: float
    currency: str = "EUR"
    basis: str = Field(description="Qué supuestos enlazan esta banda con las fuentes")


class PropertyEstimate(BaseModel):
    """Salida trazable: bandas, fuentes y lagunas — no cifra única sin contexto."""

    disclaimer: str
    geocode: GeocodeHit | None = None
    offer_price_eur_m2_band: MoneyBand | None = Field(
        default=None,
        description="Banda €/m² (oferta segunda mano) cuando aplica fuente local + HPI",
    )
    sale_value: MoneyBand | None = Field(
        default=None,
        description="Banda valor venta si hay €/m² y property_sqm",
    )
    rent_monthly: MoneyBand | None = Field(
        default=None,
        description="Reservado — sin fuente abierta integrada en esta versión",
    )
    macro_hpi_note: str | None = Field(
        default=None,
        description="Contexto índice precios vivienda país (Eurostat), no precio de la finca",
    )
    methodology: str | None = None
    sources: list[SourceCitation] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class EnrichmentResponse(BaseModel):
    """Shape of the enriched profile. Grows as pipeline steps are added."""

    case_id: str
    status: str = "received"
    dossier: Dossier | None = None
    llm_summary: LlmSummary | None = None
    modules: list[Any] = []
    audit_log: list[AuditEvent] = []
    property_estimate: PropertyEstimate | None = None
