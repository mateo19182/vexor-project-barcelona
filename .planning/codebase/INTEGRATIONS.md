# External Integrations & APIs

## LLM & Agentic AI

### Anthropic Claude API
- **Provider:** Anthropic
- **Model:** `claude-sonnet-4-6`
- **Auth:** `ANTHROPIC_API_KEY` environment variable
- **Usage Locations:**
  1. **OSINT Web Research** (`backend/app/pipeline/modules/osint_web.py`)
     - Server-side agentic loop with `web_search` and `web_fetch` tools
     - Max tokens: 8000
     - Supports client-side Exa tool fallback (when `EXA_API_KEY` set)
     - Max resumes: 1 (tool loop continuation)
  2. **LLM Dossier Summarization** (`backend/app/pipeline/llm_summary.py`)
     - Synthesizes enrichment findings into factual summary for voice agents
     - Max tokens: 8192
     - Structured JSON output schema for `summary` + `key_facts`
- **Design Principle:** Server-side tool loop for cost efficiency; all claims carry sources (no hallucinations)

## Search & Web Intelligence

### Exa (Optional Web Search)
- **Provider:** Exa Labs
- **Type:** Semantic search + text extraction
- **Auth:** `EXA_API_KEY` environment variable (optional)
- **Trigger Condition:** When set, `osint_web.py` swaps Anthropic web tools for client-side Exa
- **Usage:** `backend/app/pipeline/modules/osint_web.py`
  - Tool name: `exa_search` (client-side tool loop)
  - Max iterations: 6
  - Per-result text truncation: 2000 characters
- **Fallback:** If not set, uses Anthropic's server-side `web_search` / `web_fetch`

### Brave Search API
- **Provider:** Brave Search
- **Type:** Web search with site filtering support
- **Auth:** `BRAVE_API_KEY` environment variable
- **Endpoints:** `https://api.search.brave.com/res/v1/web/search`
- **Usage Locations:**
  1. **BOE Module** (`backend/app/pipeline/modules/boe.py`)
     - Searches Spain's Official State Gazette (`site:boe.es`)
     - Detects bankruptcy, court notices, embargos
  2. **BORME Module** (`backend/app/pipeline/modules/borme.py`)
     - Searches Commercial Registry (`site:boe.es inurl:borme`)
     - Detects director appointments, company dissolutions
  3. **Brave Social Discovery** (`backend/app/pipeline/modules/brave_social.py`)
     - Targeted `site:` queries for social profiles (LinkedIn, Instagram, Twitter, etc.)
     - Returns SocialLink candidates
- **Timeout:** 15 seconds

### Nominatim / OpenStreetMap Geocoding (Free, No Auth)
- **Type:** Address-to-coordinates geolocation
- **URLs:**
  - Nominatim: `https://nominatim.openstreetmap.org/search`
  - Photon (backup): `https://photon.komoot.io/api/`
- **Auth:** User-Agent header required
  - Config key: `NOMINATIM_USER_AGENT`
  - Default: `VexorBCN-Enrichment/0.1 (hackathon; mateoamadoares@gmail.com)`
- **Usage:** `backend/app/services/geocoding.py`
  - Input: Free-text address
  - Output: Provincia, municipio, calle, número
  - Supports country code filtering (ES, PT, PL, FR, etc.)
- **Module:** `backend/app/pipeline/modules/property.py` (calls `geocoding.py`)

## Professional Network Intelligence

### LinkdAPI (LinkedIn Enrichment)
- **Provider:** linkdapi.com
- **Type:** LinkedIn profile scraping API
- **Auth:** `LINKDAPI_API_KEY` environment variable
- **Endpoints:**
  - `/api/v1/profile/overview` — current employment, location, headline
  - `/api/v1/profile/details` — extended profile data
- **Usage:** `backend/app/pipeline/modules/linkedin.py`
  - Requires `contact:linkedin` signal (e.g., `linkedin.com/in/<slug>`)
  - Extracts: employer (contradiction to "unemployed" claims), location, education
  - Emits: `employer`, `role`, `location` signals
