"""Final synthesis pass.

Stub for now: aggregates every module's facts/gaps and stitches the
per-module summaries. Once we have multiple modules producing signals, this
becomes an LLM call that cross-references findings (e.g. flag contradictions
between LinkedIn employment and the legal asset report).
"""

from __future__ import annotations

from app.models import Dossier
from app.pipeline.base import Context, ModuleResult


async def synthesize(ctx: Context, results: list[ModuleResult]) -> Dossier:
    all_facts = [f for r in results for f in r.facts]
    all_gaps = [g for r in results for g in r.gaps]

    summary_parts = [r.summary for r in results if r.status == "ok" and r.summary]
    if summary_parts:
        summary = " ".join(summary_parts)
    else:
        summary = f"No enrichment data recovered for case {ctx.case.case_id}."

    return Dossier(summary=summary, facts=all_facts, gaps=all_gaps)
