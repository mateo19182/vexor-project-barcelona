# gaia_enrichment — Google account public intelligence

`backend/app/pipeline/modules/gaia_enrichment.py`

```
requires: ("gaia_id",)
```

Runs in wave 2+ — after `google_id` promotes `gaia_id` to Context.

## Overview

Given a Gaia ID, fetches all public intelligence from the Google Maps contributor profile: display name, profile picture, contributor stats, review history, and uploaded photos. The stats and photo volume are strong lifestyle signals that contradict insolvency claims.

## What it finds

| Output | Signal kind | Trigger |
|---|---|---|
| Display name | Fact | Name resolved from Maps profile |
| Contributor stats | Fact | Reviews count, photos count, points, Local Guides level |
| Review activity | `lifestyle` | Each reviewed place (with rating + timestamp) |
| Uploaded photos | `lifestyle` | Each public photo (with place name when available) |

## Pages scraped

| URL | Purpose |
|---|---|
| `/maps/contrib/{gaia_id}/reviews` | Profile header (name, pic, stats) + full review history |
| `/maps/contrib/{gaia_id}/photos` | Grid of all publicly uploaded photos |

## Stats extracted

- **Reviews count** — total public reviews written
- **Photos count** — total photos uploaded to Google Maps
- **Points** — Local Guides points balance
- **Local Guides level** — badge level (1–10), parsed from profile text

## Config

`GOOGLE_SESSION_COOKIES` — same cookie dict used by `google_id`. Skips cleanly when absent.
