"""Tests for app/pipeline/modules/property.py

Verifica:
  1. Que el módulo cumple el protocolo Module (name, requires, async run).
  2. Casos de skip (país no ES, sin dirección).
  3. Flujo con geocoding + Catastro mockeados — MITMA/SERPAVI usan datos reales.
  4. Estimaciones numéricas correctas.
  5. Estructura del ModuleResult (signals, facts, gaps, raw).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models import Case
from app.pipeline.base import Context, ModuleResult, context_from_case
from app.pipeline.modules.property import PropertyModule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(**kwargs) -> Case:
    defaults = dict(
        case_id="test-001",
        country="ES",
        debt_eur=10_000.0,
        debt_origin="personal_loan",
        debt_age_months=12,
        call_attempts=3,
        call_outcome="voicemail",
        legal_asset_finding="no_assets_found",
    )
    defaults.update(kwargs)
    return Case(**defaults)


def _make_ctx(address: str | None = "Calle Gran Vía 1, Madrid", **kwargs) -> Context:
    case = _make_case(address=address, **kwargs)
    return context_from_case(case)


# Geocoding hit simulando Madrid capital
MOCK_GEO_HIT = {
    "lat": "40.4168",
    "lon": "-3.7038",
    "display_name": "Gran Vía, Madrid, Comunidad de Madrid, España",
    "licence": "ODbL",
    "place_id": 12345,
    "address": {
        "road": "Gran Vía",
        "house_number": "1",
        "city": "Madrid",
        "state": "Comunidad de Madrid",
        "postcode": "28013",
        "country_code": "es",
    },
}

# Inmueble Catastro simulado
MOCK_INMUEBLE = {
    "tipoBien": "UR",
    "referenciaCatastral": {"referenciaCatastral": "0847106VK4704F0006FI"},
    "direccion": {"codigoPostal": "28013"},
    "datosEconomicos": {
        "uso": "Residencial",
        "superficieConstruida": "90",
        "añoConstruccion": "1970",
        "coeficienteParticipacion": "5.5",
    },
    "unidadesConstructivas": [],
}


# ---------------------------------------------------------------------------
# 1. Protocolo Module
# ---------------------------------------------------------------------------

class TestModuleProtocol:
    def test_has_name(self):
        assert PropertyModule.name == "property"

    def test_has_requires(self):
        assert hasattr(PropertyModule, "requires")
        assert isinstance(PropertyModule.requires, tuple)
        assert "address" in PropertyModule.requires

    def test_run_is_coroutine(self):
        import inspect
        assert inspect.iscoroutinefunction(PropertyModule.run)

    def test_instance_is_module_protocol(self):
        from app.pipeline.base import Module
        m = PropertyModule()
        assert isinstance(m, Module)


# ---------------------------------------------------------------------------
# 2. Casos de skip
# ---------------------------------------------------------------------------

class TestSkipCases:
    @pytest.mark.asyncio
    async def test_skips_non_es_country(self):
        ctx = _make_ctx(country="PT")
        result = await PropertyModule().run(ctx)
        assert result.status == "skipped"
        assert result.name == "property"
        assert any("ES" in g for g in result.gaps)

    @pytest.mark.asyncio
    async def test_skips_with_no_address(self):
        ctx = _make_ctx(address=None)
        ctx.address = None  # clear whatever context_from_case set
        result = await PropertyModule().run(ctx)
        assert result.status == "skipped"
        assert result.name == "property"

    @pytest.mark.asyncio
    async def test_skips_with_empty_address(self):
        ctx = _make_ctx(address="   ")
        ctx.address = "   "
        result = await PropertyModule().run(ctx)
        assert result.status == "skipped"


# ---------------------------------------------------------------------------
# 3. Flujo completo con mocks de red
# ---------------------------------------------------------------------------

class TestFullFlowMocked:
    """MITMA y SERPAVI usan JSON real. Catastro y geocoding están mockeados."""

    @pytest.mark.asyncio
    async def test_ok_status_with_valid_address(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert result.status == "ok"
        assert result.name == "property"

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert isinstance(result, ModuleResult)
        assert result.summary != ""
        assert isinstance(result.signals, list)
        assert isinstance(result.facts, list)
        assert isinstance(result.gaps, list)
        assert isinstance(result.raw, dict)

    @pytest.mark.asyncio
    async def test_catastro_data_in_raw(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert "catastro" in result.raw
        cd = result.raw["catastro"]
        assert cd["referencia_catastral"] == "0847106VK4704F0006FI"
        assert cd["superficie_m2"] == pytest.approx(90.0)
        assert cd["uso"] == "Residencial"
        assert cd["ano_construccion"] == "1970"

    @pytest.mark.asyncio
    async def test_mitma_and_serpavi_in_raw(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert "mitma" in result.raw, "MITMA debe estar en raw para Madrid"
        assert result.raw["mitma"]["eur_m2_total"] == pytest.approx(5286.2)

        assert "serpavi" in result.raw, "SERPAVI debe estar en raw para Madrid"
        assert result.raw["serpavi"]["alquiler_eur_m2_mes_mediana"] == pytest.approx(13.97)


# ---------------------------------------------------------------------------
# 4. Estimaciones numéricas
# ---------------------------------------------------------------------------

class TestEstimations:
    @pytest.mark.asyncio
    async def test_sale_estimate_present_when_sqm_known(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),  # 90 m²
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        est = result.raw.get("estimates", {})
        assert "venta_total_eur_low" in est
        assert "venta_total_eur_high" in est

        # 90 m² × 5286 €/m² × 0.80 = ~380k
        assert est["venta_total_eur_low"] == pytest.approx(90 * 5286.2 * 0.80, rel=0.01)
        assert est["venta_total_eur_high"] == pytest.approx(90 * 5286.2 * 1.20, rel=0.01)

    @pytest.mark.asyncio
    async def test_rent_estimate_present_when_sqm_known(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),  # 90 m²
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        est = result.raw.get("estimates", {})
        assert "alquiler_mensual_eur_low" in est
        assert "alquiler_mensual_eur_high" in est

        # 90 m² × 13.97 €/m²/mes × 0.85 = ~1069
        assert est["alquiler_mensual_eur_low"] == pytest.approx(90 * 13.97 * 0.85, rel=0.01)

    @pytest.mark.asyncio
    async def test_estimates_use_case_sqm_when_catastro_missing(self):
        """Si Catastro no devuelve inmuebles, usamos property_sqm del caso."""
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[]),
            ),
        ):
            ctx = _make_ctx(property_sqm=100.0)
            result = await PropertyModule().run(ctx)

        est = result.raw.get("estimates", {})
        assert "venta_total_eur_low" in est
        # 100 m² × 5286 €/m² × 0.80 ≈ 422k
        assert est["venta_total_eur_low"] == pytest.approx(100 * 5286.2 * 0.80, rel=0.01)


# ---------------------------------------------------------------------------
# 5. Signals y facts
# ---------------------------------------------------------------------------

class TestSignalsAndFacts:
    @pytest.mark.asyncio
    async def test_emits_asset_signals(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert len(result.signals) >= 1
        kinds = {s.kind for s in result.signals}
        assert "asset" in kinds

    @pytest.mark.asyncio
    async def test_signals_have_source_url(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        for sig in result.signals:
            assert sig.source.startswith("http"), f"Signal sin URL: {sig}"
            assert 0.0 <= sig.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_catastro_fact_emitted(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[MOCK_INMUEBLE]),
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        assert len(result.facts) >= 1
        all_claims = " ".join(f.claim for f in result.facts)
        assert "0847106VK4704F0006FI" in all_claims  # referencia catastral


# ---------------------------------------------------------------------------
# 6. Degradación elegante (gaps, no excepciones)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_geocoding_failure_adds_gap_not_exception(self):
        with patch(
            "app.pipeline.modules.property.geocoding.geocode_best_effort",
            new=AsyncMock(side_effect=Exception("Nominatim timeout")),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        # No debe lanzar excepción — el runner la capturaría,
        # pero queremos que el módulo mismo la gestione
        assert result.name == "property"
        assert any("Geocodificación" in g for g in result.gaps)

    @pytest.mark.asyncio
    async def test_catastro_failure_adds_gap_not_exception(self):
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[]),  # sin resultados
            ),
        ):
            ctx = _make_ctx()
            result = await PropertyModule().run(ctx)

        # Sin Catastro, aún debe intentar MITMA y SERPAVI
        assert "catastro" not in result.raw or result.raw.get("catastro") is None
        assert "mitma" in result.raw  # Madrid existe en MITMA
        assert any("Catastro" in g for g in result.gaps)

    @pytest.mark.asyncio
    async def test_no_estimates_without_sqm(self):
        """Sin m² (ni Catastro ni case.property_sqm) no hay estimación de valor total."""
        no_sqm_inmueble: dict[str, Any] = {
            "tipoBien": "UR",
            "referenciaCatastral": {"referenciaCatastral": "ABC123"},
            "direccion": {},
            "datosEconomicos": {
                "uso": "Residencial",
                "superficieConstruida": None,  # sin m²
                "añoConstruccion": "2000",
            },
        }
        with (
            patch(
                "app.pipeline.modules.property.geocoding.geocode_best_effort",
                new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_vias",
                new=AsyncMock(return_value=[{"nombreVia": "GRAN VÍA", "tipoVia": "CL"}]),
            ),
            patch(
                "app.pipeline.modules.property.catastro_svc.get_inmuebles_by_address",
                new=AsyncMock(return_value=[no_sqm_inmueble]),
            ),
        ):
            ctx = _make_ctx()  # sin property_sqm
            result = await PropertyModule().run(ctx)

        est = result.raw.get("estimates", {})
        assert "venta_total_eur_low" not in est
        assert "alquiler_mensual_eur_low" not in est
