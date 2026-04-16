import asyncio
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.models import Case, EnrichmentResponse, LeadVerification, Signal
from app.pipeline.audit import AuditLog, write_run_log
from app.pipeline.base import context_from_case
from app.pipeline.modules import REGISTRY
from app.pipeline.runner import run_pipeline
from app.pipeline.llm_summary import generate_llm_summary
from app.pipeline.synthesis import synthesize, build_enriched_dossier

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
    enriched = await build_enriched_dossier(ctx, results)
    # Skip the LLM summary when running a module subset — it's expensive and
    # a single-module dossier isn't worth summarizing. Full runs still get it.
    llm_summary = None if only is not None else await generate_llm_summary(ctx, dossier)

    # Extract lead verification from its module result (if it ran).
    lead_verification = _extract_lead_verification(results)

    status = "enriched" if any(r.status == "ok" for r in results) else "no_data"

    response = EnrichmentResponse(
        case_id=case.case_id,
        status=status,
        dossier=dossier,
        enriched_dossier=enriched,
        llm_summary=llm_summary,
        lead_verification=lead_verification,
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


def _extract_lead_verification(results: list) -> LeadVerification | None:
    """Pull the structured verification report from the lead_verification module."""
    for r in results:
        if getattr(r, "name", None) == "lead_verification" and r.status == "ok":
            v = (r.raw or {}).get("verification")
            if v:
                return LeadVerification(
                    quality=v.get("quality", "unknown"),
                    score=v.get("score", 0.0),
                    summary=v.get("summary", ""),
                    checks=v.get("checks", []),
                    cross_checks=v.get("cross_checks", []),
                )
    return None


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
            enriched = await build_enriched_dossier(ctx, results)
            llm_summary = (
                None if only_val is not None
                else await generate_llm_summary(ctx, dossier)
            )
            status = "enriched" if any(r.status == "ok" for r in results) else "no_data"

            response = EnrichmentResponse(
                case_id=case.case_id,
                status=status,
                dossier=dossier,
                enriched_dossier=enriched,
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


# ── CSV import ────────────────────────────────────────────────────────────


# PII columns → (signal_kind, signal_tag)
_CSV_SIGNAL_COLUMNS: dict[str, tuple[str, str | None]] = {
    "name": ("name", None),
    "email": ("contact", "email"),
    "email_2": ("contact", "email"),
    "phone": ("contact", "phone"),
    "phone_2": ("contact", "phone"),
    "twitter": ("contact", "twitter"),
    "instagram": ("contact", "instagram"),
    "instagram_2": ("contact", "instagram"),
    "linkedin": ("contact", "linkedin"),
    "address": ("address", None),
}


def _row_to_case(row: dict[str, str]) -> Case:
    """Convert one CSV row into a Case with signals."""
    signals: list[Signal] = []
    for col, (kind, tag) in _CSV_SIGNAL_COLUMNS.items():
        val = (row.get(col) or "").strip()
        if not val:
            continue
        signals.append(Signal(
            kind=kind,
            tag=tag,
            value=val,
            source="csv_import",
            confidence=1.0,
        ))

    # Parse numeric/optional Case fields
    def _float(key: str) -> float | None:
        v = (row.get(key) or "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None

    def _int(key: str) -> int | None:
        v = (row.get(key) or "").strip()
        try:
            return int(v) if v else None
        except ValueError:
            return None

    return Case(
        case_id=row.get("case_id", "").strip() or "unknown",
        country=row.get("country", "").strip() or None,
        debt_eur=_float("debt_eur"),
        debt_origin=row.get("debt_origin", "").strip() or None,
        debt_age_months=_int("debt_age_months"),
        call_attempts=_int("call_attempts"),
        call_outcome=row.get("call_outcome", "").strip() or None,
        legal_asset_finding=row.get("legal_asset_finding", "").strip() or None,
        signals=signals,
        context=row.get("context", "").strip() or None,
    )


class CsvBatchResponse(BaseModel):
    total: int
    results: list[EnrichmentResponse]


@app.post("/enrich-csv", response_model=CsvBatchResponse)
async def enrich_csv(
    file: UploadFile,
    fresh: Annotated[bool, Query()] = True,
) -> CsvBatchResponse:
    """Upload a CSV file and enrich every row sequentially.

    The CSV must have a header row. Standard columns (case_id, country,
    debt_eur, …) map to Case fields. PII columns (name, email, phone,
    twitter, instagram, linkedin, address) become input signals.

    Rows are processed one at a time so logs stay readable.
    """
    raw = await file.read()
    text = raw.decode("utf-8-sig")  # handle BOM from Excel exports
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV is empty or has no data rows")

    print(
        f"[csv] processing {len(rows)} lead(s) from {file.filename}",
        file=sys.stderr, flush=True,
    )

    results: list[EnrichmentResponse] = []
    for i, row in enumerate(rows, 1):
        case = _row_to_case(row)
        print(
            f"[csv] ({i}/{len(rows)}) enriching {case.case_id}...",
            file=sys.stderr, flush=True,
        )
        resp = await run_enrichment(case, fresh=fresh)
        results.append(resp)
        print(
            f"[csv] ({i}/{len(rows)}) {case.case_id} → {resp.status}",
            file=sys.stderr, flush=True,
        )

    return CsvBatchResponse(total=len(results), results=results)
