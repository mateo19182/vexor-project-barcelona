# linkedin — LinkedIn OSINT enrichment

`backend/app/pipeline/modules/linkedin.py`

```
requires: ("linkedin_url",)
```

Runs in wave 2+ — after `osint_web` promotes `linkedin_url` to Context.

## Overview

Calls LinkdAPI (`linkdapi.com`) with two endpoints:

| Endpoint | Params | Returns |
|---|---|---|
| `GET /api/v1/profile/overview` | `username=<slug>` | Name, headline, current positions, follower count, location, URN |
| `GET /api/v1/profile/details` | `urn=<urn>` | About text, full position history (title, company, duration) |

Auth: `X-linkdapi-apikey` header. Skips cleanly when `LINKDAPI_API_KEY` is absent.

## What it finds

| Output | Field | Source |
|---|---|---|
| `role` signal | Headline verbatim | Overview |
| `employer` signal (one per entry) | `CurrentPositions[].name` | Overview |
| `location` signal | `location.fullLocation` | Overview |
| `affiliation` signal | `industryName` | Overview |
| Fact | Headline text | Overview |
| Fact | About / summary blurb (≤500 chars) | Details |
| Fact (top 3) | Position: title — company — duration | Details |

## Key signal: employer

`CurrentPositions` in the overview is LinkedIn's "currently employed at" list. Surfaced as an `employer` signal with confidence 0.85. Directly contradicts the common "I have no income" debtor claim.

## Gaps

- Skipped with an explicit gap when `LINKDAPI_API_KEY` is not configured.
- If overview returns no URN, the details call is skipped and logged as a gap.
- API errors are returned as gaps (not exceptions), keeping the pipeline non-blocking.

## Config

`LINKDAPI_API_KEY` — get one at `linkdapi.com/signup` (100 free credits, no card required).