- **Graceful Fallback:** Skips cleanly when `LINKDAPI_API_KEY` not set

### Jooble (Job Market Intelligence)
- **Provider:** jooble.org
- **Type:** Job posting aggregator API
- **Auth:** `JOOBLE_API_KEY` environment variable
- **Usage:** `backend/app/pipeline/modules/jooble.py`
  - Requires `role` signal (from LinkedIn or case input)
  - Optional: `location` signal for geographic narrowing
  - Returns: salary ranges, demand levels, job market activity
  - Emits: `lifestyle` signal (employment validation), salary fact
- **Graceful Fallback:** Skips when API key absent or role is non-searchable (e.g., "unemployed")

## Social Media OSINT

### Twitter/X (twscrape)
- **Type:** Twitter API via authenticated scraper (burner account)
- **Auth:** Username/password OR cookie-based (cookies take precedence)
  - `TWITTER_USERNAME` — burner account
  - `TWITTER_PASSWORD` — burner password
  - `TWITTER_COOKIES` — JSON dict of session cookies (preferred; more stable)
- **Usage:** `backend/app/pipeline/modules/twitter.py`
  - Requires: `contact:twitter` signal
  - Fetches: public profile, recent timeline
  - Emits: location, activity/lifestyle, employer/asset signals from bio + tweet content
  - Keyword scanning: employer mentions, travel patterns, asset ownership
- **Module:** `backend/app/enrichment/twitter.py`

### Instagram (Osintgram Wrapper)
- **Type:** Instagram scraper (third-party, requires session)
- **Location:** `../Osintgram/` (sibling directory to `backend/`)
- **Auth:** 
  - `HIKERAPI_TOKEN` — HikerAPI for OSINT Gram's hikerapi-backed mode
  - Paths (configurable):
    - `OSINTGRAM_ROOT` — Osintgram directory (default: `../Osintgram`)
    - `OSINTGRAM_PYTHON` — Python venv (default: `../Osintgram/venv/bin/python`)
    - `OSINTGRAM_OUTPUT_DIR` — Shared cache (default: `../Osintgram/output`)
- **Usage:** `backend/app/pipeline/modules/instagram.py`
  - Requires: `contact:instagram` signal
  - Runs: `enrich_instagram()` async subprocess call
  - Emits: facts (captions analysis), gaps, profile metadata
  - Caching: Output reused across cases per handle (delete subdir to force refresh)
- **Vision Analysis:** `backend/app/enrichment/vision.py` (optional Google Vision for image captions)

## Breach Intelligence & Risk Signals

### XposedOrNot (XON) — Free Breach Lookup
- **Provider:** xposedornot.com
- **Type:** Breach analytics + exposure database
- **Auth:** None (free, public API)
- **Endpoint Base:** `https://api.xposedornot.com/v1`
- **Endpoints Used:**
  - `/breach-analytics/{email}` — rich breach metadata, pastes, password risk
  - `/check-email/{email}` — lightweight fallback list
- **Usage:** `backend/app/pipeline/modules/xon.py`
  - Requires: `contact:email` signal
  - Emits: `contact` signals (every breach domain = registered service), `risk_flag` (plaintext, paste, sensitive data)
  - Sensitive data types flagged: SSNs, credit cards, bank accounts, passports, health/tax records
- **Timeout:** 15 seconds
- **Rate Limit Handling:** 429 → retry with backoff

### Breach Intelligence Provider (Custom Vendor)
- **Provider:** Configurable host, vendor-agnostic
- **Type:** Breach database with email/phone/username lookups
- **Auth:**
  - `BREACH_INTEL_HOST` — upstream hostname (vendor identity hidden; only host URL used)
  - `BREACH_INTEL_API_KEY` — API key for authentication
