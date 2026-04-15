# breach_scout — breach intelligence lookup

`backend/app/pipeline/modules/breach_scout.py`

## Overview

Queries a breach-intelligence API (host configured via `BREACH_INTEL_HOST`) for records associated with the debtor's name, and optionally their email and phone if already in context. Returns contact fields found in breach records — emails, phones, and usernames the debtor has registered under — as well as risk signals from breach exposure itself.

```
requires: ("name",)
```

Runs in **wave 1** alongside `osint_web` and `xon`. Because it needs only `ctx.name`, it can promote newly discovered emails and phones to `Context` early enough for later modules to use them.

Two request modes, selected automatically:

| Mode | Activated when | Endpoint | Returns |
|---|---|---|---|
| **Authenticated** | `BREACH_INTEL_API_KEY` is set | `POST /api/v1/query_detail_batch` | Unmasked email, phone, username, real_name |
| **Unauthenticated** | API key absent | `POST /api/v1/query` | Masked breach list only (no contact fields) |

Auth header: `X-Auth-Key: {BREACH_INTEL_API_KEY}`.

## What it finds

Keywords queried: `ctx.name` always; `ctx.email` and `ctx.phone` appended if non-empty (deduplicated, batch sent in one request).

Scopes requested: `email`, `phone`, `real_name`, `user_name`.

From the results the module extracts:

- **Emails** not already in `ctx.email` → `contact` signal, promoted to `ctx_patch` if `ctx.email` is currently empty
- **Phones** not already in `ctx.phone` → `contact` signal, promoted to `ctx_patch` if `ctx.phone` is currently empty
- **Usernames / aliases** → `contact` signals (leads for social profile discovery)
- **Breach hit count** → `risk_flag` signal and summary `Fact`

Unknown field names are handled by a defensive string scanner that detects email-shaped and phone-shaped strings anywhere in the response object.

## Output

| Field | Type | Description |
|---|---|---|
| `signals` | `list[Signal]` | `risk_flag` for breach presence; `contact` for each discovered email, phone, or username |
| `facts` | `list[Fact]` | Summary claim: how many breach records matched the debtor's identifiers |
| `gaps` | `list[str]` | Unauthenticated-mode notice; response-size truncation notice; "no records found" |
| `ctx_patch` | `ContextPatch` | `email` and/or `phone` promoted at confidence 0.55 when discovered and not already in context |
| `raw` | `dict` | `keywords`, `mode`, `status_code`, `response_bytes`, `response` (full parsed payload) |

`social_links` is always empty — discovered handles are emitted as `contact` signals, not verified profile links.

### Signal confidence

| Signal | Confidence |
|---|---|
| Breach presence (`risk_flag`) | 0.85 |
| Discovered email (`contact`) | 0.70 |
| Discovered phone (`contact`) | 0.70 |
| Discovered username (`contact`) | 0.65 |
| `ctx_patch` email or phone | 0.55 |

## Size and performance guards

Famous or high-exposure subjects can generate very large API responses (thousands of breach records). Two safeguards:

1. **Thread-offloaded JSON parsing** — `resp.json()` runs via `asyncio.to_thread` so the event loop (and wave-1 siblings) stay unblocked during parsing.
2. **Record cap** — only the first 100 records are processed even if the response contains more. A gap note is added when truncation occurs, and `raw.response_bytes` records the actual payload size.

## Skips / errors

| Situation | Status | Behaviour |
|---|---|---|
| `BREACH_INTEL_HOST` not set | `skipped` | Module exits immediately with a gap; pipeline continues |
| `BREACH_INTEL_API_KEY` not set | `ok` / `no_data` | Falls back to unauthenticated masked endpoint; gap notes limited data |
| HTTP error or network failure | `error` | Gap records the exception; `raw.status_code` preserved |
| 200 response with no records | `no_data` | Gap: "No breach records found" |
| Records returned but no usable fields extracted | `no_data` | Gap explains; `raw.response` available for inspection |

## Hard rules

1. Every signal and fact carries `source=BREACH_INTEL_HOST` — the provider name never appears in any output field.
2. `ctx_patch` only promotes a field if it is currently empty on Context (confidence 1.0 seed values from case input are never overwritten).
3. Username signals are capped at 10 per run to avoid flooding the output with noise from high-exposure subjects.

None — no LLM involved. 