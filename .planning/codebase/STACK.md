# Tech Stack & Build

## Language & Runtime
- **Python** 3.12 (required: `>=3.12`)
- **Package Manager** `uv` (modern, fast alternative to pip; configured in `backend/pyproject.toml`)

## Web Framework
- **FastAPI** >=0.115 — async web framework for REST API endpoints
- **Uvicorn** >=0.30 (with `[standard]` extras) — ASGI server

## Data & Configuration
- **Pydantic** >=2.8 — data validation and serialization (models in `backend/app/models.py`)
- **pydantic-settings** >=2.4 — environment-based configuration loader
  - Config file: `backend/app/config.py`
  - Env file: `backend/.env` or `../.env` (searched relative to CWD)
  - Example template: `backend/.env.example`

## HTTP Client
- **httpx** >=0.27 — async/sync HTTP client used throughout enrichment modules

## LLM & AI
- **anthropic** >=0.40 — Anthropic SDK for Claude API calls
  - Used in:
    - `backend/app/pipeline/modules/osint_web.py` — Claude Sonnet 4.6 with server-side web_search/web_fetch
    - `backend/app/pipeline/llm_summary.py` — Claude Sonnet 4.6 for final dossier summarization
  - Model constant: `MODEL = "claude-sonnet-4-6"` (see `osint_web.py:35`, `llm_summary.py:28`)
  - Auth: `ANTHROPIC_API_KEY` from environment

## Web Scraping & Data Extraction
- **playwright** >=1.44 — headless browser for GAIA enrichment (Google Maps photo extraction)
  - Used in: `backend/app/enrichment/gaia_enrichment.py` (CSS background-image extraction)
- **beautifulsoup4** >=4.12 — HTML/XML parsing
- **twscrape** >=0.14 — Twitter/X API scraper (burner account auth)
  - Requires: `TWITTER_USERNAME`, `TWITTER_PASSWORD`, or `TWITTER_COOKIES` (JSON)

## Search & OSINT
- **exa-py** >=1.0 — Exa search client for web search (optional; swaps Anthropic web tools when `EXA_API_KEY` set)
  - Used in: `backend/app/pipeline/modules/osint_web.py`
- **python-dotenv** >=1.0 — loads `.env` files

## CLI Entry Point
- Script: `enrich` → `app.cli:main` (defined in `pyproject.toml` as project script)

## Dev Tools
- **ruff** >=0.6 — fast Python linter/formatter (configured: `line-length = 100`)

## Build & Packaging
- Build backend: **hatchling** (defined in `[build-system]`)
- Package location: `backend/app/` (defined in `[tool.hatch.build.targets.wheel]`)

## Project Metadata
- Name: `barcelona`
- Version: `0.1.0`
- Description: "Vexor × Project Europe Barcelona — debtor enrichment agent"
- File: `backend/pyproject.toml`

## Configuration Approach

### Environment Variables (`.env` / config.py)
All secrets and external API keys are loaded via `pydantic-settings` from environment.

**Core LLM & Search:**
- `ANTHROPIC_API_KEY` — Claude API
- `EXA_API_KEY` — Exa web search (optional; falls back to Anthropic web_search)
- `OPENROUTER_API_KEY` — (reserved, not yet used)

**OSINT & Data Providers:**
- `SERPER_API_KEY` — SerpAPI for reverse-image Google Lens lookups
- `BRAVE_API_KEY` — Brave Search API for BOE/BORME/social discovery
- `NOSINT_API_KEY` — NoSINT CSINT platform for email/username/phone enrichment
- `JOOBLE_API_KEY` — Jooble job market API for role/salary signals
- `LINKDAPI_API_KEY` — LinkdAPI for LinkedIn profile enrichment
- `HIKERAPI_TOKEN` — HikerAPI for Osintgram Instagram OSINT

**Breach Intelligence & Platform Checks:**
- `BREACH_INTEL_HOST` — Breach database provider (opaque, host only)
- `BREACH_INTEL_API_KEY` — Breach API auth
- `PLATFORM_CHECK_HOST` — Registration-check VMs (default: `163.5.221.166`)
- `PLATFORM_CHECK_PROXY` — Proxy for platform checks (optional)
- `INSTAGRAM_CHECK_PORT`, `INSTAGRAM_CHECK_API_KEY` — Instagram reg check
- `TWITTER_CHECK_PORT`, `TWITTER_CHECK_API_KEY` — Twitter reg check
- `ICLOUD_CHECK_PORT`, `ICLOUD_CHECK_API_KEY` — iCloud reg check
- `GITHUB_CHECK_PORT` — GitHub check (default: `19185`)
- `GITHUB_CHECK_API_KEY` — GitHub check auth

