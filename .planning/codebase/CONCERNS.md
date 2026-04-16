# Technical Debt & Concerns

## CRITICAL SECURITY ISSUES

### Exposed API Keys in `.env` File
**Severity:** CRITICAL  
**Location:** `/Users/pedro/Desktop/Code/Nordés/.env`

The `.env` file in the repository root contains plaintext API keys and secrets:
- `ANTHROPIC_API_KEY` (Claude API key)
- `CLAY_API_KEY` (Clay enrichment service)
- `CATASTRO_API_KEY` (Spanish property registry)
- `GOOGLE_SESSION_COOKIES` (Google session tokens — multiple cookies with sensitive auth data)
- `NOSINT_API_KEY` (OSINT platform API key)
- `JOOBLE_API_KEY` (Job search API)

**Issue:** This file should NEVER be in version control. Even if rotated now, commit history retains the keys.

**Action Required:**
1. Immediately rotate ALL API keys listed above
2. Remove `.env` from git history (use `git filter-branch` or similar)
3. Add `.env` to `.gitignore` if not already present
4. Use `.env.example` as the template (already exists with empty values)
5. Consider moving secrets to environment variables or a secure vault for non-development environments

---

### Hardcoded Platform Check IP
**Severity:** MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/config.py:40`

```python
platform_check_host: str = "163.5.221.166"
```

Internal IP hardcoded in source. Should be moved to `.env` with empty default.

---

### Google Session Cookies in Configuration
**Severity:** MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/config.py:87`  
**File:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/gaia_enrichment.py:24-36`

The `GOOGLE_SESSION_COOKIES` are passed as a large JSON string in `.env` and loaded at runtime. While necessary for Google Maps/GAIA enrichment, this:
- Requires manual cookie extraction from Chrome DevTools
- Cookies expire and need periodic refresh (not automated)
- No validation that the JSON structure is correct until runtime

**Improvement:** Add schema validation in `_load_cookies()` to validate required cookie names early.

---

## Architecture & Design Issues

### Broad Exception Catching Throughout Pipeline
**Severity:** MEDIUM  
**Locations:** Multiple module files including:
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/property.py` (lines marked BLE001)
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/gaia_enrichment.py:34` (catch-all)
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/breach_scout.py` (multiple)
- `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/jooble.py:72` (bare except)

**Pattern:**
```python
except Exception as e:  # noqa: BLE001
except Exception:
```

While intentional (per comments), this masks real bugs. Examples:
- Out-of-memory errors treated as data failures
- Import errors treated as graceful skip
- Timeout errors same as API errors

**Improvement:** Distinguish between recoverable errors (API, network) and fatal ones (imports, OOM). At minimum, add structured logging with exception type/traceback.

---

### No Input Validation on Case Parameters
**Severity:** MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/models.py` (Case class)

The `Case` model accepts:
- `country` as optional string — no ISO-2 validation
- `debt_eur` as optional float — accepts negative or zero
- `call_attempts` as optional int — accepts negative
- `context` as free-form text — no length limits (potential DoS with huge text)

**Impact:** Modules downstream assume valid data. Example: `property.py` assumes `country == "ES"` without sanitization.

**Improvement:** Add Pydantic validators:
```python
@field_validator("country")
def validate_country(cls, v):
    if v and len(v) != 2:
        raise ValueError("country must be ISO-2")
    return v

@field_validator("debt_eur")
def validate_debt(cls, v):
    if v is not None and v < 0:
        raise ValueError("debt_eur must be non-negative")
    return v
```

---

### Cache Key Collision Risk
**Severity:** LOW-MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/cache.py:26-28`

```python
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")
s = _SAFE_SLUG.sub("_", value).strip("._-") or "x"
return s[:128]
```

The cache slug is naively constructed by replacing unsafe characters with `_`. Two different case IDs could collide:
- `"case-2024-01-Barcelona"` → `case_2024_01_Barcelona`
- `"case_2024_01_Barcelona"` → `case_2024_01_Barcelona`

Both hash to the same cache directory, causing stale data leakage.

**Improvement:** Use a proper slug function (e.g., `python-slugify`) or hash the case_id: `hashlib.sha256(case_id.encode()).hexdigest()[:16]`.

