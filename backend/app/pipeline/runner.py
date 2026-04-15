"""Wave-based scheduler.

Semantics:
  - A module is "ready" when every name in its `requires` is non-empty on the
    Context.
  - Each wave runs all ready modules concurrently via `asyncio.gather`.
  - After a wave, each result's `ctx_patch` is merged into the Context with a
    confidence-beats rule, potentially unblocking modules for the next wave.
  - If no module is ready and some remain pending, they are emitted with
    `status="skipped"` and an explicit gap — we never silently drop work.
  - If a module raises, we catch it and emit `status="error"` with the
    exception in `gaps`. One bad module doesn't poison the pipeline.

All orchestration events go through the `AuditLog` — nothing goes straight
to stderr here. That keeps the audit trail and the live stream in sync.
"""

from __future__ import annotations

import asyncio
import time

from app.models import ContextPatch
from app.pipeline.audit import AuditLog
from app.pipeline.base import Context, Module, ModuleResult
from app.pipeline.cache import load_cached, save_cached


def _missing_requirements(ctx: Context, module: Module) -> list[str]:
    """Return the names of this module's requirements that aren't yet filled."""
    return [k for k in module.requires if not getattr(ctx, k, None)]


def _apply_patch(
    ctx: Context,
    patch: ContextPatch,
    audit: AuditLog,
    module_name: str,
    wave: int,
) -> None:
    """Merge `patch` into `ctx`, recording one audit event per field touched.

    Rule: an incoming entry overwrites the existing one iff its confidence is
    >= the existing entry's confidence. Ties go to the new writer (later
    modules usually have more evidence). Provenance is always updated.
    """
    for field in ContextPatch.model_fields:
        incoming = getattr(patch, field)
        if incoming is None:
            continue
        existing = ctx.identity_provenance.get(field)
        if existing is not None and existing.confidence > incoming.confidence:
            audit.record(
                "ctx_patch_rejected",
                module=module_name,
                wave=wave,
                message=(
                    f"{field}: kept (conf {existing.confidence:.2f} > "
                    f"incoming {incoming.confidence:.2f})"
                ),
                field=field,
                existing_confidence=existing.confidence,
                existing_source=existing.source,
                incoming_confidence=incoming.confidence,
                incoming_source=incoming.source,
            )
            continue
        setattr(ctx, field, incoming.value)
        ctx.identity_provenance[field] = incoming
        audit.record(
            "ctx_patch_applied",
            module=module_name,
            wave=wave,
            message=f"{field}={incoming.value!r} (conf {incoming.confidence:.2f})",
            field=field,
            value=incoming.value,
            source=incoming.source,
            confidence=incoming.confidence,
        )


async def _run_one(module: Module, ctx: Context) -> ModuleResult:
    t0 = time.monotonic()
    try:
        result = await module.run(ctx)
    except Exception as e:  # noqa: BLE001 — intentional catch-all per module
        return ModuleResult(
            name=module.name,
            status="error",
            gaps=[f"{module.name} raised {type(e).__name__}: {e}"],
            duration_s=time.monotonic() - t0,
        )
    # Runner is authoritative on wall-clock.
    result.duration_s = time.monotonic() - t0
    return result


def _is_fresh(module_name: str, fresh: bool | set[str]) -> bool:
    """True if this module should bypass the cache on this run."""
    if fresh is True:
        return True
    if isinstance(fresh, (set, frozenset)):
        return module_name in fresh
    return False


