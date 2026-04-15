# boe — BOE (Boletín Oficial del Estado) lookup

`backend/app/pipeline/modules/boe.py`

## Overview

Searches Spain's Official State Gazette ([boe.es](https://www.boe.es)) for mentions of the debtor's name using the Brave Search API with `site:boe.es` filtering. Surfaces legally relevant entries: concursos de acreedores (bankruptcy proceedings), edictos (court notices), embargos (levies), insolvency notices, and official role appointments.

```
requires: ("name",)
```

Runs in **wave 1** alongside `osint_web` and `breach_scout`. Requires only `ctx.name`.

Two complementary queries are sent:

| Query | Purpose |
|---|---|
| `site:boe.es "{name}"` | Broad name mention sweep |
| `site:boe.es "{name}" concurso OR embargo OR edicto OR insolvencia` | Targeted legal/debt signals |

Results are deduplicated by URL across both queries.

## What it finds

- **Bankruptcy proceedings** (`concurso de acreedores`) — debtor declared insolvent or subject to creditor proceedings
- **Court notices / edictos** — judicial notifications published in the BOE (often for debtors who couldn't be reached)
- **Embargos / levies** — asset seizure orders published officially
- **Insolvency / liquidation notices** — `insolvencia`, `liquidación`, `quiebra`
- **Official roles** — directorships, appointments (`cargo`, `nombramiento`, `administrador`) that may indicate business assets or liability

## Output

| Field | Type | Description |
|---|---|---|
| `signals` | `list[Signal]` | `risk_flag` for legal/debt hits; `role` for appointments |
| `facts` | `list[Fact]` | Other BOE mentions that don't match a specific risk or role keyword |
| `gaps` | `list[str]` | "No BOE entries found" when clean; key-not-configured notice |

`social_links` and `ctx_patch` are always empty — BOE entries don't yield identity fields.

### Signal confidence

| Signal | Confidence |
|---|---|
| Risk flag (concurso, embargo, edicto, etc.) | 0.85 |
| Role / appointment | 0.70 |
| Other BOE mention (`Fact`) | 0.60 |

All signals carry `source` = the canonical `boe.es` URL for the entry.

## Skips / errors

| Situation | Status | Behaviour |
|---|---|---|
| `BRAVE_API_KEY` not set | `skipped` | Module exits immediately; pipeline continues |
| Brave API returns non-200 | `no_data` | Empty results; no exception raised |
| No results after both queries | `no_data` | Gap: "No BOE entries found for '{name}'" |
| Network / timeout error | `no_data` | Exception swallowed per-query; empty results returned |

## Hard rules

1. Every signal and fact carries a `source` URL pointing to the specific `boe.es` entry — no unsourced claims.
2. Results are deduplicated by URL before classification to avoid duplicate signals from overlapping queries.
3. No LLM involved — classification is keyword-based only.
