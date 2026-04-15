# Project Context — Enrichment Pipeline

## INPUTS

PII (might be outdated!):
- name
- telephone
- address
- email
- NIF

Case fields:
- case number
- country
- debt_eur
- debt_origin
- debt_age_months
- call_attempts
- call_outcome
- legal_asset_finding

## Enrichment Sources

| Source | Notes |
|---|---|
| **Data Breaches** | betting, traveling, events, G Maps Reviews, second hand (wallapop...) |
| **Family?** | Investigate family connections |
| **RRSS** | Social media profiles |
| **Clay** | Clay enrichment API |
| **Updated data?** | Verify if existing data is current |

## Automate Law Info Requests

- get balance on accounts
- https://opencorporates.com/


## Processing

Input da


```
Merge Data ——> Find Out What's Relevant
```

Combine all enrichment sources, then filter for actionable signals relevant to debt collection.