async def run_pipeline(
    ctx: Context,
    modules: list[Module],
    audit: AuditLog,
    *,
    logs_dir: str | None = None,
    fresh: bool | set[str] = False,
) -> list[ModuleResult]:
    """Run `modules` against `ctx` in waves until every module has a result.

    Caching:
      * When `logs_dir` is provided, each ok/no_data result is saved to
        `{logs_dir}/{case_id}/cache/{module_name}.json` after the wave.
      * On subsequent runs, a cached result is loaded and the module's
        `run(...)` is skipped — unless `fresh=True` (skip cache for all)
        or `fresh={"module_name", ...}` (skip cache for named modules).
      * `ctx_patch` from cached results is still applied, so downstream
        modules see the same context they would after a live run.
    """
    pending: list[Module] = list(modules)
    results: list[ModuleResult] = []
    wave = 0

    audit.record(
        "pipeline_started",
        message=f"starting with {len(modules)} module(s): {[m.name for m in modules]}",
        modules=[m.name for m in modules],
    )

    while pending:
        ready = [m for m in pending if not _missing_requirements(ctx, m)]
        if not ready:
            # Nothing can advance. Emit skipped results for whatever's left.
            for m in pending:
                missing = _missing_requirements(ctx, m)
                audit.record(
                    "module_completed",
                    module=m.name,
                    message=f"skipped — missing inputs {missing}",
                    status="skipped",
                    missing=missing,
                )
                results.append(
                    ModuleResult(
                        name=m.name,
                        status="skipped",
                        gaps=[f"skipped: missing inputs [{', '.join(missing)}]"],
                    )
                )
            break

        wave += 1
        ready_names = [m.name for m in ready]
        audit.record(
            "wave_started",
            wave=wave,
            message=str(ready_names),
            modules=ready_names,
        )

        # Try the cache first. Any module with a fresh hit short-circuits;
        # everyone else runs concurrently alongside.
        cached_by_name: dict[str, ModuleResult] = {}
        to_run: list[Module] = []
        for m in ready:
            if logs_dir is not None and not _is_fresh(m.name, fresh):
                hit = load_cached(logs_dir, ctx.case.case_id, m.name)
                if hit is not None:
                    cached_by_name[m.name] = hit
                    continue
            to_run.append(m)

        live_results = await asyncio.gather(*(_run_one(m, ctx) for m in to_run))
        live_by_name = {m.name: r for m, r in zip(to_run, live_results, strict=True)}

        # Preserve the original `ready` order when merging results so the
        # response mirrors module declaration order, not cache/live split.
        for m in ready:
            pending.remove(m)
            if m.name in cached_by_name:
                r = cached_by_name[m.name]
                results.append(r)
                _apply_patch(ctx, r.ctx_patch, audit, m.name, wave)
                audit.record(
                    "module_cache_hit",
                    module=m.name,
                    wave=wave,
                    message=(
                        f"loaded cached {r.status} "
                        f"({len(r.signals)} signal(s), {len(r.facts)} fact(s), "
                        f"{len(r.gaps)} gap(s))"
                    ),
                    status=r.status,
                    signals=len(r.signals),
                    facts=len(r.facts),
                    gaps=len(r.gaps),
                    cached_duration_s=r.duration_s,
                )
                continue

            r = live_by_name[m.name]
            results.append(r)
            _apply_patch(ctx, r.ctx_patch, audit, m.name, wave)
            audit.record(
                "module_completed",
                module=m.name,
                wave=wave,
                message=(
                    f"{r.status} in {r.duration_s:.2f}s "
                    f"({len(r.signals)} signal(s), {len(r.facts)} fact(s), "
                    f"{len(r.gaps)} gap(s))"
                ),
                status=r.status,
                duration_s=r.duration_s,
                signals=len(r.signals),
                facts=len(r.facts),
                gaps=len(r.gaps),
            )

            # Persist ok/no_data; keep error & skipped out of the cache so
            # the next run retries them.
            if logs_dir is not None and r.status in ("ok", "no_data"):
                save_cached(logs_dir, ctx.case.case_id, r)

    counts = {
        "ok": sum(1 for r in results if r.status == "ok"),
        "error": sum(1 for r in results if r.status == "error"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
    }
    audit.record(
        "pipeline_completed",
        message=(
            f"{counts['ok']} ok, {counts['skipped']} skipped, {counts['error']} error(s)"
        ),
        **counts,
    )
    return results
