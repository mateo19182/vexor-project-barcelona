"""Eurostat house price index (HPI) — country-level macro context."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

# Existing dwellings, index 2015=100, quarterly — same basket used for ratio scaling.
EUROSTAT_HPI_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q"

_EU_CLIENT_HEADERS = {"User-Agent": settings.nominatim_user_agent}


async def fetch_hpi_existing_dwelling(
    *,
    geo: str,
    time_period: str,
    timeout_s: float = 20.0,
) -> float | None:
    """
    geo: Eurostat code, usually same as ISO-3166-1 alpha-2 (e.g. ES, PT, FR).
    time_period: e.g. '2015-Q4', '2025-Q4'
    """
    params = {
        "format": "JSON",
        "geo": geo.upper(),
        "unit": "I15_Q",
        "purchase": "DW_EXST",
        "time": time_period,
    }
    async with httpx.AsyncClient(headers=_EU_CLIENT_HEADERS, timeout=timeout_s) as client:
        r = await client.get(EUROSTAT_HPI_URL, params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        payload: dict[str, Any] = r.json()
    if "error" in payload:
        return None
    values = payload.get("value") or {}
    if not values:
        return None
    # Single observation requested — take first value
    v = next(iter(values.values()))
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def fetch_latest_hpi_existing_dwelling(
    *,
    geo: str,
    timeout_s: float = 20.0,
) -> tuple[str | None, float | None]:
    """Latest available quarter for existing dwellings, index 2015=100."""
    params = {
        "format": "JSON",
        "geo": geo.upper(),
        "unit": "I15_Q",
        "purchase": "DW_EXST",
        "lastTimePeriod": 1,
    }
    async with httpx.AsyncClient(headers=_EU_CLIENT_HEADERS, timeout=timeout_s) as client:
        r = await client.get(EUROSTAT_HPI_URL, params=params)
        if r.status_code == 404:
            return None, None
        r.raise_for_status()
        payload: dict[str, Any] = r.json()
    if "error" in payload:
        return None, None
    times = (payload.get("dimension") or {}).get("time", {}).get("category", {}).get("index") or {}
    if not times:
        return None, None
    period = next(iter(times.keys()))
    values = payload.get("value") or {}
    if not values:
        return period, None
    try:
        v = float(next(iter(values.values())))
    except (TypeError, ValueError, StopIteration):
        return period, None
    return period, v


async def hpi_ratio_since_latest(
    *,
    geo: str,
    base_period: str = "2015-Q4",
) -> tuple[str | None, float | None, float | None, float | None]:
    """
    Returns (latest_period, base_index, latest_index, ratio latest/base).
    """
    base = await fetch_hpi_existing_dwelling(geo=geo, time_period=base_period)
    latest_period, latest = await fetch_latest_hpi_existing_dwelling(geo=geo)
    if base is None or latest is None or base == 0:
        return latest_period, base, latest, None
    return latest_period, base, latest, latest / base
