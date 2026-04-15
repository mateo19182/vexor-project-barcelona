"""Tests for app/services/catastro.py

parse_tipo_via y pick_best_inmueble no hacen I/O — tests unitarios puros.
get_vias / get_inmuebles_by_address hacen HTTP — se testean solo si hay API key.
"""

import pytest

from app.services.catastro import parse_tipo_via, pick_best_inmueble


# ---------------------------------------------------------------------------
# parse_tipo_via
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("road, expected_tipo, expected_nombre_contains", [
    ("Calle Gran Vía",         "CL", "GRAN VÍA"),
    ("Calle Mayor",            "CL", "MAYOR"),
    ("Avenida Diagonal",       "AV", "DIAGONAL"),
    ("Avinguda Diagonal",      "AV", "DIAGONAL"),       # catalán
    ("Paseo de la Castellana", "PS", "CASTELLANA"),     # strip "de la"
    ("Passeig de Gràcia",      "PS", "GRÀCIA"),         # strip "de"
    ("Passeig de Maragall",    "PS", "MARAGALL"),       # caso real Barcelona
    ("Paseo del Prado",        "PS", "PRADO"),          # strip "del"
    ("Calle de Alcalá",        "CL", "ALCALÁ"),         # strip "de"
    ("Avenida de la Constitución", "AV", "CONSTITUCIÓN"),  # strip "de la"
    ("Plaza Mayor",            "PZ", "MAYOR"),
    ("Placa Catalunya",        "PZ", "CATALUNYA"),      # catalán
    ("Rúa do Vilar",           "RU", "DO VILAR"),       # gallego: "do" no se stripea
    ("Rua do Vilar",           "RU", "DO VILAR"),
    ("Carretera de Burgos",    "CR", "BURGOS"),         # strip "de"
    ("Camino de Santiago",     "CM", "SANTIAGO"),       # strip "de"
    ("Gran Vía",               "CL", "GRAN VÍA"),       # sin prefijo → fallback CL
    ("Carrer de Balmes",       "CL", "BALMES"),         # catalán, strip "de"
    ("Travesía de las Flores", "TR", "FLORES"),         # strip "de las"
])
def test_parse_tipo_via(road, expected_tipo, expected_nombre_contains):
    tipo, nombre = parse_tipo_via(road)
    assert tipo == expected_tipo, f"'{road}' → tipo={tipo!r}, esperado {expected_tipo!r}"
    assert expected_nombre_contains in nombre, (
        f"'{road}' → nombre={nombre!r}, esperaba contener '{expected_nombre_contains}'"
    )


def test_parse_tipo_via_returns_uppercase_nombre():
    _, nombre = parse_tipo_via("Calle de la Paz")
    assert nombre == nombre.upper()


def test_parse_tipo_via_unknown_prefix_fallback_to_cl():
    tipo, nombre = parse_tipo_via("Diagonal 123")
    # Sin prefijo reconocido → CL
    assert tipo == "CL"
    assert nombre  # no vacío


# ---------------------------------------------------------------------------
# pick_best_inmueble
# ---------------------------------------------------------------------------

def _inmueble(uso: str, m2: float) -> dict:
    return {
        "datosEconomicos": {"uso": uso, "superficieConstruida": str(m2)},
        "referenciaCatastral": {},
        "direccion": {},
    }


def test_pick_best_inmueble_empty():
    assert pick_best_inmueble([]) is None


def test_pick_best_inmueble_single():
    items = [_inmueble("Residencial", 80)]
    result = pick_best_inmueble(items)
    assert result is not None
    assert result["datosEconomicos"]["uso"] == "Residencial"


def test_pick_best_inmueble_prefers_residential():
    items = [
        _inmueble("Comercial", 500),
        _inmueble("Residencial", 80),
        _inmueble("Almacén", 200),
    ]
    result = pick_best_inmueble(items)
    assert result["datosEconomicos"]["uso"] == "Residencial"


def test_pick_best_inmueble_largest_when_no_residential():
    items = [
        _inmueble("Comercial", 100),
        _inmueble("Oficinas", 500),
        _inmueble("Almacén", 50),
    ]
    result = pick_best_inmueble(items)
    assert result["datosEconomicos"]["superficieConstruida"] == "500"


def test_pick_best_inmueble_largest_residential_among_several():
    items = [
        _inmueble("Residencial", 60),
        _inmueble("Residencial", 120),
        _inmueble("Residencial", 90),
    ]
    result = pick_best_inmueble(items)
    assert result["datosEconomicos"]["superficieConstruida"] == "120"
