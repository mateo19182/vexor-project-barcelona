# property — Spanish real-estate valuation

`backend/app/pipeline/modules/property.py`

## Overview

Given a debtor's Spanish address, estimates the physical attributes and market value (sale + rent) of the underlying property by chaining four public data sources. ES-only — skips cleanly for any other country.

```
requires: ("address",)
```

Runs after any wave that may promote `address` into the context (the case seed normally carries it directly, so in practice wave 1).

## Pipeline

| Step | Source | What it yields |
|---|---|---|
| 1. Geocoding | Nominatim / Photon (OpenStreetMap) | provincia, municipio, calle, número, postcode, lat/lon |
| 2. Catastro API | `catastro-api.es` | superficie construida (m²), uso, año de construcción, referencia catastral |
| 3. MITMA T4 2025 | [apps.fomento.gob.es](https://apps.fomento.gob.es/boletinonline2/sedal/35103500.XLS) | €/m² valor tasado de venta por municipio |
| 4. SERPAVI 2024 | [serpavi.mivau.gob.es](https://serpavi.mivau.gob.es/) | €/m²/mes alquiler real (datos fiscales AEAT) por municipio |
| 5. Estimates | — | `m² × €/m²` with uncertainty bands |

### Uncertainty bands

| Estimate | Low | High |
|---|---|---|
| Sale value | ×0.80 | ×1.20 |
| Monthly rent | ×0.85 | ×1.15 |

### Fallbacks

- **Provincia cleanup**: Nominatim sometimes returns CCAA names (e.g. "Comunidad de Madrid" → "Madrid", "Región de Murcia" → "Murcia") — stripped before Catastro lookup.
- **Catastro provincia retry**: if `/vias` misses with the geocoded provincia and it differs from the municipio, retries with `provincia = municipio` (works for capitals: Barcelona, Madrid, Sevilla…).
- **House-number fallback**: if the geocoder returns a range (`"1-3"`) or empty, the module extracts the first plausible number from the raw address string.
- **m² fallback**: Catastro `superficieConstruida` > `ctx.case.property_sqm` if Catastro misses.
- **Municipio → provincia capital**: if MITMA or SERPAVI has no row for the municipio (MITMA only covers ~306 municipalities >25k hab; SERPAVI ~2,555), falls back to the provincial capital and records the granularity downgrade as a gap.

## Output

| Field | Type | Description |
|---|---|---|
| `signals` | `list[Signal]` | One `asset` per estimate (sale, rent) with range string and location |
| `facts` | `list[Fact]` | Catastro physical attributes (m², uso, año, referencia catastral) |
| `gaps` | `list[str]` | Explicit list of each step that failed or had to degrade (geocode miss, Catastro miss, MITMA/SERPAVI municipio-not-found, etc.) |
| `raw` | `dict` | Full structured detail: `geocode`, `catastro`, `mitma`, `serpavi`, `estimates` — for synthesis or API callers |

### Signal confidence

| Signal | Confidence |
|---|---|
| `asset` — sale estimate (MITMA) | 0.65 |
| `asset` — rent estimate (SERPAVI) | 0.70 |
| `Fact` — Catastro physical data | 0.95 |

## Skips / errors

| Situation | Status | Behaviour |
|---|---|---|
| `ctx.case.country` ≠ `"ES"` | `skipped` | MITMA / SERPAVI are ES-only; no valid base rate |
| No address on ctx | `skipped` | Nothing to geocode |
| Catastro misses but MITMA/SERPAVI hit | `ok` | Estimates still emitted using `case.property_sqm` if present |
| All four sources miss | `error` | Gaps list each reason |

## Env

```
CATASTRO_API_KEY=
```

See also [`CATASTRO_API.md`](../CATASTRO_API.md) for raw endpoint docs.

## Hard rules

1. ES-only. Any other country short-circuits before any network call.
2. Every estimate is traceable: signals cite MITMA or SERPAVI URLs, and the `notes` field spells out the arithmetic (`{m²} × {€/m²} (source, period) × band ±{%}`).
3. Fallbacks are disclosed — when MITMA/SERPAVI degrade from municipio to provincia capital, a gap entry names the substitution.
