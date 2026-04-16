"""Twitter/X OSINT enrichment module.

Requires ``twitter_handle`` on the Context — promoted by ``osint_web`` when
it finds a Twitter/X profile with confidence >= 0.6.  Fetches the public
profile and recent timeline via ``twscrape`` and surfaces:

  * Bio text as a Fact (employer hints, location clues).
  * Profile location field as a ``location`` Signal.
  * Activity recency as a ``lifestyle`` Signal (active posting contradicts
    the "I have nothing" claim).
  * Keyword-scanned tweet content for employer, travel, and asset signals.

Self-skips cleanly when TWITTER_USERNAME is not configured.
"""

from __future__ import annotations

import re

from app.config import settings
from app.enrichment.twitter import enrich_twitter
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

# Simple keyword patterns for tweet content scanning.
# These are intentionally conservative — only fire on fairly direct mentions.
_EMPLOYER_PATTERNS = [
    r"\bwork(?:ing)? (?:at|for|with)\b",
    r"\bjoined\b.*\bteam\b",
    r"\bmy (?:job|office|company|employer|boss)\b",
    r"@[A-Za-z0-9_]+ (?:hiring|we're hiring)",
]
_TRAVEL_PATTERNS = [
    r"\bjust (?:landed|arrived)\b",
    r"\bflying to\b",
    r"\bin [A-Z][a-z]+ (?:today|now|this week)\b",
    r"\bholiday\b|\bvacation\b|\bvacaciones\b",
]
_ASSET_PATTERNS = [
    r"\bmy (?:car|moto|bike|apartment|flat|house|piso|coche|moto)\b",
    r"\bnew (?:car|phone|iphone|laptop|flat|house)\b",
    r"\bbought\b.*\b(?:car|house|flat|bike)\b",
]


def _scan_tweets(tweets: list[dict], profile_url: str) -> list[Signal]:
    """Keyword-scan combined tweet text and return signals."""
    combined = " ".join(t["text"] for t in tweets).lower()
    signals: list[Signal] = []

    for pattern in _EMPLOYER_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            signals.append(
                Signal(
                    kind="employer",
                    value="Possible employment mention in recent tweets",
                    source=profile_url,
                    confidence=0.45,
                    notes="Keyword match in tweet text — manual review required",
                )
            )
            break  # one employer signal is enough

    for pattern in _TRAVEL_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            signals.append(
                Signal(
                    kind="lifestyle",
                    value="Recent travel activity inferred from tweets",
                    source=profile_url,
                    confidence=0.50,
                    notes="Keyword match in tweet text — manual review required",
                )
            )
            break

    for pattern in _ASSET_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            signals.append(
                Signal(
                    kind="asset",
                    value="Possible asset mention (vehicle / property) in tweets",
                    source=profile_url,
                    confidence=0.40,
                    notes="Keyword match in tweet text — manual review required",
                )
            )
            break

    return signals


class TwitterModule:
    name = "twitter"
    requires: tuple[str, ...] = ("twitter_handle",)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.twitter_username:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["twitter_enrich: TWITTER_USERNAME not configured — skipping"],
            )

        handle = (ctx.twitter_handle or "").strip().lstrip("@")
        profile_url = f"https://x.com/{handle}"

        data = await enrich_twitter(
            handle=handle,
            username=settings.twitter_username,
            password=settings.twitter_password,
            cookies=settings.twitter_cookies,
        )

        if "error" in data:
            return ModuleResult(
                name=self.name,
                status="ok",
                gaps=[
                    f"Twitter profile @{handle} not retrievable: {data.get('detail') or data['error']}"
                ],
                raw=data,
            )

        if data.get("protected"):
            return ModuleResult(
                name=self.name,
                status="ok",
                gaps=[f"@{handle} account is protected — timeline not accessible"],
                raw=data,
            )

        signals: list[Signal] = []
        facts: list[Fact] = []
        gaps: list[str] = []

        # Bio → Fact
        bio = (data.get("bio") or "").strip()
        if bio:
            facts.append(
                Fact(
                    claim=f"Twitter/X bio: {bio}",
                    source=profile_url,
                    confidence=0.85,
                )
            )

        # Profile location field → Signal
        location = (data.get("location") or "").strip()
        if location:
            signals.append(
                Signal(
                    kind="location",
                    value=location,
                    source=profile_url,
                    confidence=0.70,
                    notes="Self-reported location field on Twitter/X profile",
                )
            )

        # Activity recency — active posting while claiming nothing is a contradiction
        recent = data.get("recent_tweets") or []
        if recent:
            last_date = recent[0]["date"][:10]
            signals.append(
                Signal(
                    kind="lifestyle",
                    value=f"Active on Twitter/X as recently as {last_date}",
                    source=profile_url,
                    confidence=0.80,
                )
            )
        else:
            gaps.append(f"@{handle}: no recent tweets found (account may be inactive)")

        # Tweet content keyword scan
        if recent:
            content_signals = _scan_tweets(recent, profile_url)
            signals.extend(content_signals)

        if data.get("tweet_fetch_error"):
            gaps.append(f"Timeline fetch error: {data['tweet_fetch_error']}")

        followers = data.get("followers", 0)
        summary = (
            f"@{handle} ({data.get('display_name', '')})"
            f" — {followers:,} followers."
            f" Bio: {bio or 'none'}."
            f" Location: {location or 'not set'}."
            f" Last tweet: {recent[0]['date'][:10] if recent else 'unknown'}."
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            signals=signals,
            facts=facts,
            gaps=gaps,
            raw=data,
        )
