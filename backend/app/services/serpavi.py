"""SERPAVI — Precio de alquiler real por municipio (fuente fiscal AEAT).

Carga el JSON pre-procesado en backend/data/ (extraído del XLSX oficial MIVAU 2024).
Granularidad: 2.555 municipios. Datos fiscales reales, no listings.
Fuente: https://serpavi.mivau.gob.es/
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "serpavi_alquiler_municipios_2024.json"

SOURCE_URL = "https://serpavi.mivau.gob.es/"
SOURCE_TITLE = "SERPAVI (MIVAU) — Precio alquiler por municipio 2024 (datos fiscales AEAT)"


_LEADING_ARTICLES = ("a ", "o ", "as ", "os ", "el ", "la ", "los ", "las ", "l ", "es ")


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _variants(name: str) -> list[str]:
    n = _normalize(name)
    out = [n]
    for art in _LEADING_ARTICLES:
        if n.startswith(art):
            out.append(n[len(art):].strip())
            break
    stripped = re.sub(r"\s+[aoel]\s*$", "", n).strip()
    if stripped and stripped != n:
        out.append(stripped)
    return out


@lru_cache(maxsize=1)
def _load() -> list[dict[str, Any]]:
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["municipios"]


def _prov_match(row_prov: str, provincia: str | None) -> bool:
    if provincia is None:
        return True
    return any(rv == pv for rv in _variants(row_prov) for pv in _variants(provincia))


def lookup(municipio: str, provincia: str | None = None) -> dict[str, Any] | None:
    """Devuelve el registro SERPAVI para el municipio más similar.

    Maneja artículos antepuestos/pospuestos del gallego y catalán.
    """
    rows = _load()
    nm_variants = _variants(municipio)

    # 1. Exact match con provincia
    for row in rows:
        rv = _variants(row["municipio"])
        if any(nv == v for nv in nm_variants for v in rv):
            if _prov_match(row["provincia"], provincia):
                return row

    # 2. Exact match sin provincia
    for row in rows:
        rv = _variants(row["municipio"])
        if any(nv == v for nv in nm_variants for v in rv):
            return row

    # 3. Partial match con provincia
    for row in rows:
        rm = _normalize(row["municipio"])
        if any(nv in rm or rm in nv for nv in nm_variants):
            if _prov_match(row["provincia"], provincia):
                return row

    # 4. Partial match sin provincia
    for row in rows:
        rm = _normalize(row["municipio"])
        if any(nv in rm or rm in nv for nv in nm_variants):
            return row

    return None
