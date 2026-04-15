"""
Barcelona open data: average offer €/m² second-hand homes by barri (2015), source Idealista via Ajuntament.

CKAN package: habitatges-2na-ma — serie interrumpida pero usable como base documentada.
We scale to a recent period using Eurostat national HPI ratio (see property_estimate).
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

import httpx

from app.config import settings

CKAN_DATASTORE_SEARCH = (
    "https://opendata-ajuntament.barcelona.cat/data/api/3/action/datastore_search"
)
#2015_habitatges_2na_ma2015.csv — values in thousands of €/m² (e.g. 2.775 => 2775 €/m²)
RESOURCE_ID = "cd9118c6-427c-4390-8334-3670cc3f3f6a"


def _strip_accents(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nk if not unicodedata.combining(c))


def _norm_barri_label(label: str) -> str:
    s = label.strip().lower()
    s = _strip_accents(s)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


@lru_cache(maxsize=1)
def _load_barri_rows_sync() -> list[dict[str, Any]]:
    """Sync loader for cache — called from async via asyncio.to_thread if needed."""
    params = {"resource_id": RESOURCE_ID, "limit": 500}
    headers = {"User-Agent": settings.nominatim_user_agent}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        r = client.get(CKAN_DATASTORE_SEARCH, params=params)
        r.raise_for_status()
        payload = r.json()
    if not payload.get("success"):
        return []
    return list(payload["result"].get("records") or [])


async def load_barri_rows() -> list[dict[str, Any]]:
    import asyncio

    return await asyncio.to_thread(_load_barri_rows_sync)


def row_eur_per_m2_2015(row: dict[str, Any]) -> float | None:
    raw = row.get("2015")
    if raw is None:
        return None
    try:
        # Thousands of €/m² with dot as decimal separator
        v = float(str(raw).replace(",", "."))
    except ValueError:
        return None
    return v * 1000.0


def pick_barcelona_row(
    rows: list[dict[str, Any]],
    *,
    match_tokens: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns (row, matched_token or 'BARCELONA' or None).
    """
    by_norm: dict[str, dict[str, Any]] = {}
    city_row: dict[str, Any] | None = None
    for row in rows:
        barris = row.get("Barris")
        if not isinstance(barris, str):
            continue
        if barris.strip().upper() == "BARCELONA":
            city_row = row
            continue
        by_norm[_norm_barri_label(barris)] = row

    for tok in match_tokens:
        if not tok:
            continue
        key = _norm_barri_label(tok)
        if key in by_norm:
            return by_norm[key], tok
        # Partial: token contained in barri name or vice versa
        for bn, r in by_norm.items():
            if key in bn or bn in key:
                return r, tok

    if city_row is not None:
        return city_row, "BARCELONA"
    return None, None
