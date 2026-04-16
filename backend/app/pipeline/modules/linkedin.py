"""LinkedIn OSINT enrichment module (LinkdAPI-backed).

Requires ``linkedin_url`` on the Context — usually promoted by
``osint_web`` when it finds a linkedin.com/in/<slug> URL with high
confidence. Calls LinkdAPI's profile/overview + profile/details
endpoints and translates the payload into Facts / Signals.

Self-skips cleanly when LINKDAPI_API_KEY is not configured.
"""

from __future__ import annotations

from app.config import settings
from app.enrichment.linkedin import enrich_linkedin, extract_username
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult


def _first(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v).strip()
    return ""


class LinkedInModule:
    name = "linkedin"
    requires: tuple[str, ...] = ("linkedin_url",)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.linkdapi_api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["linkedin: LINKDAPI_API_KEY not configured — skipping"],
            )

        url = ctx.linkedin_url or ""
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

        first_name = _first(overview, "firstName")
        last_name = _first(overview, "lastName")
        full_name = f"{first_name} {last_name}".strip()

        headline = _first(overview, "headline") or _first(details, "headline")
        if headline:
            facts.append(
                Fact(
                    claim=f"LinkedIn headline: {headline}",
                    source=url,
                    confidence=0.9,
                )
            )
            # Headline almost always encodes role + employer ("Product Mgr at Acme").
            signals.append(
                Signal(
                    kind="role",
                    value=headline,
                    source=url,
                    confidence=0.75,
                    notes="Verbatim LinkedIn headline — parse for role/employer",
                )
            )

        summary = _first(details, "summary")
        if summary:
            facts.append(
                Fact(
                    claim=f"LinkedIn About: {summary[:400]}",
                    source=url,
                    confidence=0.85,
                )
            )

        location = _first(details, "location") or _first(overview, "location")
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

        verification = _first(details, "verificationStatus")
        if verification and verification.lower() not in {"none", "unverified", "false"}:
            facts.append(
                Fact(
                    claim=f"LinkedIn verification status: {verification}",
                    source=url,
                    confidence=0.9,
                )
            )

        if data.get("details") is None and data.get("urn"):
            gaps.append("linkedin: details endpoint returned no data")
        elif not data.get("urn"):
            gaps.append("linkedin: no URN in overview — details endpoint skipped")

        display = full_name or username
        summary_line = (
            f"LinkedIn @{username} ({display})"
            f"{' — ' + headline if headline else ''}"
            f"{' — ' + location if location else ''}."
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
