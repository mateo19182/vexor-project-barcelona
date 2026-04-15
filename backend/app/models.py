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


class EnrichmentResponse(BaseModel):
    """Placeholder — the shape of the enriched profile is TBD."""

    case_id: str
    status: str = "received"
