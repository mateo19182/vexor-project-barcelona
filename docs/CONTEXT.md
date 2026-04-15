# Project Context — Enrichment Pipeline

## INPUTS

PII (might be outdated!):
- name
- telephone
- address

Case fields:
- country
- debt_eur
- debt_origin
- debt_age_months
- call_attempts
- call_outcome
- legal_asset_finding
- NIF ?

## Enrichment Sources

| Source | Notes |
|---|---|
| **Data Breaches** | betting, traveling, events, G Maps Reviews, second hand (wallapop...) |
| **Family?** | Investigate family connections |
| **RRSS** | Social media profiles |
| **Clay** | Clay enrichment API |
| **Updated data?** | Verify if existing data is current |

## Automate Law Info Requests

Tools:
- https://github.com/Hamed233/Digital-Footprint-OSINT-Tool
- https://opencorporates.com/

## Processing

```
Merge Data ——> Find Out What's Relevant
```

Combine all enrichment sources, then filter for actionable signals relevant to debt collection.
