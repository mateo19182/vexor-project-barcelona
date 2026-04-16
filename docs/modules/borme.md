# borme — BORME (Boletín Oficial del Registro Mercantil) lookup

`backend/app/pipeline/modules/borme.py`

## Overview

Searches Spain's Commercial Registry Gazette ([boe.es/borme](https://www.boe.es/borme/)) for mentions of the debtor's name using the Brave Search API with `site:boe.es inurl:borme` filtering. Surfaces commercially relevant entries: company formations, director appointments/removals, capital changes, dissolutions, mergers, and commercial insolvency proceedings.

```
requires: ("name",)
```

Runs in **wave 1** alongside `osint_web`, `boe`, and `breach_scout`. Requires only `ctx.name`.

Two complementary queries are sent:

| Query | Purpose |
|---|---|
| `site:boe.es inurl:borme "{name}"` | Broad name mention sweep across BORME |
| `site:boe.es inurl:borme "{name}" nombramiento OR cese OR concurso OR administrador` | Targeted role / insolvency signals |

Results are deduplicated by URL across both queries.

## What it finds

- **Director / admin roles** — `nombramiento`, `administrador`, `consejero`, `apoderado`, `secretario` — debtor holds (or held) a corporate role
- **Role terminations** — `cese`, `dimisión`, `revocación` — potentially distressed or disengaging from a company
- **Company formation** — `constitución de sociedad` — debtor as founder / partner (potential business assets)
- **Capital changes** — `ampliación de capital`, `reducción de capital` — may indicate financial stress or growth
- **Dissolution / liquidation** — `disolución`, `liquidación`, `extinción` — company being wound down
- **Commercial insolvency** — `concurso de acreedores`, `quiebra` — bankruptcy of a company linked to the debtor
- **Corporate restructuring** — `fusión`, `escisión`, `transformación` — mergers / spinoffs / changes of form

## Output

| Field | Type | Description |
|---|---|---|
| `signals` | `list[Signal]` | `risk_flag` for insolvency / dissolution / cese; `role` for appointments |
| `facts` | `list[Fact]` | Other BORME mentions that don't match a specific risk or role keyword |
| `gaps` | `list[str]` | "No BORME entries found" when clean; key-not-configured notice |

`social_links` and `ctx_patch` are always empty — BORME entries don't yield identity fields (they may reference companies, but linking debtor ↔ company is left to synthesis / LLM summary).

### Signal confidence

| Signal | Confidence |
|---|---|
| Risk flag (concurso, disolución, liquidación, cese, quiebra) | 0.85 |
| Role / appointment (nombramiento, administrador, consejero) | 0.75 |
| Other BORME mention (`Fact`) | 0.60 |

All signals carry `source` = the canonical `boe.es/borme/...` URL for the entry.

## Skips / errors

| Situation | Status | Behaviour |
|---|---|---|
| `BRAVE_API_KEY` not set | `skipped` | Module exits immediately; pipeline continues |
| Brave API returns non-200 | `no_data` | Empty results; no exception raised |
| No results after both queries | `no_data` | Gap: "No BORME entries found for '{name}'" |
| Network / timeout error | `no_data` | Exception swallowed per-query; empty results returned |

## Hard rules

1. Every signal and fact carries a `source` URL pointing to the specific BORME entry on `boe.es` — no unsourced claims.
2. Results are deduplicated by URL before classification to avoid duplicate signals from overlapping queries.
3. No LLM involved — classification is keyword-based only.
4. BORME ≠ BOE. The `boe` module covers judicial / state notices (edictos, embargos); this module covers commercial-registry acts. Both can run simultaneously; overlap is avoided via the `inurl:borme` filter.
