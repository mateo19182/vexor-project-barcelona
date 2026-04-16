# twitter — Twitter/X OSINT enrichment

`backend/app/pipeline/modules/twitter.py`

```
requires: ("twitter_handle",)
```

Runs in wave 2+ — after `osint_web` promotes `twitter_handle` to Context (confidence ≥ 0.6).

## Overview

Fetches a public profile and recent timeline via `twscrape` (Twitter's internal GraphQL). No official API required — uses a burner account for auth.

## What it finds

| Output | Signal kind | Source |
|---|---|---|
| Bio text | Fact | Profile |
| Profile location field | `location` (conf 0.70) | Profile |
| Active posting recently | `lifestyle` (conf 0.80) | Timeline |
| Employment mention in tweets | `employer` (conf 0.45) | Tweet keywords |
| Travel mention in tweets | `lifestyle` (conf 0.50) | Tweet keywords |
| Asset mention in tweets | `asset` (conf 0.40) | Tweet keywords |

Keyword scanning is intentionally conservative — one signal per category, manual review flagged in notes.

## Config

| Env var | Notes |
|---|---|
| `TWITTER_USERNAME` | Burner account username. Module skips if absent. |
| `TWITTER_PASSWORD` | Password (used when no cookies set). |
| `TWITTER_COOKIES` | JSON dict of session cookies — more stable than password auth. |
