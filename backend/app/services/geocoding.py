"""Geocoding via OpenStreetMap Nominatim (traceable, no API key)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx

from app.config import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api/"


def normalize_address_line(addr: str) -> str:
    s = addr.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_accents(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nk if not unicodedata.combining(c))


async def nominatim_search(
    *,
    query: str,
    country_codes: str,
    timeout_s: float = 15.0,
) -> dict[str, Any] | None:
    """
    Returns the first Nominatim hit or None.
    country_codes: comma-separated ISO-3166-1alpha2, e.g. 'es' or 'es,pt'
    """
    headers = {"User-Agent": settings.nominatim_user_agent}
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": country_codes.lower(),
    }
    async with httpx.AsyncClient(headers=headers, timeout=timeout_s) as client:
        r = await client.get(NOMINATIM_URL, params=params)
        if r.status_code in (403, 429):
            return None
        r.raise_for_status()
        data = r.json()
    if not data:
        return None
    return data[0]


def _photon_feature_to_nominatim_like(feature: dict[str, Any]) -> dict[str, Any]:
    """Map Photon GeoJSON feature to a Nominatim jsonv2-shaped dict for shared parsing.

    Photon doesn't expose state_district (provincia) — `county` is the closest
    field and maps to comarca/provincia depending on the country. For Spain we
    use it as `state_district` so the property module gets the right provincia.
    """
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or [None, None]
    lon, lat = coords[0], coords[1]
    street = props.get("street")
    num = props.get("housenumber")
    # Prefer explicit city; fall back to name of the feature itself (e.g. a town)
    city = props.get("city") or (props.get("name") if props.get("type") in ("city", "town", "village") else None)
    line = ", ".join(p for p in [f"{street} {num}".strip() if street or num else None, city] if p)
    return {
        "lat": str(lat) if lat is not None else None,
        "lon": str(lon) if lon is not None else None,
        "display_name": line or props.get("name"),
        "licence": "Data © OpenStreetMap contributors, ODbL (served by Photon API, Komoot)",
        "place_id": props.get("osm_id"),
        "address": {
            "house_number": props.get("housenumber"),
            "road": props.get("street"),
            "postcode": props.get("postcode"),
            "suburb": props.get("locality"),
            "city_district": props.get("district"),
            "city": city,
            # county in Photon = comarca/provincia — use as state_district
            "state_district": props.get("county"),
            "state": props.get("state"),
            "country": props.get("country"),
            "country_code": props.get("countrycode"),
        },
    }


async def photon_search(
    *,
    query: str,
    country_iso2: str,
    timeout_s: float = 15.0,
) -> dict[str, Any] | None:
    """Photon (OSM). Filters by countrycode when multiple hits."""
    params: dict[str, str | int] = {"q": query, "limit": 8, "lang": "en"}
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(headers=headers, timeout=timeout_s) as client:
        r = await client.get(PHOTON_URL, params=params)
        r.raise_for_status()
        data = r.json()
    feats = data.get("features") or []
    cc = country_iso2.upper()
    for f in feats:
        props = f.get("properties") or {}
        if props.get("countrycode", "").upper() == cc:
            return _photon_feature_to_nominatim_like(f)
    return _photon_feature_to_nominatim_like(feats[0]) if feats else None


async def geocode_best_effort(*, query: str, country_iso2: str) -> tuple[dict[str, Any] | None, str]:
    """
    Try Nominatim, then Photon. Returns (hit_or_none, engine_label).
    """
    hit = await nominatim_search(query=query, country_codes=country_iso2.lower())
    if hit is not None:
        return hit, "nominatim"
    alt = await photon_search(query=query, country_iso2=country_iso2)
    return alt, "photon"


def extract_location_hints(hit: dict[str, Any]) -> dict[str, str | None]:
    """Pull human fields from a Nominatim jsonv2 hit.

    For Spain, Nominatim uses three tiers:
      state          → CCAA  (Galicia, Cataluña, Comunidad de Madrid…)
      state_district → Provincia (A Coruña, Barcelona, Madrid…)  ← lo que Catastro quiere
      city/town      → Municipio

    `provincia` expone state_district con fallback a state para que el módulo
    de propiedad no tenga que conocer esta jerarquía interna.
    """
    addr = hit.get("address") or {}
    # road: puede venir también como historic (plazas, monumentos) o amenity
    road = (
        addr.get("road")
        or addr.get("historic")
        or addr.get("amenity")
        or addr.get("pedestrian")
    )
    return {
        "display_name": hit.get("display_name"),
        "lat": str(hit["lat"]) if hit.get("lat") is not None else None,
        "lon": str(hit["lon"]) if hit.get("lon") is not None else None,
        "house_number": addr.get("house_number"),
        "road": road,
        "postcode": addr.get("postcode"),
        "suburb": addr.get("suburb") or addr.get("neighbourhood"),
        "city_district": addr.get("city_district"),
        "city": (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
        ),
        # state_district es la provincia en ES; state es la CCAA
        "provincia": addr.get("state_district") or addr.get("state"),
        "state": addr.get("state"),
        "country": addr.get("country"),
        "country_code": addr.get("country_code"),
    }


def barcelona_match_tokens(hints: dict[str, str | None]) -> list[str]:
    """Collect strings that may match an Ajuntament 'barri' label."""
    raw = [
        hints.get("suburb"),
        hints.get("city_district"),
        hints.get("city"),
    ]
    out: list[str] = []
    for x in raw:
        if not x:
            continue
        out.append(x)
        out.append(_strip_accents(x))
    return out
