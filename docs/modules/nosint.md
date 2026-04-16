# nosint — NoSINT / CSINT multi-platform lookup

`backend/app/pipeline/modules/nosint.py`

```
requires: ("email",)
```

Runs in wave 1.

## Overview

Streams results from 30+ OSINT modules (via the NoSINT/CSINT API) for a given email address. Surfaces which platforms the email is registered on and any breach/leak/paste hits.

## What it finds

| Output | Signal kind | Trigger |
|---|---|---|
| Per-platform hit | `contact` | Email found on that platform |
| Breach / leak / paste | `risk_flag` | Module name contains breach-related keyword |
| Fact | — | Summary: total hits + list of matched platforms |

## Config

`NOSINT_API_KEY` (or equivalent) in `.env`. Skips cleanly when absent.
