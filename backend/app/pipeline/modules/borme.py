"""BORME (Boletín Oficial del Registro Mercantil) module.

Searches Spain's Commercial Registry Gazette for mentions of the debtor's
name using Brave Search API with `site:boe.es inurl:borme`. Surfaces
commercially relevant entries: director appointments / removals, company
formations, dissolutions, capital changes, and commercial insolvency.

Companion to `boe.py`: that module covers judicial / state notices
(edictos, embargos); this one covers commercial-registry acts. The
`inurl:borme` filter keeps the two disjoint.

Requires BRAVE_API_KEY in environment.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from app.config import settings
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT = 15.0

_RISK_KEYWORDS = {
    "concurso",
    "quiebra",
    "disolución",
    "disolucion",
    "liquidación",
    "liquidacion",
    "extinción",
    "extincion",
    "cese",
    "dimisión",
    "dimision",
    "revocación",
    "revocacion",
    "insolvencia",
}

_ROLE_KEYWORDS = {
    "nombramiento",
    "administrador",
    "consejero",
    "apoderado",
    "secretario",
    "presidente",
    "vicepresidente",
    "constitución",
    "constitucion",
    "fusión",
    "fusion",
    "escisión",
    "escision",
    "ampliación de capital",
    "ampliacion de capital",
    "reducción de capital",
    "reduccion de capital",
}


def _name_in_text(name: str, text: str) -> bool:
    """Return True if all words of *name* appear in *text* (case-insensitive)."""
    for word in name.split():
        if not re.search(re.escape(word), text, re.IGNORECASE):
            return False
    return True


def _classify(text: str) -> tuple[str | None, float]:
    """Return (signal_kind, confidence) based on keyword matching, or (None, 0)."""
    lower = text.lower()
    if any(kw in lower for kw in _RISK_KEYWORDS):
        return "risk_flag", 0.85
    if any(kw in lower for kw in _ROLE_KEYWORDS):
        return "role", 0.75
    return None, 0.0


async def _brave_search(client: httpx.AsyncClient, query: str, api_key: str) -> list[dict[str, Any]]:
    try:
        r = await client.get(
            _BRAVE_URL,
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
                "User-Agent": "VexorEnrichmentPipeline/1.0",
            },
            params={"q": query, "count": 10, "country": "es", "search_lang": "es"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("web", {}).get("results", [])
    except Exception:
        return []


class BormeModule:
    name = "borme"
    requires: tuple[str, ...] = ("name",)

    async def run(self, ctx: Context) -> ModuleResult:
        if not settings.brave_api_key:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary="BORME module disabled (BRAVE_API_KEY not set).",
                gaps=["BRAVE_API_KEY env var not configured"],
            )

        name = ctx.name
        queries = [
            f'site:boe.es inurl:borme "{name}"',
            f'site:boe.es inurl:borme "{name}" nombramiento OR cese OR concurso OR administrador',
        ]

        async with httpx.AsyncClient() as client:
            results_per_query = await asyncio.gather(
                *[_brave_search(client, q, settings.brave_api_key) for q in queries]
            )

        seen: set[str] = set()
        signals: list[Signal] = []
        facts: list[Fact] = []

        for results in results_per_query:
            for r in results:
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)

                title = r.get("title", "") or ""
                description = r.get("description", "") or ""
                text = f"{title} {description}"

                if not _name_in_text(name, text):
                    continue

                kind, confidence = _classify(text)
                if kind:
                    signals.append(
                        Signal(
                            kind=kind,
                            value=title or url,
                            source=url,
                            confidence=confidence,
                            notes=description or None,
                        )
                    )
                else:
                    facts.append(
                        Fact(
                            claim=title or url,
                            source=url,
                            confidence=0.60,
                        )
                    )

        if not signals and not facts:
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"No BORME entries found for '{name}'.",
            )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=f"{len(signals)} BORME risk/role signal(s), {len(facts)} other entry(ies) for '{name}'.",
            signals=signals,
            facts=facts,
        )
