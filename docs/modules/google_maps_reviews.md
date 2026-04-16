# google_maps_reviews — Google Maps review history

`backend/app/pipeline/modules/google_maps_reviews.py`

```
requires: ("gaia_id",)
```

Runs in wave 2+ — after `google_id` promotes `gaia_id` to Context.

## Overview

Fetches the debtor's public Google Maps review history using their Gaia ID. Each review includes the place visited, rating, review text, and timestamp. This surfaces lifestyle signals (frequent restaurant visits, hotel stays, travel) that directly contradict "I have no money" claims.

## What it finds

| Output | Signal kind | Trigger |
|---|---|---|
| Recent review activity | `lifestyle` | Any reviews found |
| Specific place mentions | `lifestyle` | Individual review text |
| Fact | — | Per-review summary: place, rating, text excerpt |

## Config

`GOOGLE_SESSION_COOKIES` — same cookie dict used by `google_id`. Skips cleanly when absent.
