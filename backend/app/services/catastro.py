"""Catastro API — wrapper sobre api.catastro-api.es.

Flujo: dirección libre → geocoding → vias → inmueble-localizacion.

El cliente devuelve siempre None ante errores de red o ausencia de resultados;
los gaps se propagan hacia arriba, nunca se silencian.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx

from app.config import settings

BASE_URL = "https://api.catastro-api.es"
SOURCE_URL = "https://catastro-api.es"
TIMEOUT = 15.0

# Tipos de vía más comunes según Catastro
TIPO_VIA_MAP: dict[str, str] = {
    # Ordered longest-first so "gran via" matches before "via"
    "gran via": "CL",
    "avinguda": "AV",   # catalán
    "avenida": "AV",
    "passeig": "PS",    # catalán
    "paseo": "PS",
    "travesia": "TR",
    "travesía": "TR",
    "carretera": "CR",
    "camino": "CM",
    "ronda": "RD",
    "glorieta": "GL",
    "urbanizacion": "UR",
    "urbanización": "UR",
    "boulevard": "BV",
    "pasaje": "PJ",
    "plaza": "PZ",
    "placa": "PZ",      # catalán
    "rua": "RU",
    "rúa": "RU",
    "via": "VI",
    "calle": "CL",
    "carrer": "CL",     # catalán
    "cami": "CM",       # catalán
}


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def _headers() -> dict[str, str]:
    return {
        "x-api-key": settings.catastro_api_key,
        "Accept": "application/json",
    }


def _has_key() -> bool:
    return bool(settings.catastro_api_key.strip())


async def get_vias(
    provincia: str,
    municipio: str,
    nombre_via: str,
) -> list[dict[str, Any]]:
    """Busca calles que contengan `nombre_via` en el municipio.

    Devuelve lista de {nombreVia, tipoVia, codigoVia} o [] si no hay resultados.
    """
    if not _has_key():
        return []
    params = {
        "provincia": provincia,
        "municipio": municipio,
        "nombreVia": nombre_via[:30],  # Catastro no acepta strings muy largos
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(f"{BASE_URL}/api/callejero/vias", params=params, headers=_headers())
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("vias") or []
        except (httpx.RequestError, Exception):  # noqa: BLE001
            return []


async def get_inmuebles_by_address(
    provincia: str,
    municipio: str,
    tipo_via: str,
    nombre_via: str,
    numero: str,
    planta: str | None = None,
    puerta: str | None = None,
) -> list[dict[str, Any]]:
    """Inmuebles para una dirección concreta.

    Devuelve lista de inmuebles (cada uno con datosEconomicos, referenciaCatastral, etc.)
    o [] si no hay resultados o la API falla.
    """
    if not _has_key():
        return []
    params: dict[str, str] = {
        "provincia": provincia,
        "municipio": municipio,
        "tipoVia": tipo_via,
        "nombreVia": nombre_via,
        "numero": numero,
    }
    if planta:
        params["planta"] = planta
    if puerta:
        params["puerta"] = puerta

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(
                f"{BASE_URL}/api/callejero/inmueble-localizacion",
                params=params,
                headers=_headers(),
            )
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("inmuebles") or []
        except (httpx.RequestError, Exception):  # noqa: BLE001
            return []


# Partículas iniciales que Catastro omite del nombre de vía
# "Passeig de Maragall" → Catastro lo tiene como "MARAGALL" (sin "de")
_VIA_PARTICLES = ("de les ", "de los ", "de las ", "de la ", "del ", "de ", "d'", "l'")


def parse_tipo_via(road: str) -> tuple[str, str]:
    """Extrae (tipoVia, nombreVia) de un nombre de calle en texto libre.

    Ejemplos:
      "Calle Gran Vía"      → ("CL", "GRAN VÍA")
      "Passeig de Maragall" → ("PS", "MARAGALL")   # strip partícula "de"
      "Avinguda Diagonal"   → ("AV", "DIAGONAL")
      "Gran Vía"            → ("CL", "GRAN VÍA")   # fallback
    """
    road_clean = road.strip()
    road_lower = _normalize(road_clean)

    tipo = "CL"
    nombre_raw = road_clean

    for prefix, code in TIPO_VIA_MAP.items():
        if road_lower.startswith(prefix):
            tipo = code
            nombre_raw = road_clean[len(prefix):].strip()
            break

    # Quitar partícula inicial ("de", "de la", "del"…) que Catastro no incluye
    nombre_lower = _normalize(nombre_raw)
    for particle in _VIA_PARTICLES:
        if nombre_lower.startswith(particle):
            nombre_raw = nombre_raw[len(particle):].strip()
            break

    return tipo, (nombre_raw.upper() or road_clean.upper())


def parse_planta_puerta(address: str) -> tuple[str | None, str | None]:
    """Extrae planta y puerta del texto libre de una dirección.

    Catastro usa códigos de planta como: BJ (bajo), EN (entresuelo),
    PR (principal), AT (ático), SS (sótano), y números ("01", "02"…).

    Ejemplos:
      "Entresuelo 1"      → ("EN", "01")
      "3º Izquierda"      → ("03", "IZ")
      "Bajo B"            → ("BJ", "B")
      "Planta 4, Puerta 2"→ ("04", "02")
      "Ático Derecha"     → ("AT", "DR")
      "Principal"         → ("PR", None)
    """
    text = address.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    # --- Planta ---
    planta: str | None = None

    planta_keywords = [
        (r"\bentresuelo\b",  "EN"),
        (r"\bentsol\b",      "EN"),   # catalán
        (r"\bprincipal\b",   "PR"),
        (r"\bppal\b",        "PR"),
        (r"\batico\b",       "AT"),
        (r"\bsobreatic[oo]\b", "SA"),
        (r"\bsotano\b",      "SS"),
        (r"\bsemisotano\b",  "SS"),
        (r"\bbajo\b",        "BJ"),
        (r"\bbajos\b",       "BJ"),
    ]
    for pattern, code in planta_keywords:
        if re.search(pattern, text):
            planta = code
            break

    if planta is None:
        # Números de planta: "3º", "3°", "3o", "planta 3", "p3", "piso 3"
        m = re.search(r"(?:planta|piso|p\.?)\s*(\d{1,2})|(\d{1,2})\s*[º°o]", text)
        if m:
            num = m.group(1) or m.group(2)
            planta = str(int(num)).zfill(2)

    # --- Puerta ---
    puerta: str | None = None

    puerta_keywords = [
        (r"\bizquierda\b|\bizq\.?\b|\biz\b", "IZ"),
        (r"\bderecha\b|\bdcha\.?\b|\bdr\b",  "DR"),
        (r"\bcentro\b|\bcen\b",              "CE"),
        (r"\binterior\b|\bint\b",            "IN"),
        (r"\bexterior\b|\bext\b",            "EX"),
    ]
    for pattern, code in puerta_keywords:
        if re.search(pattern, text):
            puerta = code
            break

    if puerta is None:
        # Letra sola o número tras la planta: "Entresuelo 1", "3º B", "Planta 4, 2"
        # Buscamos número o letra que sigue a la planta o a una coma
        m = re.search(
            r"(?:entresuelo|entsol|principal|atico|bajo|bajos|planta|piso|[º°o])\s*[,\s]\s*([a-z\d]{1,2})\b",
            text,
        )
        if m:
            val = m.group(1).upper()
            puerta = val.zfill(2) if val.isdigit() else val

    return planta, puerta


def pick_best_inmueble(inmuebles: list[dict[str, Any]]) -> dict[str, Any] | None:
    """De la lista de inmuebles devuelta por Catastro, elige el más representativo.

    Prioridad: uso Residencial > mayor superficie. Si no hay residencial, el mayor.
    """
    if not inmuebles:
        return None

    def surface(i: dict[str, Any]) -> float:
        try:
            return float(i.get("datosEconomicos", {}).get("superficieConstruida", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    residenciales = [
        i for i in inmuebles
        if "residencial" in str(i.get("datosEconomicos", {}).get("uso", "")).lower()
    ]
    candidates = residenciales or inmuebles
    return max(candidates, key=surface)
