from fastapi import FastAPI

from app.models import Case, EnrichmentResponse

app = FastAPI(title="Vexor BCN — debtor enrichment")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/enrich", response_model=EnrichmentResponse)
def enrich(case: Case) -> EnrichmentResponse:
    """Accept a case row. Enrichment pipeline is not yet implemented."""
    return EnrichmentResponse(case_id=case.case_id, status="received")
