import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models import Case, EnrichmentResponse
from app.pipeline.audit import AuditLog, write_run_log
from app.pipeline.base import context_from_case
from app.pipeline.modules import REGISTRY
from app.pipeline.runner import run_pipeline
from app.pipeline.llm_summary import generate_llm_summary
from app.pipeline.synthesis import synthesize

app = FastAPI(title="Vexor BCN — debtor enrichment")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/modules")
def modules() -> dict[str, list[dict[str, Any]]]:
    """List every registered module, including its declared `requires`."""
    return {
        "modules": [
            {
                "name": m.name,
                "requires": [
                    f"{kind}:{tag}" if tag else kind
                    for kind, tag in m.requires
                ],
            }
            for m in REGISTRY
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


@app.post("/enrich/stream")
async def enrich_stream(
    case: Case,
    fresh: Annotated[list[str] | None, Query()] = None,
    only: Annotated[list[str] | None, Query()] = None,
) -> StreamingResponse:
    """Run enrichment and stream AuditEvents as SSE, then the full response."""

    if fresh is None:
        fresh_val: bool | set[str] = False
    elif fresh == ["true"]:
        fresh_val = True
    else:
        fresh_val = set(fresh)

    only_val = set(only) if only else None

    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_event(ev_json: str) -> None:
        await queue.put(ev_json)

    async def run_and_finish() -> None:
        try:
            ctx = context_from_case(case)
            audit = AuditLog(on_event=on_event)

            if only_val is not None:
                available = {m.name for m in REGISTRY}
                unknown = only_val - available
                if unknown:
                    await queue.put(None)
                    return
                mods = [m for m in REGISTRY if m.name in only_val]
            else:
                mods = REGISTRY

            results = await run_pipeline(
                ctx, mods, audit, logs_dir=settings.logs_dir, fresh=fresh_val,
            )
            dossier = await synthesize(ctx, results)
            llm_summary = (
                None if only_val is not None
                else await generate_llm_summary(ctx, dossier)
            )
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
                write_run_log(response, settings.logs_dir)
            except OSError:
                pass

            payload = json.dumps(
                {"kind": "result", "data": response.model_dump()},
                ensure_ascii=False,
            )
            await queue.put(f"data: {payload}\n\n")
        except Exception as e:
            err = json.dumps({"kind": "error", "message": str(e)})
            await queue.put(f"data: {err}\n\n")
        finally:
            await queue.put(None)

    async def event_generator():
        task = asyncio.create_task(run_and_finish())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ── Historical run browser ─────────────────────────────────────────────

_RUN_FILE_RE = re.compile(r"^\d{8}T\d{6}Z\.json$")


@app.get("/cases")
def list_cases() -> dict[str, list[dict[str, Any]]]:
    """List every case directory and its timestamped run files."""
    logs = Path(settings.logs_dir)
    if not logs.is_dir():
        return {"cases": []}

    cases: list[dict[str, Any]] = []
    for case_dir in sorted(logs.iterdir()):
        if not case_dir.is_dir():
            continue
        runs = sorted(
            (
                {"timestamp": f.stem, "file": f.name}
                for f in case_dir.iterdir()
                if f.is_file() and _RUN_FILE_RE.match(f.name)
            ),
            key=lambda r: r["timestamp"],
            reverse=True,
        )
        if runs:
            cases.append({"case_id": case_dir.name, "runs": runs})
    return {"cases": cases}


@app.get("/cases/{case_id}/runs/{filename}")
def get_run(case_id: str, filename: str) -> Any:
    """Return a single historical run log as JSON."""
    if not _RUN_FILE_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    path = Path(settings.logs_dir) / case_id / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="run not found")
    return json.loads(path.read_text(encoding="utf-8"))
