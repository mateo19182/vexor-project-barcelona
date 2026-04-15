import sys
from typing import Annotated

from fastapi import FastAPI, Query

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
async def enrich(
    case: Case,
    fresh: Annotated[list[str] | None, Query()] = None,
) -> EnrichmentResponse:
    """Run every registered enrichment module against the case and synthesize.

    `fresh` mirrors the CLI `--fresh` flag:
      * absent                        → reuse cached results (default)
      * `?fresh=true`                 → recompute every module
      * `?fresh=mod1&fresh=mod2`      → recompute only those modules
    """
    if fresh is None:
        fresh_val: bool | set[str] = False
    elif fresh == ["true"]:
        fresh_val = True
    else:
        fresh_val = set(fresh)
    return await run_enrichment(case, fresh=fresh_val)
