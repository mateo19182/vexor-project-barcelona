from fastapi import FastAPI

from app.models import Case, EnrichmentResponse, ModuleResultView
from app.pipeline.audit import AuditLog
from app.pipeline.base import context_from_case
from app.pipeline.modules import REGISTRY
from app.pipeline.runner import run_pipeline
from app.pipeline.synthesis import synthesize

app = FastAPI(title="Vexor BCN — debtor enrichment")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(case: Case) -> EnrichmentResponse:
    """Run every registered enrichment module against the case and synthesize."""
    ctx = context_from_case(case)
    audit = AuditLog()
    results = await run_pipeline(ctx, REGISTRY, audit)
    dossier = await synthesize(ctx, results)

    status = "enriched" if any(r.status == "ok" for r in results) else "no_data"
    return EnrichmentResponse(
        case_id=case.case_id,
        status=status,
        dossier=dossier,
        modules=[ModuleResultView(**r.model_dump()) for r in results],
        audit_log=audit.events,
    )
