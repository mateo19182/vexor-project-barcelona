"""Address → approximate property value signals (geocoding + public statistics)."""

from __future__ import annotations

from datetime import UTC, datetime
from app.models import (
    Case,
    GeocodeHit,
    MoneyBand,
    PropertyEstimate,
    SourceCitation,
)
from Pedro.services import barcelona_open_data, eurostat_hpi, geocoding

DISCLAIMER_ES = (
    "Estimación orientativa, no tasación oficial ni valor de referencia catastral. "
    "No sustituye peritación ni informe registral. Los importes derivan de datos "
    "públicos agregados y pueden desviarse del mercado actual en la finca concreta."
)

CKAN_PACKAGE_URL = (
    "https://opendata-ajuntament.barcelona.cat/data/ca/dataset/habitatges-2na-ma"
)
EUROSTAT_HPI_PAGE = "https://ec.europa.eu/eurostat/databrowser/view/prc_hpi_q/default/table"
OSM_NOMINATIM_POLICY = "https://operations.osmfoundation.org/policies/nominatim/"
PHOTON_INFO = "https://photon.komoot.io/"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_barcelona_city(hints: dict[str, str | None]) -> bool:
    city = (hints.get("city") or "").lower()
    return "barcelona" in city


async def estimate_from_case(case: Case) -> PropertyEstimate:
    gaps: list[str] = []
    sources: list[SourceCitation] = []

    if not case.address or not case.address.strip():
        gaps.append("Sin dirección no se puede geocodificar ni contextualizar el inmueble.")
        return PropertyEstimate(
            disclaimer=DISCLAIMER_ES,
            geocode=None,
            sale_value=None,
            rent_monthly=None,
            offer_price_eur_m2_band=None,
            macro_hpi_note=None,
            sources=sources,
            gaps=gaps,
        )

    q = geocoding.normalize_address_line(case.address)
    country = (case.country or "").strip().upper()
    if len(country) != 2:
        gaps.append("Código de país ISO-2 inválido o ausente.")
        return PropertyEstimate(
            disclaimer=DISCLAIMER_ES,
            geocode=None,
            sale_value=None,
            rent_monthly=None,
            offer_price_eur_m2_band=None,
            macro_hpi_note=None,
            sources=sources,
            gaps=gaps,
        )

    try:
        hit, engine = await geocoding.geocode_best_effort(query=q, country_iso2=country)
    except Exception as e:  # noqa: BLE001 — traceable failure, no fake data
        gaps.append(f"Geocodificación no disponible: {e!s}.")
        sources.append(
            SourceCitation(
                title="Nominatim (OpenStreetMap) — política de uso",
                url=OSM_NOMINATIM_POLICY,
                retrieved_at=_now_iso(),
                note="Fallo en cadena Nominatim → Photon",
            )
        )
        return PropertyEstimate(
            disclaimer=DISCLAIMER_ES,
            geocode=None,
            sale_value=None,
            rent_monthly=None,
            offer_price_eur_m2_band=None,
            macro_hpi_note=None,
            sources=sources,
            gaps=gaps,
        )

    if hit is None:
        gaps.append(
            "Geocodificación sin resultados (Nominatim y Photon) para la dirección y país indicados."
        )
        sources.append(
            SourceCitation(
                title="Nominatim (OpenStreetMap)",
                url="https://nominatim.openstreetmap.org/",
                retrieved_at=_now_iso(),
                note="Sin coincidencias",
            )
        )
        sources.append(
            SourceCitation(
                title="Photon API (datos OpenStreetMap, Komoot)",
                url=PHOTON_INFO,
                retrieved_at=_now_iso(),
                note="Sin coincidencias",
            )
        )
        return PropertyEstimate(
            disclaimer=DISCLAIMER_ES,
            geocode=None,
            sale_value=None,
            rent_monthly=None,
            offer_price_eur_m2_band=None,
            macro_hpi_note=None,
            sources=sources,
            gaps=gaps,
        )

    hints = geocoding.extract_location_hints(hit)
    raw_pid = hit.get("place_id")
    place_id: int | None
    if isinstance(raw_pid, int):
        place_id = raw_pid
    elif isinstance(raw_pid, str) and raw_pid.isdigit():
        place_id = int(raw_pid)
    else:
        place_id = None

    geo = GeocodeHit(
        display_name=hints.get("display_name"),
        lat=hints.get("lat"),
        lon=hints.get("lon"),
        road=hints.get("road"),
        house_number=hints.get("house_number"),
        postcode=hints.get("postcode"),
        suburb=hints.get("suburb"),
        city_district=hints.get("city_district"),
        city=hints.get("city"),
        state=hints.get("state"),
        country_code=hints.get("country_code"),
        nominatim_place_id=place_id,
        licence=hit.get("licence"),
    )
    if engine == "nominatim":
        sources.append(
            SourceCitation(
                title="Nominatim (OpenStreetMap) — resultado de búsqueda",
                url="https://nominatim.openstreetmap.org/",
                retrieved_at=_now_iso(),
                note=f"place_id={hit.get('place_id')}, licence={hit.get('licence')}",
            )
        )
    else:
        sources.append(
            SourceCitation(
                title="Photon API (datos OpenStreetMap, Komoot)",
                url=PHOTON_INFO,
                retrieved_at=_now_iso(),
                note=f"osm_id={hit.get('place_id')}, licence={hit.get('licence')}",
            )
        )

    # --- Eurostat HPI (country macro) ---
    euro_geo = country
    latest_period, base_idx, latest_idx, hpi_ratio = await eurostat_hpi.hpi_ratio_since_latest(
        geo=euro_geo
    )
    macro_note: str | None = None
    if latest_period and base_idx is not None and latest_idx is not None and hpi_ratio is not None:
        macro_note = (
            f"Eurostat PRC_HPI_Q: vivienda existente, índice 2015=100. "
            f"Base 2015-Q4={base_idx:.2f}, último ({latest_period})={latest_idx:.2f}, "
            f"ratio={hpi_ratio:.3f}."
        )
        sources.append(
            SourceCitation(
                title="Eurostat — House price index (PRC_HPI_Q)",
                url=EUROSTAT_HPI_PAGE,
                retrieved_at=_now_iso(),
                note=f"País {euro_geo}, período actual {latest_period}",
            )
        )
    else:
        gaps.append(
            "Índice Eurostat de precios de vivienda no disponible para este país "
            "(o falló la consulta); no se aplica escalado macro."
        )

    # --- Barcelona: €/m² oferta 2015 (Idealista vía Ajuntament) + escalado HPI país ---
    offer_band: MoneyBand | None = None
    sale_value: MoneyBand | None = None
    methodology: str | None = None

    if country == "ES" and _is_barcelona_city(hints) and hpi_ratio is not None:
        rows = await barcelona_open_data.load_barri_rows()
        tokens = geocoding.barcelona_match_tokens(hints)
        row, matched = barcelona_open_data.pick_barcelona_row(rows, match_tokens=tokens)
        base_m2 = barcelona_open_data.row_eur_per_m2_2015(row) if row else None
        if base_m2 is not None:
            scaled = base_m2 * hpi_ratio
            # Banda amplia: incertidumbre modelo + serie2015 base
            low = scaled * 0.75
            high = scaled * 1.35
            offer_band = MoneyBand(
                min_eur=round(low, 2),
                max_eur=round(high, 2),
                currency="EUR",
                basis=(
                    f"€/m² oferta segunda mano 2015 (Ajuntament, fuente Idealista) "
                    f"ajustado por índice HPI Eurostat país {euro_geo} ({latest_period} vs 2015-Q4). "
                    f"Coincidencia barrio: {matched or 'desconocida'}."
                ),
            )
            methodology = (
                "Precio medio oferta €/m² en 2015 por barrio (datos abiertos Ajuntament) "
                "multiplicado por ratio HPI vivienda existente Eurostat (último trimestre / 2015-Q4)."
            )
            sources.append(
                SourceCitation(
                    title="Ajuntament de Barcelona — habitatges segona mà €/m² (CKAN)",
                    url=CKAN_PACKAGE_URL,
                    retrieved_at=_now_iso(),
                    note="Serie 2015; fuente original Idealista según metadatos del dataset",
                )
            )
            if case.property_sqm is not None and case.property_sqm > 0:
                sale_value = MoneyBand(
                    min_eur=round(low * case.property_sqm, 2),
                    max_eur=round(high * case.property_sqm, 2),
                    currency="EUR",
                    basis=(
                        f"Banda de valor de venta aproximada = (€/m² banda) × {case.property_sqm} m² "
                        f"declarados en el caso. Tipología informada: "
                        f"{case.property_typology or 'no especificada'}."
                    ),
                )
            else:
                gaps.append(
                    "Sin superficie (m²) no se estima el valor total de venta; solo €/m² aproximado."
                )
        else:
            gaps.append(
                "No se pudo leer el precio €/m² 2015 del dataset del Ajuntament para esta fila."
            )
    elif country == "ES":
        gaps.append(
            "Dirección fuera de Barcelona ciudad: este pipeline no integra aún €/m² municipal "
            "de otra fuente abierta; solo contexto HPI nacional."
        )
    else:
        gaps.append(
            "Fuera de España no se aplica el dataset de barrios de Barcelona; "
            "solo contexto HPI Eurostat si disponible."
        )

    gaps.append(
        "Alquiler mensual: no integrado (falta fuente abierta homogénea por dirección en este servicio)."
    )

    return PropertyEstimate(
        disclaimer=DISCLAIMER_ES,
        geocode=geo,
        sale_value=sale_value,
        rent_monthly=None,
        offer_price_eur_m2_band=offer_band,
        macro_hpi_note=macro_note,
        methodology=methodology,
        sources=sources,
        gaps=gaps,
    )
