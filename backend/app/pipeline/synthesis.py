"""Final synthesis pass.

Stub for now: aggregates every module's signals/facts/gaps and stitches the
per-module summaries. Once we have multiple modules producing signals, this
becomes an LLM call that cross-references findings (e.g. flag contradictions
between LinkedIn employment and the legal asset report).
"""

from __future__ import annotations

from app.models import Dossier, Signal
from app.pipeline.base import Context, ModuleResult


def _dedupe_signals(signals: list[Signal]) -> list[Signal]:
    """Keep one signal per `(kind, value)`, picking the highest confidence.

    Value comparison is case-insensitive and trim-insensitive; two modules
    reporting "Barcelona, ES" and " barcelona, es " should collapse.
    """
    best: dict[tuple[str, str], Signal] = {}
    for s in signals:
        key = (s.kind, s.value.strip().lower())
        existing = best.get(key)
        if existing is None or s.confidence > existing.confidence:
            best[key] = s
    return list(best.values())


async def synthesize(ctx: Context, results: list[ModuleResult]) -> Dossier:
    all_facts = [f for r in results for f in r.facts]
    all_signals = _dedupe_signals([s for r in results for s in r.signals])
    all_gaps = [g for r in results for g in r.gaps]

    summary_parts = [r.summary for r in results if r.status == "ok" and r.summary]
    if summary_parts:
        summary = " ".join(summary_parts)
    else:
        summary = f"No enrichment data recovered for case {ctx.case.case_id}."

    return Dossier(
        summary=summary, facts=all_facts, signals=all_signals, gaps=all_gaps
    )