---

### Silent Cache Corruption Allowed
**Severity:** LOW-MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/cache.py:42-45`

```python
try:
    return ModuleResult.model_validate_json(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    return None
```

If a cache file is corrupted (partial write, bad JSON, schema mismatch), it silently returns `None` and the module re-runs. This is fine for idempotence, but:
- **No logging** — operators don't know a cache file is bad
- **Silently discards data** — if validation fails, the file is never re-written
- **Could mask real issues** — e.g., upgrades that break the cache schema

**Improvement:** Log warnings when cache validation fails; optionally move corrupt files to a `.bad/` subdirectory for debugging.

---

### Module Dependency System Doesn't Auto-Unlock
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/runner.py` (entire design)

Per the docstring, if a module's dependencies aren't met, it's emitted with `status="skipped"` rather than being auto-included. This is intentional (per the comments), but creates a foot-gun:

- User requests `only={"linkedin"}` without realizing LinkedIn requires `contact:linkedin` from another module
- Result: LinkedIn returns skipped with no error; user thinks it ran but found nothing

**Current behavior is correct per design**, but the error message could be clearer. The `only` parameter doesn't auto-include transitive dependencies.

---

## Performance Issues

### Blocking HTTP Calls in Thread Executor
**Severity:** LOW-MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/jooble.py:62-73`

```python
def _fetch_sync(api_key: str, body_str: str, host: str) -> dict[str, Any]:
    """Blocking HTTP call to Jooble. Runs in a thread executor."""
    conn = http.client.HTTPConnection(...)
```

Uses synchronous `http.client` instead of `httpx.AsyncClient`. The `run_in_executor` workaround works, but:
- Blocks a thread pool thread for the full request (15s timeout)
- Less efficient than native async
- Not consistent with other modules using `httpx.AsyncClient`

**Improvement:** Migrate to `httpx.AsyncClient` for consistency and better concurrency.

---

### Subprocess Timeout for Instagram Osintgram
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/instagram.py:27`

```python
COMMAND_TIMEOUT_S = 120.0
```

Hard-coded 2-minute timeout for Osintgram subprocess. If the Osintgram tool is stuck or the network is slow, the entire pipeline stalls. No configurable override in `.env`.

**Improvement:** Make timeout configurable via settings.

---

### LLM Summary Generation on Every Full Run
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/main.py:84`

```python
llm_summary = None if only is not None else await generate_llm_summary(ctx, dossier)
```

The LLM summary is only skipped when running a subset of modules (`only` is set). On full runs, even if only one module changed, the entire dossier is re-summarized. This is expensive and not cached.

**Note:** This is a trade-off between accuracy and cost. Could implement a hash of dossier content to skip re-summarization if nothing changed.

---

## Missing Error Handling & Edge Cases

### Nominatim User-Agent
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/config.py:56-57`

```python
nominatim_user_agent: str = "VexorBCN-Enrichment/0.1 (hackathon; mateoamadoares@gmail.com)"
```

Hard-coded email address in production setting. Nominatim asks for contact info, but this should be templated or moved to `.env`.

---

### No Timeout on Anthropic API Calls
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/osint_web.py`

The OSINT web module uses Anthropic's server-side tool loop with resumption, but there's no overall timeout for the entire flow. If Claude gets stuck or the API is slow, the request could hang indefinitely.

**Improvement:** Add an overall timeout or max-resume-count (already has `MAX_RESUMES = 1`, but no wall-clock timeout).

---

### Instagram Module Doesn't Validate Osintgram Install
**Severity:** MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/instagram.py` (entire design)

The module assumes Osintgram is installed at the path in `config.osintgram_root`. If the path is wrong or the binary is missing, the subprocess call fails with a cryptic error.

**Improvement:** On startup, validate that `osintgram_python` is executable and print a clear error if not found.

---

### No Validation of Vision Model API Response
**Severity:** LOW-MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/vision.py`

The vision model (OpenRouter) is called to extract facts from images, but:
- No validation that the response is valid JSON
- No schema validation on the returned fields
- If the model returns malformed data, the entire module fails

---

## Documentation & Maintainability Issues

### Magic Numbers Throughout Codebase
**Examples:**
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/breach_scout.py` — confidence thresholds
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/property.py:34-37` — uncertainty bands (0.80–1.20 for sales, 0.85–1.15 for rent)
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/image_search.py` — various API limits
- `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/jooble.py:35-36` — demand thresholds (50 high, 10 moderate)

These should be moved to `config.py` with explanations, or at least grouped into a `constants.py` per module.

---

### Print Statements Instead of Logging
**Severity:** LOW  
**Locations:** ~43 files use `print(..., file=sys.stderr)`

Instead of:
```python
def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
```

Should use Python's `logging` module for:
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Structured logging (JSON output for aggregation)
- Filtering and redirection at runtime

---

### Incomplete Comments on Complex Logic
**Example:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/instagram.py:45-59`

The `_media_pk_to_shortcode()` function converts Instagram media PKs to shortcodes using base64 alphabet, but:
- No explanation of WHY this conversion is needed
- No source/reference for the algorithm
- Assumes the reader knows Instagram's internal media ID format

---

## Missing Test Coverage

**Severity:** MEDIUM

There's no evidence of unit or integration tests in the codebase. Critical areas without tests:
- Cache key collision scenarios
- Module dependency resolution logic
- Signal deduplication in synthesis
- Input validation on Case objects
- Error handling in modules (do they emit status="error" correctly?)

---

## Unfinished/Disabled Code

### Disabled Nosint Module
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/nosint.py`

The file exists and is registered in `REGISTRY`, but:
- Likely disabled or incomplete (check git blame for context)
- Still consumes API quota if accidentally triggered

---

### Unused `_host_for_country()` Function
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/jooble.py:33-34`

```python
def _host_for_country(country_code: str | None) -> str:  # noqa: ARG001
    return _JOOBLE_HOST
```

The `country_code` parameter is marked as intentionally unused (`# noqa: ARG001`), but the function still exists. Either:
- It's a stub for future multi-country support
- It's dead code from a refactor

**Improvement:** Remove if dead; make it a comment if planned.

---

## Dependency Management Issues

### Incomplete `pyproject.toml`
**Severity:** LOW  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/pyproject.toml`

Dependencies listed:
- `anthropic>=0.40`
- `twscrape>=0.14`
- `playwright>=1.44`
- etc.

But several used dependencies are NOT listed (inferred from imports):
- `beautifulsoup4>=4.12` ✓ listed
- Many third-party provider SDKs (Clay, Jooble, etc.) — may be implicit
- `exa-py>=1.0` — listed but described as conditionally imported

**No lock file (`uv.lock`)** in the repo, making reproducibility harder.

---

## Potential Data Privacy Issues

### Unstructured Context Field Stored in Logs
**Severity:** MEDIUM  
**Location:** `/Users/pedro/Desktop/Code/Nordés/backend/app/models.py:69-75`

The `Case.context` field is free-form text that could contain:
- Personal notes about the debtor (nationality, family details, medical info)
- Previous collector comments (may contain PII)
- Phone numbers, addresses, financial details

These are stored verbatim in the audit log JSON at `logs/{case_id}/{timestamp}.json`.

**Improvement:** Consider redacting or hashing sensitive patterns in context before logging, or move logs to encrypted storage.

---

## Summary of Priorities

| Priority | Count | Items |
|----------|-------|-------|
| **CRITICAL** | 1 | Exposed API keys in `.env` |
| **HIGH** | 2 | Input validation gaps, broad exception catching |
| **MEDIUM** | 6 | Cache collisions, Instagram subprocess, Nominatim config, LLM summary caching, Vision validation, Privacy of context logs |
| **LOW** | 5 | Magic numbers, print vs. logging, timeouts, unused functions, dependency docs |

---

## Recommended Next Steps

1. **Immediate (< 1 day):** Rotate all exposed API keys; remove `.env` from git history
2. **High (< 1 week):** Add input validation on Case model; improve exception messages
3. **Medium (< 2 weeks):** Migrate to structured logging; add module startup validation; fix cache key collisions
4. **Low (ongoing):** Refactor hardcoded numbers; add unit tests; document complex functions
