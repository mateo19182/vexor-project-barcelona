# platform_check — registration lookup (Instagram / Twitter / iCloud)

Three modules share a single client that asks a per-platform VM whether an email or phone number is registered on that platform.

## Modules

| Module | File | `requires` | Identifier |
|---|---|---|---|
| `instagram_check` | `modules/instagram_check.py` | `("email",)` | `ctx.email` |
| `twitter_check` | `modules/twitter_check.py` | `("email",)` | `ctx.email` |
| `icloud_check` | `modules/icloud_check.py` | `()` | `ctx.email` and/or `ctx.phone` (checks both; self-skips if neither) |

Shared client: `app/enrichment/platform_check.py` → `check_platform()`.

## Protocol

```
POST /cs  {}              → bare UUID  (session create)
POST /h   {s, w, p}       → {"s": "<STATUS>"}
  w = identifier (email or phone)
  p = proxy URL
```

HTTPS on a self-signed cert (`verify=False`). Both calls require `Authorization: <api_key>`.

## Status mapping

| Upstream value | `registered` |
|---|---|
| `REGISTERED`, `SUCCESS`, `VALID`, `FOUND` | `True` |
| `NOT_REGISTERED`, `FAIL`, `NOT_FOUND`, `UNREGISTERED` | `False` |
| `INVALID`, `BAN`, anything else | `None` (ambiguous → `no_data`) |

## Output

| Field | Description |
|---|---|
| `signals` | One `contact` signal (confidence 0.8) when `registered=True` |
| `gaps` | Explains ambiguous/error outcomes |
| `raw` | `platform`, `identifier`, `status_raw`, `http_status`, `session_id`, `error` |

`icloud_check` runs both identifiers concurrently; final status is the best across both checks.

## Config (`.env`)

```
PLATFORM_CHECK_HOST=163.5.221.166
PLATFORM_CHECK_PROXY=http://<user>:<pass>@<host>:<port>

INSTAGRAM_CHECK_PORT=19182
INSTAGRAM_CHECK_API_KEY=<key>

TWITTER_CHECK_PORT=19183
TWITTER_CHECK_API_KEY=<key>

ICLOUD_CHECK_PORT=19184
ICLOUD_CHECK_API_KEY=<key>
```

All three modules self-skip when their port or api_key is missing.