**Twitter/X Credentials (twscrape):**
- `TWITTER_USERNAME` — Burner account username
- `TWITTER_PASSWORD` — Burner account password
- `TWITTER_COOKIES` — JSON cookie dict (overrides password auth if set)

**Geolocation & Property APIs:**
- `NOMINATIM_USER_AGENT` — OSM Nominatim User-Agent header (default: VexorBCN + email)
- `GOOGLE_SESSION_COOKIES` — JSON dict of Google session cookies for GAIA enrichment
  - Required keys: `SID`, `SSID`, `APISID`, `SAPISID`, `__Secure-1PAPISID`, `NID`
- `CATASTRO_API_KEY` — Spanish Catastro API authentication

**Osintgram Paths (Instagram OSINT):**
- `OSINTGRAM_ROOT` — Root directory (default: `../Osintgram`)
- `OSINTGRAM_PYTHON` — Python binary path (default: `../Osintgram/venv/bin/python`)
- `OSINTGRAM_OUTPUT_DIR` — Shared cache directory (default: `../Osintgram/output`)

**Logging:**
- `LOGS_DIR` — Per-run JSON audit logs (default: `logs/`)
  - Structure: `logs/{case_id}/{timestamp}.json`

## Directory Structure
```
backend/
  app/
    main.py                 FastAPI application & REST endpoints
    models.py               Pydantic I/O models (Case, Signal, Dossier, etc.)
    config.py               Settings loader (pydantic-settings)
    cli.py                  CLI entry point
    pipeline/
      base.py               Module protocol & Context abstraction
      runner.py             Orchestrator (wave scheduling, dependency resolution)
      audit.py              Audit logging
      cache.py              Module result caching
      synthesis.py          Signal deduplication & dossier assembly
      llm_summary.py        Claude-powered dossier summarization
      modules/
        __init__.py         REGISTRY of all enrichment modules
        osint_web.py        Claude web research (web_search / web_fetch tools)
        linkedin.py         LinkedIn enrichment (LinkdAPI)
        twitter.py          Twitter/X timeline & profile (twscrape)
        instagram.py        Instagram OSINT (via enricher)
        gaia_enrichment.py   Google Maps reviews & photos (Google API + Playwright)
        breach_scout.py      Breach database lookups
        xon.py              XposedOrNot breach API
        image_search.py      Reverse-image lookups (SerpAPI Google Lens)
        boe.py              Boletín Oficial del Estado (Brave Search)
        borme.py            Commercial registry (Brave Search)
        wallapop.py         Marketplace seller profiles
        jooble.py           Job market salary & demand signals
        property.py         Spanish property valuation (Catastro + MITMA + SERPAVI)
        platform_check.py    Registration checks (Instagram/Twitter/iCloud/GitHub)
        brave_social.py      Social link discovery (Brave Search)
        nosint.py           NoSINT CSINT platform
      modules/
        *_check.py          Platform-specific check modules
    enrichment/
      linkedin.py           LinkdAPI client
      twitter.py            twscrape wrapper
      instagram.py          Osintgram wrapper + vision analysis
      gaia_enrichment.py     Google Maps enricher (Playwright + httpx)
      nosint.py             NoSINT SSE streamer
      platform_check.py      Shared platform-check VM client
      wallapop.py           Wallapop marketplace scraper
      jooble.py             Jooble API client
      reverse_image.py       SerpAPI Google Lens client
      vision.py             Google Vision API (image analysis)
    services/
      geocoding.py          Nominatim & Photon address lookup
      catastro.py           Spanish property registry API
      mitma.py              Ministry property valuation tables (MITMA T4 2025)
      serpavi.py            SERPAVI rental market data (AEAT fiscal data)
  pyproject.toml            Project metadata, dependencies, build config
  .env.example              Example .env template
```

## Dependencies Summary (pyproject.toml)

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.115 | REST framework |
| uvicorn | >=0.30 (with [standard]) | ASGI server |
| pydantic | >=2.8 | Data validation |
| pydantic-settings | >=2.4 | Config loader |
| httpx | >=0.27 | Async HTTP client |
| anthropic | >=0.40 | Claude API |
| exa-py | >=1.0 | Exa search (optional) |
| playwright | >=1.44 | Browser automation |
| beautifulsoup4 | >=4.12 | HTML parsing |
| twscrape | >=0.14 | Twitter scraper |
| python-dotenv | >=1.0 | .env loader |
| ruff (dev) | >=0.6 | Linter/formatter |

## Execution
```bash
cd backend
uv sync                              # Install deps
uv run uvicorn app.main:app --reload # Start dev server (localhost:8000)
```

API endpoints:
- `GET /health` — health check
- `GET /modules` — list all registered modules
- `POST /enrich` — full enrichment pipeline
- `POST /enrich/{module_name}` — single module

CLI:
```bash
uv run enrich [--fresh [MODULE]] [--only MODULE] <case_json_file>
```
