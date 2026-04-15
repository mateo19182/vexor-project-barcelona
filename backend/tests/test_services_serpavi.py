"""Tests for app/services/serpavi.py

Los datos vienen del JSON real en backend/data/ — no hace falta mock.
"""

import pytest

from app.services import serpavi


def test_lookup_exact_capital():
    row = serpavi.lookup("Madrid")
    assert row is not None
    assert row["municipio"] == "Madrid"
    assert row["alquiler_eur_m2_mes_mediana"] == pytest.approx(13.97)


def test_lookup_barcelona():
    row = serpavi.lookup("Barcelona")
    assert row is not None
    assert row["alquiler_eur_m2_mes_mediana"] > 10  # >10 €/m²/mes en BCN


def test_lookup_case_insensitive():
    row = serpavi.lookup("sevilla")
    assert row is not None
    assert row["municipio"] == "Sevilla"


def test_lookup_accent_insensitive():
    row_accented = serpavi.lookup("Málaga")
    row_plain = serpavi.lookup("Malaga")
    assert row_accented is not None
    assert row_plain is not None
    assert row_accented["municipio"] == row_plain["municipio"]


def test_lookup_not_found_returns_none():
    row = serpavi.lookup("PuebloFicticio12345", "ProvinciaFicticia")
    assert row is None


def test_lookup_fields_present():
    row = serpavi.lookup("Bilbao")
    assert row is not None
    required_fields = [
        "municipio",
        "provincia",
        "alquiler_eur_m2_mes_mediana",
        "alquiler_eur_m2_mes_p25",
        "alquiler_eur_m2_mes_p75",
        "alquiler_eur_mes_mediana",
        "n_viviendas_colectiva",
    ]
    for f in required_fields:
        assert f in row, f"Campo faltante: {f}"


def test_lookup_rent_in_plausible_range():
    for city in ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao", "Zaragoza"]:
        row = serpavi.lookup(city)
        assert row is not None, f"No SERPAVI row for {city}"
        alq = row["alquiler_eur_m2_mes_mediana"]
        assert 2 < alq < 20, f"{city}: €/m²/mes = {alq} fuera de rango esperado"


def test_lookup_percentiles_ordered():
    # P25 ≤ mediana ≤ P75 siempre
    for city in ["Madrid", "Barcelona", "Valencia"]:
        row = serpavi.lookup(city)
        assert row is not None
        p25 = row["alquiler_eur_m2_mes_p25"]
        med = row["alquiler_eur_m2_mes_mediana"]
        p75 = row["alquiler_eur_m2_mes_p75"]
        if p25 and med and p75:
            assert p25 <= med <= p75, (
                f"{city}: percentiles fuera de orden P25={p25} med={med} P75={p75}"
            )


def test_lookup_provincia_disambiguates():
    row = serpavi.lookup("Santiago de Compostela", "Coruña")
    assert row is not None
    assert "Santiago" in row["municipio"]


def test_coverage_is_large():
    # SERPAVI cubre 2.555 municipios — debe encontrar ciudades medianas
    for city in ["Vigo", "Alicante", "Córdoba", "Valladolid", "Pamplona"]:
        row = serpavi.lookup(city)
        assert row is not None, f"SERPAVI debería cubrir {city}"
