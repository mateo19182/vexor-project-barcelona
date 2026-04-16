"""Property enrichment module.

Flujo para direcciones en España (country=ES):
  1. Geocoding (Nominatim/Photon) → provincia, municipio, calle, número
  2. Catastro API → m², uso, año de construcción, referencia catastral
  3. MITMA T4 2025 → €/m² valor tasado de venta por municipio
  4. SERPAVI 2024  → €/m²/mes alquiler real (datos fiscales AEAT) por municipio
  5. Estimaciones = m² × precio_unitario, con banda de incertidumbre

Emite:
  - signals: `asset` con la estimación de valor/alquiler
  - facts:   datos físicos del inmueble (m², uso, año, RC)
  - raw:     todo el detalle estructurado para síntesis o respuesta API
  - gaps:    qué no se pudo obtener y por qué
"""

from __future__ import annotations

import sys
from typing import Any

from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult
from app.services import catastro as catastro_svc
from app.services import geocoding
from app.services import mitma as mitma_svc
from app.services import serpavi as serpavi_svc

MITMA_SOURCE = "https://apps.fomento.gob.es/boletinonline2/sedal/35103500.XLS"
SERPAVI_SOURCE = "https://serpavi.mivau.gob.es/"
CATASTRO_SOURCE = "https://catastro-api.es"

# Banda de incertidumbre aplicada a las estimaciones
SALE_BAND_LOW = 0.80
SALE_BAND_HIGH = 1.20
RENT_BAND_LOW = 0.85
RENT_BAND_HIGH = 1.15

# Prefijos administrativos que Nominatim antepone al nombre de la provincia
# cuando devuelve la CCAA en lugar de la provincia real.
_PROVINCIA_PREFIJOS = (
    "comunidad de ",
    "comunidad foral de ",
    "región de ",
    "principado de ",
    "islas ",
    "illes ",
    "país ",
)


