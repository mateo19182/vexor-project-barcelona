"""NoSINT CSINT module — streams 30+ module results for a given email address.

Requires: contact:email signal
Output:
  signals  — one `contact` signal per platform where the email is found;
             `risk_flag` for any breach/leak/paste module hit.
  facts    — summary fact with hit count and list of matched platforms.
  raw      — full `all_results` list (every module event, valid or not).
"""

from __future__ import annotations

import sys

from app.config import settings
from app.enrichment.nosint import enrich_nosint
from app.models import Fact, Signal, SocialLink
from app.pipeline.base import Context, ModuleResult

# Module names containing these keywords are classified as risk_flag signals
_BREACH_KEYWORDS = {"breach", "hibp", "haveibeenpwned", "leak", "pwned", "paste", "exposed"}

_SOURCE_BASE = "https://nosint.org"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _is_breach_module(module_name: str) -> bool:
    lower = module_name.lower()
    return any(kw in lower for kw in _BREACH_KEYWORDS)


class NosintModule:
    name = "nosint"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "email"),)

    async def run(self, ctx: Context) -> ModuleResult:
        api_key = settings.nosint_api_key
        if not api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary="NoSINT skipped — NOSINT_API_KEY not configured.",
                gaps=["NOSINT_API_KEY is not set"],
            )

        email_sig = ctx.best("contact", "email")
        email = email_sig.value if email_sig else ""
        result = await enrich_nosint(email, api_key)

        if not result.all_results and result.gaps:
            return ModuleResult(
                name=self.name,
                status="error",
                summary=f"NoSINT lookup failed for {email}.",
                gaps=result.gaps,
                raw={"search_id": result.search_id},
                duration_s=result.duration_s,
            )

        signals: list[Signal] = []
        social_links: list[SocialLink] = []
        facts: list[Fact] = []

        for hit in result.hits:
            module_name: str = hit.get("module_name") or ""
            target_url: str = hit.get("target_url") or ""
            cached: bool = hit.get("cached", False)

            # Build a usable source URL from the target_url domain
            source_url = (
                f"https://{target_url}" if target_url and not target_url.startswith("http")
                else target_url or _SOURCE_BASE
            )

            notes_parts = [f"Found by NoSINT module: {module_name}"]
            if cached:
                notes_parts.append("(cached result)")
            notes = "; ".join(notes_parts)

            if _is_breach_module(module_name):
                signals.append(Signal(
                    kind="risk_flag",
                    value=f"Email found in {module_name}",
                    source=source_url,
                    confidence=0.85,
                    notes=notes,
                ))
            else:
                signals.append(Signal(
                    kind="contact",
                    value=target_url or module_name,
                    source=source_url,
                    confidence=0.8,
                    notes=notes,
                ))
                if target_url:
                    social_links.append(SocialLink(
                        platform=module_name,
                        url=source_url,
                        confidence=0.8,
                    ))

        # Summary facts
        hit_count = len(result.hits)
        total = len(result.all_results)

        if hit_count:
            platform_list = ", ".join(
                h.get("target_url") or h.get("module_name", "?")
                for h in result.hits[:15]
            )
            if len(result.hits) > 15:
                platform_list += f" (+{len(result.hits) - 15} more)"
            facts.append(Fact(
                claim=f"Email active on {hit_count} platform(s) out of {total} checked: {platform_list}",
                source=_SOURCE_BASE,
                confidence=0.85,
            ))

        gaps = list(result.gaps)
        if total and not hit_count:
            gaps.append(f"NoSINT checked {total} module(s) but found no valid hits for this email")

        # Build summary line
        breach_hits = [s for s in signals if s.kind == "risk_flag"]
        contact_hits = [s for s in signals if s.kind == "contact"]
        summary_parts = []
        if contact_hits:
            summary_parts.append(f"Email found on {len(contact_hits)} platform(s)")
        if breach_hits:
            summary_parts.append(f"{len(breach_hits)} breach/leak hit(s)")
        summary = (
            " | ".join(summary_parts)
            if summary_parts
            else f"NoSINT: no valid hits for {email} across {total} module(s)."
        )

        return ModuleResult(
            name=self.name,
            status="ok" if result.all_results else "no_data",
            summary=summary,
            signals=signals,
            social_links=social_links,
            facts=facts,
            gaps=gaps,
            raw={
                "search_id": result.search_id,
                "total_modules_run": total,
                "hits_count": hit_count,
                "all_results": result.all_results,
            },
            duration_s=result.duration_s,
        )
