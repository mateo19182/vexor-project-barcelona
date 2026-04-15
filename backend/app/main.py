from fastapi import FastAPI

from app.enrichment.instagram import enrich_instagram
from app.models import Case, EnrichmentResponse

app = FastAPI(title="Vexor BCN — debtor enrichment")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(case: Case) -> EnrichmentResponse:
    """Accept a case row and run the enrichment pipeline.

    Currently the pipeline has one step: Instagram OSINT (via Osintgram +
    OpenRouter vision). More steps will follow.
    """
    instagram = await enrich_instagram(case) if case.instagram_handle else None
    return EnrichmentResponse(
        case_id=case.case_id,
        status="enriched" if instagram else "received",
        instagram=instagram,
    )