def _clean_provincia(raw: str | None) -> str:
    """Devuelve el nombre de provincia limpio para Catastro.

    Nominatim a veces devuelve "Comunidad de Madrid" en lugar de "Madrid",
    "Región de Murcia" en lugar de "Murcia", etc.
    """
    if not raw:
        return ""
    s = raw.strip()
    lower = s.lower()
    for prefix in _PROVINCIA_PREFIJOS:
        if lower.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _fmt_eur(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M €"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k €"
    return f"{v:.0f} €"


class PropertyModule:
    name = "property"
    requires: tuple[str, ...] = ("address",)

    async def run(self, ctx: Context) -> ModuleResult:
        # Solo España por ahora — MITMA y SERPAVI son bases nacionales ES
        if (ctx.case.country or "").upper() != "ES":
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["property enrichment solo disponible para ES (country≠ES)"],
            )

        address = ctx.address or ctx.case.address or ""
        if not address.strip():
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["sin dirección no se puede enriquecer el inmueble"],
            )

        gaps: list[str] = []
        facts: list[Fact] = []
        signals: list[Signal] = []
        raw: dict[str, Any] = {}

        # --- 1. Geocoding ---
        _log(f"[property] geocoding '{address}'")
        q = geocoding.normalize_address_line(address)
        try:
            hit, engine = await geocoding.geocode_best_effort(query=q, country_iso2="ES")
        except Exception as e:  # noqa: BLE001
            gaps.append(f"Geocodificación falló: {e}")
            hit, engine = None, "none"

        hints: dict[str, str | None] = {}
        if hit:
            hints = geocoding.extract_location_hints(hit)
            raw["geocode"] = {
                "engine": engine,
                "display_name": hints.get("display_name"),
                "lat": hints.get("lat"),
                "lon": hints.get("lon"),
                "postcode": hints.get("postcode"),
                "city": hints.get("city"),
                "provincia": hints.get("provincia"),
                "state": hints.get("state"),
            }
        else:
            gaps.append("Geocodificación sin resultados — usando datos de dirección tal cual")

        municipio = hints.get("city") or ""
        # Usar state_district (provincia real) en lugar de state (CCAA)
        provincia = _clean_provincia(hints.get("provincia") or hints.get("state"))
        road = hints.get("road") or ""

        # Geocoders a veces devuelven house_number como rango ("1-3") o lo pierden.
        # Si parece rango o está vacío, intentamos extraerlo del texto de la dirección.
        raw_num = hints.get("house_number") or ""
        if not raw_num or "-" in raw_num:
            fallback_num = _extract_house_number(address)
            if fallback_num:
                _log(f"[property] house_number geocoder='{raw_num}' → usando fallback='{fallback_num}'")
            house_number = fallback_num or raw_num
        else:
            house_number = raw_num

        _log(f"[property] geocode → municipio={municipio!r}, provincia={provincia!r}, road={road!r}")

        # --- 2. Catastro API ---
        catastro_data: dict[str, Any] | None = None

        if road and house_number and municipio:
            tipo_via, nombre_via = catastro_svc.parse_tipo_via(road)

            # Resolver nombre exacto de vía.
            # Catastro usa la provincia administrativa ("Barcelona"), no la comarca
            # ("Barcelonès"). Si el primer intento falla con la provincia geocodificada,
            # reintentamos con provincia = municipio — válido para capitales cuyo
            # nombre coincide con su provincia (Barcelona, Madrid, Sevilla…).
            _log(f"[property] catastro /vias → {nombre_via!r} prov={provincia!r} mun={municipio!r}")
            vias = await catastro_svc.get_vias(provincia, municipio, nombre_via[:20])
            prov_catastro = provincia  # provincia que Catastro aceptó
            if not vias and provincia.lower() != municipio.lower():
                _log(f"[property] catastro /vias retry con provincia='{municipio}'")
                vias = await catastro_svc.get_vias(municipio, municipio, nombre_via[:20])
                if vias:
                    prov_catastro = municipio

            if vias:
                via = vias[0]
                nombre_via_exacto: str = via.get("nombreVia", nombre_via)
                tipo_via_exacto: str = via.get("tipoVia", tipo_via)
            else:
                nombre_via_exacto = nombre_via
                tipo_via_exacto = tipo_via
                gaps.append(
                    f"Catastro /vias sin resultado para '{nombre_via}' en {municipio} "
                    "— usando tipo de vía inferido"
                )

            # Extraer planta y puerta del texto de la dirección para filtrar en Catastro.
            # Si los pasamos, la API devuelve solo la unidad concreta (ej: EN/01)
            # en vez de los 40 inmuebles del portal.
            planta, puerta = catastro_svc.parse_planta_puerta(address)
            _log(
                f"[property] catastro /inmueble-localizacion → {tipo_via_exacto} {nombre_via_exacto} "
                f"{house_number} planta={planta} puerta={puerta} (prov={prov_catastro})"
            )
            inmuebles = await catastro_svc.get_inmuebles_by_address(
                provincia=prov_catastro,
                municipio=municipio,
                tipo_via=tipo_via_exacto,
                nombre_via=nombre_via_exacto,
                numero=house_number,
                planta=planta,
                puerta=puerta,
            )

            # Si el filtro por planta/puerta no devuelve nada (Catastro es estricto
            # con los códigos), reintentamos sin filtro y elegimos el mejor.
            if not inmuebles and (planta or puerta):
                _log("[property] catastro sin resultado con planta/puerta → retry sin filtro")
                inmuebles = await catastro_svc.get_inmuebles_by_address(
                    provincia=prov_catastro,
                    municipio=municipio,
                    tipo_via=tipo_via_exacto,
                    nombre_via=nombre_via_exacto,
                    numero=house_number,
                )

            if inmuebles:
                best = catastro_svc.pick_best_inmueble(inmuebles)
                if best:
                    eco = best.get("datosEconomicos", {})
                    ref = best.get("referenciaCatastral", {})
                    catastro_data = {
                        "referencia_catastral": ref.get("referenciaCatastral"),
                        "superficie_m2": _safe_float(eco.get("superficieConstruida")),
                        "uso": eco.get("uso"),
                        "ano_construccion": eco.get("añoConstruccion"),
                        "coeficiente_participacion": eco.get("coeficienteParticipacion"),
                        "codigo_postal": best.get("direccion", {}).get("codigoPostal"),
                        "n_inmuebles_portal": len(inmuebles),
                    }
                    raw["catastro"] = catastro_data
                    _log(
                        f"[property] catastro → {catastro_data['superficie_m2']} m², "
                        f"uso={catastro_data['uso']}, RC={catastro_data['referencia_catastral']}"
                    )

                    # Fact: datos físicos del inmueble
                    rc = catastro_data["referencia_catastral"] or "desconocida"
                    uso = catastro_data["uso"] or "desconocido"
                    ano = catastro_data["ano_construccion"] or "desconocido"
                    m2_cat = catastro_data["superficie_m2"]
                    m2_str = f"{m2_cat:.0f} m²" if m2_cat else "desconocida"
                    facts.append(Fact(
                        claim=(
                            f"Inmueble en {address}: superficie {m2_str}, uso {uso}, "
                            f"año construcción {ano}. Referencia catastral: {rc}."
                        ),
                        source=CATASTRO_SOURCE,
                        confidence=0.95,
                    ))
            else:
                gaps.append(
                    f"Catastro API sin inmuebles para '{tipo_via_exacto} {nombre_via_exacto} "
                    f"{house_number}' en {municipio} — sin m² ni RC"
                )
        else:
            gaps.append(
                "Geocoding no resolvió calle + número + municipio — sin consulta a Catastro"
            )

        # m² efectivos: Catastro > case input
        sqm: float | None = (
            (catastro_data or {}).get("superficie_m2")
            or ctx.case.property_sqm
        )

        # --- 3. MITMA — precio venta €/m² ---
        # Fallback: municipio exacto → municipio parcial → provincia capital
        mitma_row: dict[str, Any] | None = None
        eur_m2_venta: float | None = None
        mitma_granularity: str = ""

        if municipio:
            mitma_row = mitma_svc.lookup(municipio, provincia or None)
            if mitma_row:
                mitma_granularity = "municipio"
            elif provincia:
                # Fallback: buscar la capital de provincia (mismo nombre que la provincia)
                mitma_row = mitma_svc.lookup(provincia)
                if mitma_row:
                    mitma_granularity = "provincia_capital"
                    gaps.append(
                        f"MITMA: '{municipio}' no en base (~306 municipios >25k hab) "
                        f"— usando capital de provincia '{mitma_row['municipio']}' como referencia"
                    )

            if mitma_row:
                eur_m2_venta = mitma_row.get("eur_m2_total")
                raw["mitma"] = {
                    "municipio": mitma_row["municipio"],
                    "provincia": mitma_row["provincia"],
                    "eur_m2_total": eur_m2_venta,
                    "eur_m2_nueva": mitma_row.get("eur_m2_vivienda_nueva"),
                    "eur_m2_usada": mitma_row.get("eur_m2_vivienda_usada"),
                    "n_tasaciones": mitma_row.get("n_tasaciones_total"),
                    "granularidad": mitma_granularity,
                    "periodo": "T4 2025",
                    "source": MITMA_SOURCE,
                }
                _log(f"[property] MITMA → {eur_m2_venta} €/m² en {mitma_row['municipio']} ({mitma_granularity})")
            else:
                gaps.append(
                    f"MITMA: ni municipio '{municipio}' ni provincia '{provincia}' encontrados"
                )

        # --- 4. SERPAVI — precio alquiler €/m²/mes ---
        # Fallback: municipio exacto → municipio parcial → provincia capital
        serpavi_row: dict[str, Any] | None = None
        eur_m2_mes: float | None = None
        serpavi_granularity: str = ""

        if municipio:
            serpavi_row = serpavi_svc.lookup(municipio, provincia or None)
            if serpavi_row:
                serpavi_granularity = "municipio"
            elif provincia:
                serpavi_row = serpavi_svc.lookup(provincia)
                if serpavi_row:
                    serpavi_granularity = "provincia_capital"
                    gaps.append(
                        f"SERPAVI: '{municipio}' no en base (2.555 municipios) "
                        f"— usando capital de provincia '{serpavi_row['municipio']}' como referencia"
                    )

            if serpavi_row:
                eur_m2_mes = serpavi_row.get("alquiler_eur_m2_mes_mediana")
                raw["serpavi"] = {
                    "municipio": serpavi_row["municipio"],
                    "provincia": serpavi_row["provincia"],
                    "alquiler_eur_m2_mes_mediana": eur_m2_mes,
                    "alquiler_eur_m2_mes_p25": serpavi_row.get("alquiler_eur_m2_mes_p25"),
                    "alquiler_eur_m2_mes_p75": serpavi_row.get("alquiler_eur_m2_mes_p75"),
                    "alquiler_eur_mes_mediana": serpavi_row.get("alquiler_eur_mes_mediana"),
                    "alquiler_eur_mes_p25": serpavi_row.get("alquiler_eur_mes_p25"),
                    "alquiler_eur_mes_p75": serpavi_row.get("alquiler_eur_mes_p75"),
                    "superficie_tipica_m2": serpavi_row.get("superficie_m2_mediana"),
                    "n_viviendas_muestra": serpavi_row.get("n_viviendas_colectiva"),
                    "granularidad": serpavi_granularity,
                    "periodo": "2024",
                    "source": SERPAVI_SOURCE,
                }
                _log(f"[property] SERPAVI → {eur_m2_mes} €/m²/mes en {serpavi_row['municipio']} ({serpavi_granularity})")
            else:
                gaps.append(
                    f"SERPAVI: ni municipio '{municipio}' ni provincia '{provincia}' encontrados"
                )

        # --- 5. Estimaciones ---
        estimates: dict[str, Any] = {}

        if eur_m2_venta is not None and sqm is not None and sqm > 0:
            low = sqm * eur_m2_venta * SALE_BAND_LOW
            high = sqm * eur_m2_venta * SALE_BAND_HIGH
            estimates["venta_total_eur_low"] = round(low)
            estimates["venta_total_eur_high"] = round(high)
            estimates["venta_base_eur"] = round(sqm * eur_m2_venta)
            estimates["venta_nota"] = (
                f"{sqm:.0f} m² × {eur_m2_venta:.0f} €/m² (MITMA {mitma_row['municipio']} T4 2025)"
                f" × banda ±{int((1 - SALE_BAND_LOW) * 100)}%"
            )

        if eur_m2_mes is not None and sqm is not None and sqm > 0:
            low_r = sqm * eur_m2_mes * RENT_BAND_LOW
            high_r = sqm * eur_m2_mes * RENT_BAND_HIGH
            estimates["alquiler_mensual_eur_low"] = round(low_r)
            estimates["alquiler_mensual_eur_high"] = round(high_r)
            estimates["alquiler_mensual_base_eur"] = round(sqm * eur_m2_mes)
            estimates["alquiler_nota"] = (
                f"{sqm:.0f} m² × {eur_m2_mes:.2f} €/m²/mes (SERPAVI {serpavi_row['municipio']} 2024)"
                f" × banda ±{int((1 - RENT_BAND_LOW) * 100)}%"
            )

        if estimates:
            raw["estimates"] = estimates

        # --- Signals & summary ---
        location_str = ", ".join(p for p in [municipio, "ES"] if p)
        summary_parts: list[str] = []

        # Emit a location signal from the geocoded address so downstream
        # modules and the LLM summary can read it from ctx.signals.
        if municipio:
            signals.append(Signal(
                kind="location",
                value=location_str,
                source=CATASTRO_SOURCE if catastro_data else "geocoding",
                confidence=0.75,
                notes="Location derived from debtor's known address",
            ))

        if catastro_data:
            m2_s = f"{catastro_data['superficie_m2']:.0f} m²" if catastro_data.get("superficie_m2") else "m² desconocidos"
            uso_s = catastro_data.get("uso") or "uso desconocido"
            ano_s = catastro_data.get("ano_construccion") or ""
            summary_parts.append(f"Catastro: {m2_s}, {uso_s}" + (f", {ano_s}" if ano_s else ""))

        if "venta_total_eur_low" in estimates:
            venta_str = (
                f"{_fmt_eur(estimates['venta_total_eur_low'])}–"
                f"{_fmt_eur(estimates['venta_total_eur_high'])}"
            )
            summary_parts.append(f"venta estimada {venta_str}")
            signals.append(Signal(
                kind="asset",
                value=f"Inmueble {venta_str}",
                source=MITMA_SOURCE,
                confidence=0.65,
                notes=f"{location_str}. {estimates.get('venta_nota', '')}".strip(),
            ))

        if "alquiler_mensual_eur_low" in estimates:
            alq_str = (
                f"{_fmt_eur(estimates['alquiler_mensual_eur_low'])}–"
                f"{_fmt_eur(estimates['alquiler_mensual_eur_high'])}/mes"
            )
            summary_parts.append(f"alquiler estimado {alq_str}")
            signals.append(Signal(
                kind="asset",
                value=f"Alquiler estimado {alq_str}",
                source=SERPAVI_SOURCE,
                confidence=0.70,
                notes=f"{location_str}. {estimates.get('alquiler_nota', '')}".strip(),
            ))

        if not summary_parts and not gaps:
            gaps.append("Sin datos suficientes para estimar valor del inmueble")

        summary = (
            f"Inmueble en {address}. "
            + " | ".join(summary_parts)
            if summary_parts
            else f"Sin estimación de valor para {address}. Ver gaps."
        )

        status = "ok" if (catastro_data or eur_m2_venta or eur_m2_mes) else "error"
        return ModuleResult(
            name=self.name,
            status=status,
            summary=summary,
            signals=signals,
            facts=facts,
            gaps=gaps,
            raw=raw,
        )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extract_house_number(address: str) -> str | None:
    """Extrae el primer número de portal de una dirección en texto libre.

    Fallback para cuando el geocoder da un house_number malo (ej: "1-3" en vez de "13").
    Busca el primer número que aparece después de la primera palabra (el tipo de vía).

    "Passeig Maragall 13, Entresuelo 1" → "13"
    "Calle Mayor 5, 3º B"               → "5"
    """
    import re
    # Primer número tras al menos una palabra
    m = re.search(r"\b([1-9]\d{0,3})\b", address)
    return m.group(1) if m else None