- **Endpoints:**
  - `POST /api/v1/query` — unauthenticated, masked breach list
  - `POST /api/v1/query_detail_batch` — authenticated, full unmasked scopes
- **Scopes:** email, phone, real_name, user_name
- **Usage:** `backend/app/pipeline/modules/breach_scout.py`
  - Requires: `name` signal (wave 1, early execution)
  - Emits: email/phone/username contact signals, user aliases, breach risk flags
  - Response caps: max 100 records, max 5 MB
- **Design:** Source URLs use only host reference (no vendor hardcoding)
- **Graceful Fallback:** Skips when host/key not configured

## CSINT Platform

### NoSINT (OSINT Aggregator)
- **Provider:** nosint.org
- **Type:** Server-Sent Events (SSE) CSINT platform aggregating 30+ modules
- **Auth:** `NOSINT_API_KEY` (Bearer token)
- **Endpoint:** `https://nosint.org/api/v1/search?target=<TYPE>&module_target=<type>`
- **Protocol:** Server-Sent Events (text/event-stream)
- **Usage:** `backend/app/pipeline/modules/nosint.py` + `backend/app/enrichment/nosint.py`
  - Target types: email (primary), username, phone
  - Returns per-module results: valid registrations, URLs, metadata
  - Emits: contact signals (per-module hits), facts (platform registrations)
- **Timeout:** Connect 10s, read 120s (long-polling friendly)
- **Stream Events:**
  - `start` — search_id, total_modules
  - `result` — module_name, is_valid, result payload, cached flag
  - `done` — end-of-stream marker
- **Result Caps:** Captures valid results only; gaps logged for missing modules

## Platform Registration Checks

### Custom Platform Check VMs (Instagram/Twitter/iCloud/GitHub)
- **Type:** Custom micro-VMs with HTTPS API on self-signed certs
- **Transport:** HTTPS (certificate verification disabled)
- **Host:** `PLATFORM_CHECK_HOST` (default: `163.5.221.166`)
- **Proxy:** `PLATFORM_CHECK_PROXY` (optional)
- **Protocol:**
  - `POST /cs` → `{"s": "<session-uuid>"}` (create session)
  - `POST /h` → `{"s": "<status>"}` (check handle)
    - Body: `{"s": session, "w": identifier, "p": proxy_url}`
- **Status Mapping:**
  - REGISTERED/SUCCESS/VALID/FOUND → True
  - NOT_REGISTERED/FAIL/NOT_FOUND/UNREGISTERED → False
  - INVALID/ERROR → None (ambiguous)
- **Per-Platform Config:**
  - **Instagram:** `INSTAGRAM_CHECK_PORT`, `INSTAGRAM_CHECK_API_KEY` → `backend/app/pipeline/modules/instagram_check.py`
  - **Twitter:** `TWITTER_CHECK_PORT`, `TWITTER_CHECK_API_KEY` → `backend/app/pipeline/modules/twitter_check.py`
  - **iCloud:** `ICLOUD_CHECK_PORT`, `ICLOUD_CHECK_API_KEY` → `backend/app/pipeline/modules/icloud_check.py`
  - **GitHub:** `GITHUB_CHECK_PORT` (default: 19185), `GITHUB_CHECK_API_KEY` → `backend/app/pipeline/modules/github_check.py`
- **Shared Client:** `backend/app/enrichment/platform_check.py`
  - Timeout: 20 seconds
  - Handles session creation, identifier check, status parsing
- **Usage:** Each module requires `contact:email` (or email/phone for iCloud) signal

## Image Intelligence

### SerpAPI Google Lens (Reverse Image Search)
- **Provider:** SerpAPI
- **Type:** Reverse-image lookup API
- **Auth:** `SERPER_API_KEY` environment variable
- **Endpoint:** Google Lens (exact_matches mode only)
- **Usage:** `backend/app/pipeline/modules/image_search.py`
  - Input: Instagram profile picture URL (from `instagram.py`)
  - Strategy: Exact-match only (ignores visual lookalikes to reduce noise)
  - Emits: SocialLink candidates (low confidence 0.2–0.3, marked unverified)
  - Design: Every match labelled as visual-only, not identity verification
