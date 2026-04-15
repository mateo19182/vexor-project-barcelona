"""MITMA — Valor tasado de vivienda libre por municipio.

Carga el JSON pre-procesado en backend/data/ (generado de 35103500.XLS, Q4 2025).
Granularidad: ~306 municipios de más de 25.000 habitantes.
Fuente: https://apps.fomento.gob.es/boletinonline2/sedal/35103500.XLS
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "mitma_valor_tasado_T4_2025.json"

SOURCE_URL = "https://apps.fomento.gob.es/boletinonline2/sedal/35103500.XLS"
SOURCE_TITLE = "MITMA/MIVAU — Valor tasado vivienda libre por municipios (T4 2025)"


# Artículos que aparecen antepuestos en topónimos gallegos, catalanes y castellanos.
# "Coruña (A)" en MITMA vs "A Coruña" del geocoder — hay que saber ignorar el artículo.
_LEADING_ARTICLES = ("a ", "o ", "as ", "os ", "el ", "la ", "los ", "las ", "l ", "es ")


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _variants(name: str) -> list[str]:
    """Genera variantes del nombre para matching robusto.

    'A Coruña' → ['a coruna', 'coruna']
    'Coruña (A)' → ['coruna a', 'coruna']
    """
    n = _normalize(name)
    out = [n]
    # Quitar artículo inicial
    for art in _LEADING_ARTICLES:
        if n.startswith(art):
            out.append(n[len(art):].strip())
            break
    # Quitar artículo final entre paréntesis o tras coma: "coruna a" → "coruna"
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
    rp_variants = _variants(row_prov)
    p_variants = _variants(provincia)
    return any(rv == pv for rv in rp_variants for pv in p_variants)


def lookup(municipio: str, provincia: str | None = None) -> dict[str, Any] | None:
    """Devuelve el registro MITMA para el municipio más similar.

    Maneja artículos antepuestos/pospuestos del gallego y catalán
    ('A Coruña' / 'Coruña (A)', 'L'Hospitalet' / 'Hospitalet de Llobregat').
    """
    rows = _load()
    nm_variants = _variants(municipio)

    # 1. Exact match (cualquier variante) con provincia
    for row in rows:
        rv = _variants(row["municipio"])
        if any(nv == v for nv in nm_variants for v in rv):
            if _prov_match(row["provincia"], provincia):
                return row

    # 2. Exact match sin filtro provincia
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
