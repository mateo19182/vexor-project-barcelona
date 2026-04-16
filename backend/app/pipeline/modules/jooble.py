"""Jooble job-market enrichment module.

Requires a ``role`` signal on Context (written by the ``linkedin`` module
from the LinkedIn headline). Optionally uses a ``location`` signal to narrow
the search geographically.

What this tells a collector:
  * **Employment plausibility** — if the debtor claims to work as an X,
    are there actual X jobs in their city? A saturated market or zero
    postings is a data point worth noting.
  * **Income proxy** — salary ranges from live postings give an
    evidence-backed estimate of what someone in this role earns, useful
    for ability-to-pay assessment.
  * **Role validation** — confirms the headline describes a real,
    searchable profession (not a vague self-description).

Skips cleanly when ``JOOBLE_API_KEY`` is absent.
"""

from __future__ import annotations

import re

from app.config import settings
from app.enrichment.jooble import enrich_jooble
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

# Headline values that are clearly not job titles — skip Jooble for these.
_NON_TITLE_PATTERNS = re.compile(
    r"(desemplead|unemployed|looking for|en búsqueda|jubilad|retired|student|estudiante)",
    re.IGNORECASE,
)

_HIGH_DEMAND_THRESHOLD = 50
_MODERATE_DEMAND_THRESHOLD = 10


def _parse_salaries(jobs: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for j in jobs:
        s = j.get("salary", "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class JoobleModule:
    name = "jooble"
    # Runs after linkedin (which emits a "role" signal from the headline).
    requires: tuple[tuple[str, str | None], ...] = (("role", None),)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.jooble_api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["jooble: JOOBLE_API_KEY not configured — skipping"],
            )

        role_sig = ctx.best("role")
        headline = role_sig.value if role_sig else ""

        if not headline or _NON_TITLE_PATTERNS.search(headline):
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=f"Jooble skipped: '{headline}' is not a searchable job title.",
                gaps=[f"jooble: headline '{headline}' does not look like a job title"],
            )

        loc_sig = ctx.best("location")
        city = loc_sig.value if loc_sig else ""

        data = await enrich_jooble(
            headline=headline,
            city=city,
            api_key=settings.jooble_api_key,
            country_code=ctx.case.country,
        )

        errors = data.get("errors") or []
        if errors and not data.get("jobs"):
            return ModuleResult(
                name=self.name,
                status="ok",
                gaps=[f"jooble: {e}" for e in errors],
                raw=data,
            )

        job_title = data.get("job_title_used", headline)
        total = data.get("total_count", 0)
        jobs: list[dict] = data.get("jobs") or []
        salaries = _parse_salaries(jobs)

        facts: list[Fact] = []
        signals: list[Signal] = []
        gaps: list[str] = list(errors)

        location_label = f"{job_title} in {city}" if city else job_title
        source_ref = "jooble.org search: '" + job_title + "'" + (f" / '{city}'" if city else "")

        # ── Job-market activity signal ──────────────────────────────────────
        if total >= _HIGH_DEMAND_THRESHOLD:
            signals.append(
                Signal(
                    kind="lifestyle",
                    value=f"Active job market for {location_label} ({total}+ listings)",
                    source=source_ref,
                    confidence=0.65,
                    notes=(
                        f"High demand: {total} active Jooble listings for '{job_title}'"
                        + (f" in {city}" if city else "")
                        + " — consistent with active local employment."
                    ),
                )
            )
        elif total >= _MODERATE_DEMAND_THRESHOLD:
            signals.append(
                Signal(
                    kind="lifestyle",
                    value=f"Moderate job market for {location_label} ({total} listings)",
                    source=source_ref,
                    confidence=0.55,
                    notes=f"Moderate demand: {total} Jooble listings for '{job_title}'"
                    + (f" in {city}" if city else ""),
                )
            )
        elif total == 0:
            gaps.append(
                f"jooble: no listings found for '{job_title}'"
                + (f" in '{city}'" if city else "")
                + " — headline may be non-standard or market is very niche"
            )
        else:
            gaps.append(
                f"jooble: only {total} listing(s) for '{job_title}'"
                + (f" in '{city}'" if city else "")
            )

        # ── Salary facts ────────────────────────────────────────────────────
        for salary in salaries[:3]:
            facts.append(
                Fact(
                    claim=(
                        f"Jooble salary range for '{job_title}'"
                        + (f" in {city}" if city else "")
                        + f": {salary}"
                    ),
                    source=source_ref,
                    confidence=0.55,
                )
            )

        # ── Role validation fact ────────────────────────────────────────────
        if total > 0:
            facts.append(
                Fact(
                    claim=(
                        f"Jooble confirms '{job_title}' is an active job title"
                        + (f" in {city}" if city else "")
                        + f" ({total} listing(s) found)."
                    ),
                    source=source_ref,
                    confidence=0.60,
                )
            )

        # ── Summary ─────────────────────────────────────────────────────────
        summary_parts = [
            f"Jooble: '{job_title}'"
            + (f" in {city}" if city else "")
            + f" → {total} listing(s)."
        ]
        if salaries:
            summary_parts.append(f"Sample salaries: {', '.join(salaries[:2])}.")

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=" ".join(summary_parts),
            facts=facts,
            signals=signals,
            gaps=gaps,
            raw=data,
        )
