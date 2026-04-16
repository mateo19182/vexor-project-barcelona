import sys
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query

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


@app.get("/modules")
def modules() -> dict[str, list[dict[str, Any]]]:
    """List every registered module, including its declared `requires`."""
    return {
        "modules": [
            {"name": m.name, "requires": list(m.requires)} for m in REGISTRY
        ]
    }


async def run_enrichment(
    case: Case,
    *,
    fresh: bool | set[str] = False,
    only: set[str] | None = None,
) -> EnrichmentResponse:
    """Core orchestration — run every module against the case and synthesize.

    `fresh`:
      * `False` (default) → reuse every cached module result from prior runs.
      * `True`            → recompute every module (ignore the cache).
      * `{"instagram", …}` → recompute only the named modules.

    `only`:
      * `None` (default) → run every registered module.
      * `{"boe", …}`     → run only the named modules. Unknown names raise
        `ValueError`. Dependencies aren't auto-included — a module whose
        `requires` aren't met comes back `status="skipped"`.
    """
    ctx = context_from_case(case)
    audit = AuditLog()

    if only is None:
        modules = REGISTRY
    else:
        available = {m.name for m in REGISTRY}
        unknown = only - available
        if unknown:
            raise ValueError(
                f"unknown module(s): {sorted(unknown)}. "
                f"available: {sorted(available)}"
            )
        modules = [m for m in REGISTRY if m.name in only]

    results = await run_pipeline(
        ctx,
        modules,
        audit,
        logs_dir=settings.logs_dir,
        fresh=fresh,
    )
    dossier = await synthesize(ctx, results)
    # Skip the LLM summary when running a module subset — it's expensive and
    # a single-module dossier isn't worth summarizing. Full runs still get it.
    llm_summary = None if only is not None else await generate_llm_summary(ctx, dossier)

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
    only: Annotated[list[str] | None, Query()] = None,
) -> EnrichmentResponse:
    """Run registered enrichment modules against the case and synthesize.

    `fresh` mirrors the CLI `--fresh` flag:
      * absent                        → reuse cached results (default)
      * `?fresh=true`                 → recompute every module
      * `?fresh=mod1&fresh=mod2`      → recompute only those modules

    `only` mirrors the CLI `--only` flag:
      * absent                        → run every registered module (default)
      * `?only=mod1&only=mod2`        → run only those modules
    """
    if fresh is None:
        fresh_val: bool | set[str] = False
    elif fresh == ["true"]:
        fresh_val = True
    else:
        fresh_val = set(fresh)

    only_val = set(only) if only else None
    try:
        return await run_enrichment(case, fresh=fresh_val, only=only_val)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/enrich/{module_name}", response_model=EnrichmentResponse)
async def enrich_single(
    module_name: str,
    case: Case,
    fresh: Annotated[bool, Query()] = False,
) -> EnrichmentResponse:
    """Run a single named module. Convenience wrapper around `/enrich?only=…`."""
    try:
        return await run_enrichment(
            case,
            fresh={module_name} if fresh else False,
            only={module_name},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