- **Graceful Fallback:** Skips cleanly when `SERPER_API_KEY` absent
- **Limitations:** Stock photo / family photo reuse can cause false positives

### Google Vision API (Optional Image Analysis)
- **Provider:** Google Cloud Vision
- **Type:** OCR, face detection, label/safe-search analysis
- **Usage:** `backend/app/enrichment/vision.py`
  - Optional supplement to Instagram enrichment (caption extraction from image metadata)
  - Not a mandatory integration; graceful degradation if not configured
- **File:** `backend/app/enrichment/vision.py` (imported but not active in default pipeline)

## Maps & Geographic Intelligence

### Google Maps GAIA Enrichment
- **Provider:** Google Maps (public data)
- **Type:** Reviews, photos, contributor stats
- **Auth:** `GOOGLE_SESSION_COOKIES` (JSON dict of Google session cookies)
  - Required cookies: `SID`, `SSID`, `APISID`, `SAPISID`, `__Secure-1PAPISID`, `NID`
  - Source: Chrome DevTools → Application → Cookies → google.com
- **Usage:** `backend/app/pipeline/modules/gaia_enrichment.py`
  - Requires: `contact:gaia_id` signal (from `osint_web` or other modules)
  - Techniques:
    - **Stats API:** Direct httpx call to GHunt protobuf endpoint (`_STATS_URL`)
      - Endpoint: `https://www.google.com/locationhistory/preview/mas`
      - Payload: GHunt protobuf template (contributor activity metrics)
    - **Reviews/Photos:** Playwright browser automation (CSS background-image extraction)
      - URLs: `https://www.google.com/maps/contrib/{gaia_id}/reviews`
      - URLs: `https://www.google.com/maps/contrib/{gaia_id}/photos`
  - Emits: contributor stats, review facts, lifestyle signals (travel, restaurant patterns), photos
- **Browser:** Playwright >=1.44 (headless Firefox or Chrome)
- **Graceful Fallback:** Returns structured empty result when cookies not set
- **Source File:** `backend/app/enrichment/gaia_enrichment.py`

## Spanish Government Data

### Spanish Property Registry (Catastro)
- **Provider:** catastro-api.es (third-party API wrapping official data)
- **Type:** Property metadata API
- **Auth:** `CATASTRO_API_KEY` environment variable
- **Endpoint Base:** `https://api.catastro-api.es`
- **Endpoints Used:**
  - `/gateways/geosearch` — address → vías (streets)
  - `/gateways/inmueble_localizacion` — location → property details
- **Usage:** `backend/app/services/catastro.py` (called by `property.py`)
  - Input: geocoded address (via Nominatim)
  - Output: m2 (superficie), uso (land use), año de construcción, referencia catastral
  - Called only for addresses in Spain (country=ES)
- **Timeout:** 15 seconds
- **Graceful Fallback:** Returns None on API errors; gaps propagated (no silent failures)

### MITMA Property Valuation (Ministry of Transport)
- **Source:** `https://apps.fomento.gob.es/boletinonline2/sedal/35103500.XLS`
- **Data:** EUR/m2 estimated sale value per municipio (2025 assessment)
- **Type:** Spreadsheet data (XLS) loaded locally
- **Usage:** `backend/app/services/mitma.py`
  - Called by `property.py` for sale price estimation
  - Provides: price per m2 for Spanish municipalities
  - Bands applied: ×0.80–1.20 (uncertainty range)

### SERPAVI (Ministry of Housing Rental Data)
- **Source:** `https://serpavi.mivau.gob.es/`
- **Data:** EUR/m2/month rental market data (AEAT fiscal data, 2024)
- **Type:** Ministry rental statistics database
- **Usage:** `backend/app/services/serpavi.py`
  - Called by `property.py` for rental price estimation
  - Provides: price per m2/month for Spanish municipalities
  - Bands applied: ×0.85–1.15 (uncertainty range)

