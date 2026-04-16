"""Audit log — structured event stream for one pipeline run.

The runner calls `AuditLog.record(...)` at every meaningful orchestration
step (wave start, module completion, ctx patch application/rejection). Each
call both appends a typed `AuditEvent` to the in-memory list AND streams a
formatted line to stderr so live progress is preserved.

The full event list travels back on `EnrichmentResponse.audit_log`, giving
the API/CLI a replay and letting us render a compact summary at the end.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, PrivateAttr

from app.models import AuditEvent, EnrichmentResponse, EventKind


def _format_stream(ev: AuditEvent) -> str:
    """Single-line render used for live stderr streaming during a run."""
    head = f"[audit +{ev.elapsed_s:5.2f}s] {ev.kind:<22}"
    if ev.module:
        return f"{head} {ev.module}: {ev.message}"
    if ev.wave is not None:
        return f"{head} wave {ev.wave}: {ev.message}"
    return f"{head} {ev.message}"


class AuditLog(BaseModel):
    """Append-only event log for a single pipeline run.

    Not a public API surface — the pipeline constructs one per `enrich()`
    call. The raw events are what travels with the response; `AuditLog`
    itself is the write-side helper.
    """

    model_config = {"arbitrary_types_allowed": True}

    events: list[AuditEvent] = Field(default_factory=list)
    on_event: Callable[[str], Awaitable[None]] | None = Field(
        default=None, exclude=True,
    )
    # Wall-clock anchor for `elapsed_s` on each event. Private so it stays
    # out of serialization and never leaks into the API response.
    _started_at: float = PrivateAttr(default_factory=time.monotonic)

    def record(
        self,
        kind: EventKind,
        *,
        module: str | None = None,
        wave: int | None = None,
        message: str = "",
        stream: bool = True,
        **detail: Any,
    ) -> AuditEvent:
        ev = AuditEvent(
            kind=kind,
            elapsed_s=time.monotonic() - self._started_at,
            module=module,
            wave=wave,
            message=message,
            detail=detail,
        )
        self.events.append(ev)
        if stream:
            print(_format_stream(ev), file=sys.stderr, flush=True)
        if self.on_event is not None:
            sse_line = f"data: {json.dumps(ev.model_dump(), ensure_ascii=False)}\n\n"
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.on_event(sse_line))
            except RuntimeError:
                pass
        return ev


def render_summary(response: EnrichmentResponse) -> str:
    """Compact end-of-run summary for CLI stderr.

    Distinct from the live stream — no replay. Shows status counts, per-module
    timings + output sizes, and what the pipeline wrote back to Context.
    """
    ok = sum(1 for m in response.modules if m.status == "ok")
    err = sum(1 for m in response.modules if m.status == "error")
    skp = sum(1 for m in response.modules if m.status == "skipped")
    total = response.audit_log[-1].elapsed_s if response.audit_log else 0.0

    cached_modules = {
        e.module for e in response.audit_log if e.kind == "module_cache_hit" and e.module
    }

    lines = [
        "",
        "==== enrichment summary ====",
        f"case:    {response.case_id}",
        f"status:  {response.status}  ({ok} ok, {skp} skipped, {err} error(s))",
        f"total:   {total:.2f}s",
        "",
        "modules:",
    ]
    for m in response.modules:
        marker = " (cached)" if m.name in cached_modules else ""
        lines.append(
            f"  {m.name:<14} {m.status:<8} {m.duration_s:>5.2f}s{marker:<9}   "
            f"{len(m.signals):>2} signal(s)  {len(m.facts):>2} fact(s)  "
            f"{len(m.gaps):>2} gap(s)"
        )

    gap_events = [(m.name, g) for m in response.modules for g in m.gaps]
    if gap_events:
        lines.append("")
        lines.append("gaps:")
        for name, g in gap_events:
            lines.append(f"  {name}: {g}")

    return "\n".join(lines)


# Filesystem-safe case_id slug — keep letters/digits/`-`/`_`/`.`, collapse rest.
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(case_id: str) -> str:
    s = _SAFE_SLUG.sub("_", case_id).strip("._-") or "case"
    return s[:128]


def write_run_log(response: EnrichmentResponse, logs_dir: str | Path) -> Path:
    """Persist the full run as JSON at `{logs_dir}/{case_id}/{timestamp}.json`.

    Returns the path written. Timestamp is UTC, filename-safe; the case_id is
    slugged before being used as a directory name. One file per run — re-runs
    of the same case accumulate side-by-side rather than overwriting.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    case_dir = Path(logs_dir) / _slug(response.case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / f"{ts}.json"
    path.write_text(
        json.dumps(response.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
