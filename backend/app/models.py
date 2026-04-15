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
    """A single claim extracted from enrichment, always tied back to a source."""

    claim: str
    source: str = Field(description="IG post URL, image filename, or caption reference")
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


class EnrichmentResponse(BaseModel):
    """Shape of the enriched profile. Grows as pipeline steps are added."""

    case_id: str
    status: str = "received"
    instagram: InstagramEnrichment | None = None
