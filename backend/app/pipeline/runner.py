"""Wave-based scheduler.

Semantics:
  - A module is "ready" when every name in its `requires` is non-empty on the
    Context.
  - Each wave runs all ready modules concurrently via `asyncio.gather`.
  - After a wave, `ctx_updates` from its results are merged into the Context,
    potentially unblocking modules for the next wave.
  - If no module is ready and some remain pending, they are emitted with
    `status="skipped"` and an explicit gap — we never silently drop work.
  - If a module raises, we catch it and emit `status="error"` with the
    exception in `gaps`. One bad module doesn't poison the pipeline.
"""

from __future__ import annotations

import asyncio
import sys
import time

from app.pipeline.base import Context, Module, ModuleResult


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _missing_requirements(ctx: Context, module: Module) -> list[str]:
    """Return the names of this module's requirements that aren't yet filled."""
    return [k for k in module.requires if not getattr(ctx, k, None)]


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


async def run_pipeline(
    ctx: Context, modules: list[Module]
) -> list[ModuleResult]:
    """Run `modules` against `ctx` in waves until every module has a result."""
    pending: list[Module] = list(modules)
    results: list[ModuleResult] = []
    wave = 0

    while pending:
        ready = [m for m in pending if not _missing_requirements(ctx, m)]
        if not ready:
            # Nothing can advance. Emit skipped results for whatever's left.
            for m in pending:
                missing = _missing_requirements(ctx, m)
                _log(f"[pipeline] '{m.name}' skipped — missing: {missing}")
                results.append(
                    ModuleResult(
                        name=m.name,
                        status="skipped",
                        gaps=[f"skipped: missing inputs [{', '.join(missing)}]"],
                    )
                )
            break

        wave += 1
        _log(f"[pipeline] wave {wave}: {[m.name for m in ready]}")
        wave_results = await asyncio.gather(*(_run_one(m, ctx) for m in ready))

        for m, r in zip(ready, wave_results, strict=True):
            pending.remove(m)
            results.append(r)
            for k, v in r.ctx_updates.items():
                if hasattr(ctx, k):
                    setattr(ctx, k, v)
                else:
                    _log(
                        f"[pipeline] '{m.name}' wrote unknown ctx key '{k}' — "
                        "add it to Context in pipeline/base.py"
                    )
            _log(
                f"[pipeline] '{m.name}' -> {r.status} in {r.duration_s:.1f}s "
                f"({len(r.facts)} fact(s), {len(r.gaps)} gap(s))"
            )

    return results
