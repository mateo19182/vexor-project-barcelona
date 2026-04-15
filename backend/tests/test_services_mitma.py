"""Tests for app/services/mitma.py

Los datos vienen del JSON real en backend/data/ — no hace falta mock.
"""

import pytest

from app.services import mitma


def test_lookup_exact_capital():
    row = mitma.lookup("Madrid")
    assert row is not None
    assert row["municipio"] == "Madrid"
    assert row["eur_m2_total"] == pytest.approx(5286.2)
    assert row["n_tasaciones_total"] == 12077


def test_lookup_exact_with_provincia():
    row = mitma.lookup("Barcelona", "Barcelona")
    assert row is not None
    assert row["municipio"] == "Barcelona"
    assert row["eur_m2_total"] > 0


def test_lookup_case_insensitive():
    row = mitma.lookup("madrid")
    assert row is not None
    assert row["municipio"] == "Madrid"


def test_lookup_accent_insensitive():
    # "Málaga" con y sin tilde deben resolverse igual
    row_accented = mitma.lookup("Málaga")
    row_plain = mitma.lookup("Malaga")
    assert row_accented is not None
    assert row_plain is not None
    assert row_accented["municipio"] == row_plain["municipio"]


def test_lookup_partial_name():
    # "Jerez" debe encontrar "Jerez de la Frontera"
    row = mitma.lookup("Jerez")
    assert row is not None
    assert "Jerez" in row["municipio"]


def test_lookup_provincia_disambiguates():
    # Hay varios municipios llamados "Alcalá" — la provincia ayuda a desempatar
    row_madrid = mitma.lookup("Alcalá de Henares", "Madrid")
    assert row_madrid is not None
    assert "Alcalá" in row_madrid["municipio"]


def test_lookup_not_found_returns_none():
    # Municipio ficticio
    row = mitma.lookup("Puebloquenoexiste", "Provinciaquenoexiste")
    assert row is None


def test_lookup_fields_present():
    row = mitma.lookup("Sevilla")
    assert row is not None
    assert "eur_m2_total" in row
    assert "eur_m2_vivienda_nueva" in row
    assert "eur_m2_vivienda_usada" in row
    assert "n_tasaciones_total" in row
    assert "provincia" in row
    assert "municipio" in row


def test_lookup_eur_m2_in_plausible_range():
    for city in ["Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza"]:
        row = mitma.lookup(city)
        assert row is not None, f"No MITMA row for {city}"
        assert 500 < row["eur_m2_total"] < 10_000, (
            f"{city}: €/m² = {row['eur_m2_total']} fuera de rango esperado"
        )
