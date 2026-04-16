"""LinkedIn OSINT enrichment module (LinkdAPI-backed).

Requires a ``contact:linkedin`` signal on the Context — usually promoted by
``osint_web`` when it finds a linkedin.com/in/<slug> URL. Calls
LinkdAPI's ``/profile/overview`` and ``/profile/details`` endpoints and
translates the payload into Facts / Signals a collector can act on.

The two most valuable things LinkedIn gives us are:
  * **Employer** — from ``CurrentPositions[0].name`` in overview, which
    directly contradicts the common "I'm unemployed" debtor claim.
  * **Location** — self-reported on the profile, useful for service of
    process and geographic prioritization.

Self-skips cleanly when ``LINKDAPI_API_KEY`` is not configured.
"""

from __future__ import annotations

from app.config import settings
from app.enrichment.linkedin import enrich_linkedin, extract_username
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult


def _location_str(loc: dict | None) -> str:
    """Flatten LinkdAPI's location object to a single display string."""
    if not loc:
        return ""
    return (
        loc.get("fullLocation")
        or ", ".join(
            x for x in (loc.get("city"), loc.get("countryName")) if x
        )
        or ""
    ).strip()


class LinkedInModule:
    name = "linkedin"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "linkedin"),)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.linkdapi_api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["linkedin: LINKDAPI_API_KEY not configured — skipping"],
            )

        sig = ctx.best("contact", "linkedin")
        url = sig.value if sig else ""
        username = extract_username(url)
        if not username:
            return ModuleResult(
                name=self.name,
                status="ok",
                gaps=[f"linkedin: could not parse slug from {url!r}"],
            )

        data = await enrich_linkedin(url, settings.linkdapi_api_key)
        overview = data.get("overview") or {}
        details = data.get("details") or {}

        if "error" in overview:
            return ModuleResult(
                name=self.name,
                status="ok",
                gaps=[
                    f"LinkedIn profile {username!r} not retrievable: "
                    f"{overview.get('detail') or overview['error']}"
                ],
                raw=data,
            )

        facts: list[Fact] = []
        signals: list[Signal] = []
        gaps: list[str] = []

        full_name = (overview.get("fullName") or "").strip() or " ".join(
            x for x in (overview.get("firstName"), overview.get("lastName")) if x
        )
        headline = (overview.get("headline") or "").strip()
        industry = (overview.get("industryName") or "").strip()
        location = _location_str(overview.get("location"))

        if headline:
            signals.append(
                Signal(
                    kind="role",
                    value=headline,
                    source=url,
                    confidence=0.85,
                    notes="Verbatim LinkedIn headline",
                )
            )

        for pos in overview.get("CurrentPositions") or []:
            company = (pos.get("name") or "").strip()
            if company:
                signals.append(
                    Signal(
                        kind="employer",
                        value=company,
                        source=pos.get("url") or url,
                        confidence=0.85,
                        notes="Listed as current position on LinkedIn",
                    )
                )

        if industry:
            signals.append(
                Signal(
                    kind="affiliation",
                    value=f"Industry: {industry}",
                    source=url,
                    confidence=0.70,
                )
            )

        if location:
            signals.append(
                Signal(
                    kind="location",
                    value=location,
                    source=url,
                    confidence=0.80,
                    notes="Self-reported location on LinkedIn profile",
                )
            )

        about = (details.get("about") or "").strip()
        if about:
            facts.append(
                Fact(
                    claim=f"LinkedIn About: {about[:500]}",
                    source=url,
                    confidence=0.85,
                )
            )

        positions = details.get("positions") or []
        for pos in positions[:3]:
            title = (pos.get("jobTitle") or "").strip()
            company = (pos.get("company") or "").strip()
            duration = (pos.get("duration") or "").strip()
            if title or company:
                bits = [p for p in (title, company, duration) if p]
                facts.append(
                    Fact(
                        claim="LinkedIn position: " + " — ".join(bits),
                        source=pos.get("companyLink") or url,
                        confidence=0.80,
                    )
                )

        if data.get("urn") is None:
            gaps.append("linkedin: no URN returned by overview — details skipped")
        elif details and "error" in details:
            gaps.append(
                f"linkedin details fetch failed: "
                f"{details.get('detail') or details['error']}"
            )

        display = full_name or username
        summary_line = (
            f"LinkedIn @{username} ({display})"
            + (f" — {headline}" if headline else "")
            + (f" — {location}" if location else "")
            + (f" — {overview.get('followerCount', 0):,} followers"
               if overview.get("followerCount") else "")
            + "."
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary_line,
            facts=facts,
            signals=signals,
            gaps=gaps,
            raw=data,
        )