## Marketplace Intelligence

### Wallapop
- **Type:** Spanish peer-to-peer marketplace
- **Auth:** None (public scraper)
- **Usage:** `backend/app/pipeline/modules/wallapop.py` + `backend/app/enrichment/wallapop.py`
  - Searches for active seller profiles matching debtor name
  - Extracts: phone numbers from listings, asset value/type, listing proximity to address
  - Scoring: phone match (0.92), location proximity, volume (>= 5 active items = risk flag)
  - Emits: `contact:phone`, `asset`, `location`, `risk_flag` signals
- **Requires:** name signal (optionally enriched by address, phone)

## Logging & Audit Trail

### JSON Audit Logs
- **Type:** Per-run structured logs
- **Location:** `{LOGS_DIR}/{case_id}/{timestamp}.json`
- **Config Key:** `LOGS_DIR` (default: `logs/`)
- **Contents:**
  - Full `EnrichmentResponse` object (dossier, modules, audit events)
  - `AuditEvent` timeline: pipeline_started, wave_started, module_completed, module_cache_hit
  - Module durations, cache hits, error details
- **Purpose:** Non-breaking audit trail; logging failures don't crash the pipeline

## Configuration Summary Table

| Integration | Type | Auth Key | Required | Graceful Fallback |
|-------------|------|----------|----------|-------------------|
| Anthropic Claude | LLM | `ANTHROPIC_API_KEY` | Yes | No (fails) |
| Exa Search | Web Search | `EXA_API_KEY` | No (optional) | Fallback to Anthropic web_search |
| Brave Search | Web Search | `BRAVE_API_KEY` | For BOE/BORME/social | No (skips) |
| Nominatim/Photon | Geocoding | User-Agent header | For property module | No (skips) |
| LinkdAPI | LinkedIn | `LINKDAPI_API_KEY` | For LinkedIn module | Yes (skips) |
| Jooble | Job Market | `JOOBLE_API_KEY` | For Jooble module | Yes (skips) |
| twscrape | Twitter | Username + Password / Cookies | For Twitter module | Yes (skips) |
| Osintgram | Instagram | `HIKERAPI_TOKEN` | For Instagram module | Yes (skips) |
| XposedOrNot | Breach | None (public) | Always available | Yes (fallback) |
| NoSINT CSINT | OSINT | `NOSINT_API_KEY` | For NoSINT module | Yes (skips) |
| Breach Scout | Breach | `BREACH_INTEL_HOST`, `BREACH_INTEL_API_KEY` | For breach module | Yes (skips) |
| Platform Check VMs | Platform Verification | Per-platform port + key | Per-module opt-in | Yes (skips) |
| SerpAPI Google Lens | Image Search | `SERPER_API_KEY` | For image_search module | Yes (skips) |
| Google Maps GAIA | Maps Enrichment | `GOOGLE_SESSION_COOKIES` | For GAIA module | Yes (returns empty) |
| Catastro API | Property Registry | `CATASTRO_API_KEY` | For property module | Yes (skips) |
| MITMA | Valuation Data | None (static XLS) | For property module | Yes (skips) |
| SERPAVI | Rental Data | None (static DB) | For property module | Yes (skips) |
| Wallapop | Marketplace | None (public scraper) | For wallapop module | Yes (skips) |

## Design Principles

1. **No Hallucinations** — Every claim carries a traceable source URL
2. **Graceful Degradation** — Missing API keys don't crash the pipeline; modules skip cleanly
3. **Asyncio Concurrency** — All HTTP clients use `httpx.AsyncClient` for parallel enrichment
4. **User-Agent Honesty** — All external requests include identifying User-Agent headers
5. **Transparency** — Module execution logged to stderr; audit trail in JSON per-run
6. **Defensibility** — All signals carry confidence scores; synthesis dedupes by kind+tag+value
