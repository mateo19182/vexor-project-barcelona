# github_check — GitHub registration check

`backend/app/pipeline/modules/github_check.py`

```
requires: ("email",)
```

Runs in wave 1 alongside the other platform-check modules.

## Overview

Asks the upstream platform-check VM (`PLATFORM_CHECK_HOST`) whether `ctx.email` is registered on GitHub. Same mechanism as `instagram_check` and `twitter_check` — see [platform_check.md](platform_check.md) for the VM protocol.

## Output

Returns a `contact` signal (platform = GitHub, value = email) on a hit, or a gap when the email is not found. Skips cleanly when `GITHUB_CHECK_API_KEY` is not configured.

## Config

`GITHUB_CHECK_PORT` + `GITHUB_CHECK_API_KEY` in `.env`.
