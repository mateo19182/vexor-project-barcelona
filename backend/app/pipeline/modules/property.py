"""Property enrichment module.

Flujo para direcciones en Espana (country=ES):
  1. Geocoding (Nominatim/Photon) -> provincia, municipio, calle, numero
  2. Catastro API -> m2, uso, ano de construccion, referencia catastral
  3. MITMA T4 2025 -> EUR/m2 valor tasado de venta por municipio
  4. SERPAVI 2024  -> EUR/m2/mes alquiler real (datos fiscales AEAT) por municipio
  5. Estimaciones = m2 x precio_unitario, con banda de incertidumbre

Emite:
  - signals: `asset` con la estimacion de valor/alquiler
  - facts:   datos fisicos del inmueble (m2, uso, ano, RC)
  - raw:     todo el detalle estructurado para sintesis o respuesta API
  - gaps:    que no se pudo obtener y por que
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
_PROVINCIA_PREFIJOS = (
    "comunidad de ",
    "comunidad foral de ",
    "region de ",
    "principado de ",
    "islas ",
    "illes ",
    "pais ",
)


def _clean_provincia(raw: str | None) -> str:
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
        return f"{v / 1_000_000:.2f}M \u20ac"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k \u20ac"
    return f"{v:.0f} \u20ac"


class PropertyModule:
    name = "property"
    requires: tuple[tuple[str, str | None], ...] = (("address", None),)

    async def run(self, ctx: Context) -> ModuleResult:
        # Solo Espana por ahora
        if (ctx.case.country or "").upper() != "ES":
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["property enrichment solo disponible para ES (country!=ES)"],
            )

        address_sig = ctx.best("address")
        address = address_sig.value if address_sig else ""
        if not address.strip():
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["sin direccion no se puede enriquecer el inmueble"],
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
            gaps.append(f"Geocodificacion fallo: {e}")
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
            gaps.append("Geocodificacion sin resultados — usando datos de direccion tal cual")

        municipio = hints.get("city") or ""
        provincia = _clean_provincia(hints.get("provincia") or hints.get("state"))
        road = hints.get("road") or ""

        raw_num = hints.get("house_number") or ""
        if not raw_num or "-" in raw_num:
            fallback_num = _extract_house_number(address)
            if fallback_num:
                _log(f"[property] house_number geocoder='{raw_num}' -> usando fallback='{fallback_num}'")
            house_number = fallback_num or raw_num
        else:
            house_number = raw_num

        _log(f"[property] geocode -> municipio={municipio!r}, provincia={provincia!r}, road={road!r}")

        # --- 2. Catastro API ---
        catastro_data: dict[str, Any] | None = None

        if road and house_number and municipio:
            tipo_via, nombre_via = catastro_svc.parse_tipo_via(road)

            _log(f"[property] catastro /vias -> {nombre_via!r} prov={provincia!r} mun={municipio!r}")
            vias = await catastro_svc.get_vias(provincia, municipio, nombre_via[:20])
            prov_catastro = provincia
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
                    "— usando tipo de via inferido"
                )

            planta, puerta = catastro_svc.parse_planta_puerta(address)
            _log(
                f"[property] catastro /inmueble-localizacion -> {tipo_via_exacto} {nombre_via_exacto} "
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

            if not inmuebles and (planta or puerta):
                _log("[property] catastro sin resultado con planta/puerta -> retry sin filtro")
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
                        "ano_construccion": eco.get("anoConstruccion"),
                        "coeficiente_participacion": eco.get("coeficienteParticipacion"),
                        "codigo_postal": best.get("direccion", {}).get("codigoPostal"),
                        "n_inmuebles_portal": len(inmuebles),
                    }
                    raw["catastro"] = catastro_data
                    _log(
                        f"[property] catastro -> {catastro_data['superficie_m2']} m2, "
                        f"uso={catastro_data['uso']}, RC={catastro_data['referencia_catastral']}"
                    )

                    rc = catastro_data["referencia_catastral"] or "desconocida"
                    uso = catastro_data["uso"] or "desconocido"
                    ano = catastro_data["ano_construccion"] or "desconocido"
                    m2_cat = catastro_data["superficie_m2"]
                    m2_str = f"{m2_cat:.0f} m2" if m2_cat else "desconocida"
                    facts.append(Fact(
                        claim=(
                            f"Inmueble en {address}: superficie {m2_str}, uso {uso}, "
                            f"ano construccion {ano}. Referencia catastral: {rc}."
                        ),
                        source=CATASTRO_SOURCE,
                        confidence=0.95,
                    ))
            else:
                gaps.append(
                    f"Catastro API sin inmuebles para '{tipo_via_exacto} {nombre_via_exacto} "
                    f"{house_number}' en {municipio} — sin m2 ni RC"
                )
        else:
            gaps.append(
                "Geocoding no resolvio calle + numero + municipio — sin consulta a Catastro"
            )

        # m2 efectivos: Catastro > case input
        sqm: float | None = (
            (catastro_data or {}).get("superficie_m2")
            or ctx.case.property_sqm
        )

        # --- 3. MITMA ---
        mitma_row: dict[str, Any] | None = None
        eur_m2_venta: float | None = None
        mitma_granularity: str = ""

        if municipio:
            mitma_row = mitma_svc.lookup(municipio, provincia or None)
            if mitma_row:
                mitma_granularity = "municipio"
            elif provincia:
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
                _log(f"[property] MITMA -> {eur_m2_venta} EUR/m2 en {mitma_row['municipio']} ({mitma_granularity})")
            else:
                gaps.append(
                    f"MITMA: ni municipio '{municipio}' ni provincia '{provincia}' encontrados"
                )

        # --- 4. SERPAVI ---
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
                _log(f"[property] SERPAVI -> {eur_m2_mes} EUR/m2/mes en {serpavi_row['municipio']} ({serpavi_granularity})")
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
                f"{sqm:.0f} m2 x {eur_m2_venta:.0f} EUR/m2 (MITMA {mitma_row['municipio']} T4 2025)"
                f" x banda +/-{int((1 - SALE_BAND_LOW) * 100)}%"
            )

        if eur_m2_mes is not None and sqm is not None and sqm > 0:
            low_r = sqm * eur_m2_mes * RENT_BAND_LOW
            high_r = sqm * eur_m2_mes * RENT_BAND_HIGH
            estimates["alquiler_mensual_eur_low"] = round(low_r)
            estimates["alquiler_mensual_eur_high"] = round(high_r)
            estimates["alquiler_mensual_base_eur"] = round(sqm * eur_m2_mes)
            estimates["alquiler_nota"] = (
                f"{sqm:.0f} m2 x {eur_m2_mes:.2f} EUR/m2/mes (SERPAVI {serpavi_row['municipio']} 2024)"
                f" x banda +/-{int((1 - RENT_BAND_LOW) * 100)}%"
            )

        if estimates:
            raw["estimates"] = estimates

        # --- Signals & summary ---
        location_str = ", ".join(p for p in [municipio, "ES"] if p)
        summary_parts: list[str] = []

        if municipio:
            signals.append(Signal(
                kind="location",
                value=location_str,
                source=CATASTRO_SOURCE if catastro_data else "geocoding",
                confidence=0.75,
                notes="Location derived from debtor's known address",
            ))

        if catastro_data:
            m2_s = f"{catastro_data['superficie_m2']:.0f} m2" if catastro_data.get("superficie_m2") else "m2 desconocidos"
            uso_s = catastro_data.get("uso") or "uso desconocido"
            ano_s = catastro_data.get("ano_construccion") or ""
            summary_parts.append(f"Catastro: {m2_s}, {uso_s}" + (f", {ano_s}" if ano_s else ""))

        if "venta_total_eur_low" in estimates:
            venta_str = (
                f"{_fmt_eur(estimates['venta_total_eur_low'])}\u2013"
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
                f"{_fmt_eur(estimates['alquiler_mensual_eur_low'])}\u2013"
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
            else f"Sin estimacion de valor para {address}. Ver gaps."
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
    import re
    m = re.search(r"\b([1-9]\d{0,3})\b", address)
    return m.group(1) if m else None
