# google_id — Google Gaia ID resolver

`backend/app/pipeline/modules/google_id.py`

```
requires: ("email",)
ctx_patch: gaia_id
```

Runs in wave 1.

## Overview

Resolves a Gmail address to its internal Google Gaia ID using the GHunt technique: authenticates against Google's `people-pa` endpoint via SAPISIDHASH + the Photos API key.

Writes `gaia_id` to Context via `ctx_patch`, which unblocks `google_maps_reviews` in the next wave.

## Config

`GOOGLE_SESSION_COOKIES` — JSON dict of Google session cookies copied from Chrome DevTools → Application → Cookies → `google.com`. Required keys: `SID`, `SSID`, `APISID`, `SAPISID`, `__Secure-1PAPISID`, `NID`.

Skips cleanly when cookies are absent or the email is not a Gmail address.
