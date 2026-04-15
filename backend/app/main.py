import sys

from fastapi import FastAPI

from app.config import settings
from app.models import Case, EnrichmentResponse
from app.pipeline.audit import AuditLog, write_run_log
from app.pipeline.base import context_from_case
from app.pipeline.modules import REGISTRY
from app.pipeline.runner import run_pipeline
from app.pipeline.llm_summary import generate_llm_summary
from app.pipeline.synthesis import synthesize

app = FastAPI(title="Vexor BCN — debtor enrichment")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def run_enrichment(
    case: Case, *, fresh: bool | set[str] = False
) -> EnrichmentResponse:
    """Core orchestration — run every module against the case and synthesize.

    `fresh`:
      * `False` (default) → reuse every cached module result from prior runs.
      * `True`            → recompute every module (ignore the cache).
      * `{"instagram", …}` → recompute only the named modules.

    Not the HTTP handler directly (FastAPI can't coerce `set[str]` from a
    query param) — the handler below wraps this with the narrower `bool`
    surface, while the CLI calls in with the full union.
    """
    ctx = context_from_case(case)
    audit = AuditLog()
    results = await run_pipeline(
        ctx,
        REGISTRY,
        audit,
        logs_dir=settings.logs_dir,
        fresh=fresh,
    )
    dossier = await synthesize(ctx, results)
    llm_summary = await generate_llm_summary(ctx, dossier)

    status = "enriched" if any(r.status == "ok" for r in results) else "no_data"
    response = EnrichmentResponse(
        case_id=case.case_id,
        status=status,
        dossier=dossier,
        llm_summary=llm_summary,
        modules=results,
        audit_log=audit.events,
    )

    try:
        log_path = write_run_log(response, settings.logs_dir)
        print(f"[audit] run log → {log_path}", file=sys.stderr, flush=True)
    except OSError as e:
        # Logging must never break the run — degrade gracefully.
        print(f"[audit] failed to write run log: {e}", file=sys.stderr, flush=True)

    return response


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(case: Case, fresh: bool = False) -> EnrichmentResponse:
    """Run every registered enrichment module against the case and synthesize.

    `fresh=true` (query param) bypasses the per-module cache and forces
    every module to recompute. The default reuses cached results from any
    prior run of the same `case_id`. For per-module invalidation use the
    CLI's `--fresh <module>` flag or delete the specific cache file.
    """
    return await run_enrichment(case, fresh=fresh)
