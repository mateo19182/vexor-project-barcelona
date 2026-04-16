# Barcelona — Vexor × Project Europe Hackathon

## What this is
An AI agent that takes a minimal debtor case (name, country, debt amount, call/legal history) and returns enrichment a human collector can actually use. Brief: `notion-the-last-human-industry.md`. Sample data: `[VexorAI] - Project BCN - Sample Data - bcn_hack.csv`.

Judged on: relevance of signals found, defensible sources (every claim traceable), reasoning transparency, honesty about gaps. **Not** judged on accuracy of the final answer.

## Stack
- Python 3.12, `uv` for env + deps
- FastAPI backend
- Anthropic for LLM orchestration
- Clay + other providers for enrichment data

## Layout
```
backend/           Python FastAPI service
  app/
    main.py        FastAPI app + routes
    models.py      Pydantic I/O models (Case, EnrichmentResponse)
    config.py      env settings
    pipeline/
      base.py      Context (shared blackboard), ModuleResult, Module protocol
      runner.py    Wave-based scheduler, auto-promotion of signals/social_links
      synthesis.py Dossier aggregation (dedupe signals, merge facts/gaps)
      llm_summary.py  Claude-generated factual summary for voice agent
      modules/     One file per enrichment module (boe, linkedin, twitter, …)
    enrichment/    Low-level API wrappers (instagram, twitter, nosint, …)
  pyproject.toml
  .env.example     ANTHROPIC_API_KEY, CLAY_API_KEY
frontend/          (TBD — not yet scaffolded)
```

## Run it
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
# POST http://localhost:8000/enrich  with a Case JSON
```

## Data model: everything is a signal

All structured data flows through **signals**. There are no separate identity fields, no `ContextPatch`, no `identity_provenance`. Context is just a signal store.

### Signal — the single structured type
`Signal(kind, value, source, confidence, notes?, tag?)`. Kinds: `name`, `address`, `location`, `employer`, `role`, `business`, `asset`, `lifestyle`, `contact`, `affiliation`, `risk_flag`. Value should be short and canonical (e.g. `"Barcelona, ES"`, `"Acme Corp"` — not a sentence). Extra detail goes in `notes`.

`tag` distinguishes signals within a kind. `contact` signals use tag to separate `email` / `phone` / `instagram` / `linkedin` / `twitter` / `gaia_id` / etc. Most other kinds don't need a tag.

Signals **accumulate on `ctx.signals`** as modules complete. Any downstream module can read prior modules' findings via `ctx.best("employer")`, `ctx.all("contact", "email")`, `ctx.has("name")`.

### Fact — unstructured claims
`Fact(claim, source, confidence)`. Free-text claims that don't fit any `SignalKind`. Use sparingly; prefer signals when the data fits a kind.

### Case input
Two kinds of input:

1. **Signals** — `signals: list[Signal]`. All structured data about the subject. E.g. `{"kind": "name", "value": "Maria Lopez", "source": "case_input", "confidence": 1.0}`, `{"kind": "contact", "tag": "email", "value": "maria@gmail.com", ...}`.
2. **Unstructured context** — `context: str`. Free-form caller notes passed to the LLM summary and osint_web. Not parsed.

### Module output -> ModuleResult
- `signals` — structured observations (accumulated on Context by the runner).
- `facts` — free-text claims.
- `social_links` — discovered profiles: `(platform, url, handle?, confidence)`. Auto-converted to `contact` signals by the runner.
- `summary`, `gaps`, `raw` — prose, known unknowns, debug dump.

### How data flows between modules

1. **Signals accumulate on Context.** After each module, the runner appends `result.signals` to `ctx.signals`. Any later module can query them.
2. **Social links auto-convert to signals.** The runner converts social_links (conf >= 0.6) to `contact` signals with the appropriate tag (e.g. `contact:linkedin`, `contact:instagram`), unlocking downstream modules automatically.
3. **Multiple values coexist.** All signal values are kept. `ctx.best("contact", "email")` returns the highest-confidence one; `ctx.all("contact", "email")` returns all.
4. **Module scheduling.** Each module declares `requires` as a tuple of `(kind, tag)` pairs. The runner checks `ctx.has(kind, tag)` for each pair before scheduling.

### Confidence rubric
- **1.0** — user-supplied / authoritative API (case input, Google Gaia ID)
- **0.85–0.90** — single-source structured field (LinkedIn position, NoSINT hit)
- **0.70–0.80** — self-reported profile data (Twitter location, LinkedIn headline)
- **0.40–0.50** — single regex / keyword match (tweet content scan)
- **0.20–0.30** — unverified visual match (reverse image search)

### Rules
- **Do NOT duplicate a signal as a Fact.** Signals are the structured layer; facts are for free text only.
- **Signal values should be canonical.** `"Acme Corp"` not `"Works at Acme Corp as an engineer"`. Detail goes in `notes`.
- **`raw` is debug exhaust.** Surface useful structured data as signals, not buried in raw dicts.

## Conventions
- Keep it small. This is a 24h hackathon — favor working end-to-end over layered abstractions.
- Every enrichment claim must carry its source. No hallucinated facts.
- If we find nothing, say so explicitly — don't fabricate.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Nordés — OSINT Enrichment Frontend**

A web frontend for the Nordés OSINT enrichment pipeline. Debt recovery agents input debtor data (name, email, phone, address) or import a CSV batch, select which enrichment modules to run, and watch the pipeline execute in real-time via a live log stream and an expanding node graph. Each node in the graph represents an enrichment module; hovering shows a quick summary, clicking expands to full detail. Designed for both hackathon demo impact and real-world debt collector use.

**Core Value:** A collector can go from "I have a name and email" to "I see every enrichment module discovering data in real-time" in under 30 seconds — with full transparency into what was found and where.

### Constraints

- **Tech stack**: React + Vite, React Flow, Tailwind CSS + shadcn/ui, TypeScript
- **Real-time**: WebSocket for live module completion streaming
- **Timeline**: Hackathon — must ship fast, polish over perfection
- **Backend dependency**: Frontend must work with mock data while backend WebSocket endpoint is being built
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Language & Runtime
- **Python** 3.12 (required: `>=3.12`)
- **Package Manager** `uv` (modern, fast alternative to pip; configured in `backend/pyproject.toml`)
## Web Framework
- **FastAPI** >=0.115 — async web framework for REST API endpoints
- **Uvicorn** >=0.30 (with `[standard]` extras) — ASGI server
## Data & Configuration
- **Pydantic** >=2.8 — data validation and serialization (models in `backend/app/models.py`)
- **pydantic-settings** >=2.4 — environment-based configuration loader
## HTTP Client
- **httpx** >=0.27 — async/sync HTTP client used throughout enrichment modules
## LLM & AI
- **anthropic** >=0.40 — Anthropic SDK for Claude API calls
## Web Scraping & Data Extraction
- **playwright** >=1.44 — headless browser for GAIA enrichment (Google Maps photo extraction)
- **beautifulsoup4** >=4.12 — HTML/XML parsing
- **twscrape** >=0.14 — Twitter/X API scraper (burner account auth)
## Search & OSINT
- **exa-py** >=1.0 — Exa search client for web search (optional; swaps Anthropic web tools when `EXA_API_KEY` set)
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
- `ANTHROPIC_API_KEY` — Claude API
- `EXA_API_KEY` — Exa web search (optional; falls back to Anthropic web_search)
- `OPENROUTER_API_KEY` — (reserved, not yet used)
- `SERPER_API_KEY` — SerpAPI for reverse-image Google Lens lookups
- `BRAVE_API_KEY` — Brave Search API for BOE/BORME/social discovery
- `NOSINT_API_KEY` — NoSINT CSINT platform for email/username/phone enrichment
- `JOOBLE_API_KEY` — Jooble job market API for role/salary signals
- `LINKDAPI_API_KEY` — LinkdAPI for LinkedIn profile enrichment
- `HIKERAPI_TOKEN` — HikerAPI for Osintgram Instagram OSINT
- `BREACH_INTEL_HOST` — Breach database provider (opaque, host only)
- `BREACH_INTEL_API_KEY` — Breach API auth
- `PLATFORM_CHECK_HOST` — Registration-check VMs (default: `163.5.221.166`)
- `PLATFORM_CHECK_PROXY` — Proxy for platform checks (optional)
- `INSTAGRAM_CHECK_PORT`, `INSTAGRAM_CHECK_API_KEY` — Instagram reg check
- `TWITTER_CHECK_PORT`, `TWITTER_CHECK_API_KEY` — Twitter reg check
- `ICLOUD_CHECK_PORT`, `ICLOUD_CHECK_API_KEY` — iCloud reg check
- `GITHUB_CHECK_PORT` — GitHub check (default: `19185`)
- `GITHUB_CHECK_API_KEY` — GitHub check auth
- `TWITTER_USERNAME` — Burner account username
- `TWITTER_PASSWORD` — Burner account password
- `TWITTER_COOKIES` — JSON cookie dict (overrides password auth if set)
- `NOMINATIM_USER_AGENT` — OSM Nominatim User-Agent header (default: VexorBCN + email)
- `GOOGLE_SESSION_COOKIES` — JSON dict of Google session cookies for GAIA enrichment
- `CATASTRO_API_KEY` — Spanish Catastro API authentication
- `OSINTGRAM_ROOT` — Root directory (default: `../Osintgram`)
- `OSINTGRAM_PYTHON` — Python binary path (default: `../Osintgram/venv/bin/python`)
- `OSINTGRAM_OUTPUT_DIR` — Shared cache directory (default: `../Osintgram/output`)
- `LOGS_DIR` — Per-run JSON audit logs (default: `logs/`)
## Directory Structure
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
- `GET /health` — health check
- `GET /modules` — list all registered modules
- `POST /enrich` — full enrichment pipeline
- `POST /enrich/{module_name}` — single module
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Language & Python Version
- **Python 3.12** (as specified in `pyproject.toml`)
- All modules use `from __future__ import annotations` for forward-compatible type hints
## Code Style
### Formatting & Linting
- **Line length:** 100 characters (enforced by `tool.ruff` in `pyproject.toml`)
- **Formatter:** Ruff is the primary linter (`ruff>=0.6` in dev dependencies)
- **Import sorting:** No explicit isort config; handled by Ruff defaults
- Code generally follows PEP 8 conventions with the 100-char line limit as the main deviation
### Type Hints
- **Pervasive and explicit:** Every function has full type hints (parameters + return type)
- Format: Modern Python 3.10+ syntax (`list[T]`, `dict[K, V]`, `T | None` instead of `Optional[T]`)
- Used in function signatures, class attributes, and async function returns
- Example from `models.py`:
### Docstrings
- **Module-level docstrings:** Every `.py` file has a docstring at the top explaining purpose
- **Class/method docstrings:** Used selectively for complex logic or API surfaces
- **Format:** Prose with examples, not strict Google/NumPy format
- Example from `base.py`:
## Naming Conventions
### Modules & Files
- **Snake_case** for all Python filenames and module names: `linkedin.py`, `gaia_enrichment.py`, `test_module_property.py`
- **Descriptive names:** Modules named after the enrichment source or capability (e.g., `linkedin`, `instagram`, `property`, `jooble`)
- **Module class names:** PascalCase with `Module` suffix: `LinkedInModule`, `InstagramModule`, `PropertyModule`, `GaiaEnrichmentModule`
### Variables & Functions
- **snake_case** for all variables, functions, and methods (including async)
- **Private functions:** Prefixed with `_` (underscore): `_missing_requirements()`, `_log()`, `_social_links_to_signals()`
- **Constants:** UPPER_CASE: `_CONFIDENCE_THRESHOLD`, `JOOBLE_TIMEOUT_S`, `_ASSET_KEYWORDS`, `MODEL`, `MAX_TOKENS`
- **Dataclass/Model fields:** snake_case, matching Pydantic defaults: `case_id`, `debt_eur`, `llm_summary`, `elapsed_s`
### Signals & Data Flow
- **Signal kinds:** Literal values matching domain semantics:
- **Signal tags:** Used to disambiguate within a kind (e.g., `contact:linkedin`, `contact:instagram`)
- **Source URLs:** Every Signal must have a full URL or reference backing the observation
## Architectural Patterns
### Module Structure
- Class attributes `name` and `requires` are **required** (not in `__init__`)
- `run()` is always **async** even if it doesn't use await
- Always returns a `ModuleResult` (never raises; exceptions are caught by the runner)
- `requires` is a tuple of `(kind, tag)` pairs; runner gates scheduling based on these
### Signals & Context Flow
- **Context** (`base.py`): Mutable blackboard passed through the pipeline
- **Signals**: Structured, provenance-tagged observations
- **Facts**: Free-text claims with source (use when observation doesn't fit a `SignalKind`)
- **SocialLinks**: Converted to `contact` signals by the runner during synthesis
### Wave-Based Scheduling
- **Pipeline runner** (`runner.py`): Orchestrates parallel execution via waves
- `_missing_requirements(ctx, module)` → list of unmet (kind, tag) pairs
- `_social_links_to_signals(links)` → convert SocialLinks to contact Signals (confidence floor: 0.6)
- `_accumulate_signals(ctx, result)` → append module's signals + converted social_links
- `run_pipeline(ctx, modules, audit, ...)` → orchestrates the full wave-based execution
### Error Handling & Graceful Degradation
- **No exceptions escape modules:** Every module returns a `ModuleResult` with `status` in `["ok", "skipped", "error"]`
- **Gaps instead of failures:** When a module can't produce data, it adds entries to `gaps[]` (human-readable explanations)
- **Configuration-based skipping:** Modules check for required API keys/env vars and self-skip gracefully
- **No silent failures:** Every "nothing happened" scenario documents itself in `gaps`
### Result Caching
- **Cache location:** `{logs_dir}/{case_id}/cache/{module_name}.json`
- **Cache policy:**
- **Invalidation:**
### Async Patterns
- **All I/O is async:** HTTP calls, subprocess launches, and other I/O use async/await
- **Blocking code in executors:** CPU-intensive or legacy sync code (e.g., Jooble HTTP in `jooble.py`) runs in `asyncio.get_event_loop().run_in_executor()`
- **No blocking in the hot path:** Main pipeline threads never block waiting for sync I/O
## Data Models
### Pydantic Models
- **Case**: Input debtor profile (minimal)
- **Signal**: Structured observation (kind, value, source, confidence, tag, notes)
- **Fact**: Free-text claim with source
- **SocialLink**: Social media profile (platform, url, handle, confidence)
- **ModuleResult**: Standard return shape for every module
- **Dossier**: Synthesized final view (summary, facts, signals, gaps)
- **LlmSummary**: LLM-generated summary for downstream consumers
- **AuditEvent & EnrichmentResponse**: Pipeline telemetry
- Models use `Field()` for descriptions and constraints (`ge`, `le`, etc.)
- Field constraints are declarative (e.g., `confidence: float = Field(ge=0.0, le=1.0)`)
- Enum-like constraints use `Literal[]` (e.g., `SignalKind` is a `Literal` union)
## Configuration
- **Settings class:** `app/config.py` uses `pydantic-settings`
- **Env vars:** Loaded from `.env` (local) and `../.env` (parent dir)
- **API keys & hosts:** All configurable via env; missing keys degrade gracefully (modules self-skip)
- **Paths:** Relative to project; e.g., `osintgram_root="../Osintgram"` assumes sibling directory
## Import Style
- **Absolute imports:** All imports are absolute from the `app` package root
- **No relative imports:** Never use `from . import` or `from .. import`
- **Grouping order** (implicit):
## Logging & Debugging
- **Stderr for live output:** `print(..., file=sys.stderr, flush=True)` for progress/debug output
- **No logging library:** Uses direct `print` to stderr; captured in audit logs and run logs
- **Private log helper:** `_log(msg)` in many modules for consistency
- **Structured audit events:** Pipeline orchestration emits `AuditEvent` objects (kind, elapsed_s, module, message, detail)
## File Organization
- `backend/app/`:
## Testing
- **Framework:** `pytest` with `pytest-asyncio`
- **Location:** `backend/tests/`
- **Pattern:** Async test methods use `@pytest.mark.asyncio` decorator
- **Mocking:** `unittest.mock` (AsyncMock, patch)
- **Coverage:** Limited; see TESTING.md for details
## Comments & Docstrings
- **When to comment:** Complex logic, non-obvious design decisions, data transformations
- **Avoid:** Restating obvious code; prefer clear variable/function names instead
- **Docstrings:** Module-level mandatory; method-level optional but encouraged for public APIs
- **Code examples in docstrings:** Provided for complex modules (e.g., `base.py`)
## Special Conventions
### Signal Confidence Scoring
- **1.0**: Definitive (e.g., claimed by debtor directly, verified receipt)
- **0.85**: High confidence (e.g., LinkedIn headline, public profile info)
- **0.80**: Solid (e.g., social media profile location, public review)
- **0.75**: Reasonable (e.g., Google Maps photo location)
- **0.70**: Moderate (e.g., inferred from context)
- **0.6+**: Above the platform-conversion floor (social links converted to contact signals)
- **< 0.6**: Surfaced in facts/raw but not promoted to structured signals
### Module Naming & Naming Collisions
- All module names must be unique in the registry (`REGISTRY` in `pipeline/modules/__init__.py`)
- Example modules: `linkedin`, `instagram`, `twitter`, `property`, `wallapop`, `gaia_enrichment`, `jooble`, etc.
- Each module registers itself by instantiating in `__init__.py`
### Status Values
- `"ok"` — Module ran successfully, produced signals/facts (or cleanly found nothing)
- `"skipped"` — Module's requirements weren't met or it self-skipped (e.g., API key missing)
- `"error"` — Module raised an exception or failed unexpectedly
- `"no_data"` — Module ran but found no enrichment data (rare; usually just `"ok"` with empty signals/facts)
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## High-Level Pattern
- **Input** → `Case` (minimal debtor data: name, country, debt amount, legal history)
- **Execution** → Wave-based dependency scheduler running enrichment modules in parallel
- **Output** → `EnrichmentResponse` (dossier + module results + audit trail)
```
```
## Core Layers
### 1. API & Entry Points
- `POST /enrich` — Run full pipeline with optional `fresh` + `only` query params
- `POST /enrich/{module_name}` — Run single module by name
- `GET /modules` — List all registered modules and their `requires`
- `GET /health` — Service health check
- Command: `uv run enrich <case.json> [--fresh [MOD..]] [--only MOD..]`
- Supports stdin (`-`) and module listing (`--list`)
### 2. Data Models
#### `Case` (Pydantic BaseModel)
- **Identity**: `case_id`, `country` (ISO-2 code)
- **Debt**: `debt_eur`, `debt_origin`, `debt_age_months`
- **History**: `call_attempts`, `call_outcome`, `legal_asset_finding`
- **Signals**: `signals: list[Signal]` — caller-provided observations
- **Context**: unstructured notes about the debtor
#### `Signal`
- `kind: SignalKind` — categorical: name, address, location, employer, role, business, asset, lifestyle, contact, affiliation, risk_flag
- `tag: str | None` — distinguishes signals within a kind (e.g., `contact:email`, `contact:instagram`)
- `value: str` — short canonical form (e.g., "Barcelona, ES", "Acme Corp")
- `source: str` — full URL or reference
- `confidence: float` — 0.0–1.0
- `notes: str | None` — extra detail
#### `Fact`
- `claim`, `source`, `confidence`
#### `ModuleResult`
- `name`, `status` ("ok" | "skipped" | "error"), `summary`
- `signals: list[Signal]` — structured findings
- `facts: list[Fact]` — unstructured claims
- `social_links: list[SocialLink]` — platform profiles (auto-converted to contact signals)
- `gaps: list[str]` — missing data / errors
- `raw: dict` — module-specific debug exhaust
- `duration_s: float` — wall-clock execution time
#### `Dossier`
- `summary: str`, `facts`, `signals`, `gaps`
#### `LlmSummary`
- `summary: str` — prose, facts only
- `key_facts: list[str]` — bullet points
#### `EnrichmentResponse`
- `case_id`, `status` ("enriched" | "no_data"), `dossier`, `llm_summary`
- `modules: list[ModuleResult]` — per-module output
- `audit_log: list[AuditEvent]` — execution timeline
#### `AuditEvent`
- `kind: EventKind` — pipeline_started, pipeline_completed, wave_started, module_completed, module_cache_hit
- `elapsed_s: float` — seconds since pipeline start
- `module`, `wave`, `message`, `detail`
### 3. Pipeline Base Abstractions
#### `Context` (Pydantic BaseModel)
- `case: Case` — read-only input
- `signals: list[Signal]` — accumulated by runner after each wave
- **Query methods**:
#### `Module` Protocol
```python
```
#### `ModuleResult`
### 4. Pipeline Orchestration
### 5. Synthesis & LLM Summary
- Dedupes signals by `(kind, tag, value.lower().strip())`, keeping highest confidence
- Collects all facts and gaps from all results
- Concatenates summaries from ok results
- Returns `Dossier`
- Uses Claude Sonnet 4.6 with JSON schema output
- Reads dossier + case facts + confirmed signals (≥70% confidence)
- Returns factual summary + key bullets
- Rules: facts only, no speculation, no coaching, one fact per bullet
- Returns None if API key missing or parse fails (non-blocking)
### 6. Audit Logging & Persistence
- Records events during pipeline execution
- `record(kind, module=..., wave=..., message=..., stream=True, **detail)` both stores and streams to stderr
- `render_summary(response) → str` produces a compact end-of-run report
- Persists entire `EnrichmentResponse` to `{logs_dir}/{case_id_slug}/{timestamp_UTC}.json`
- One file per run; re-runs accumulate side-by-side
### 7. Caching Layer
- `cache_path(logs_dir, case_id, module_name) → Path`
- `load_cached(logs_dir, case_id, module_name) → ModuleResult | None`
- `save_cached(logs_dir, case_id, result) → Path | None`
- `fresh=True` skips cache for all modules
- `fresh={"module_name", ...}` skips for named modules
- Delete cache file manually to force refresh
## Enrichment Modules
### Module Anatomy
```python
```
- Check required config (`settings.api_key`)
- Skip cleanly if config missing → `status="skipped"` + gap
- Query ctx for input signals
- Call external API or service
- Parse + classify results into signals/facts
- Return `ModuleResult`
## Enrichment Service Layer
- **linkedin.py** — LinkdAPI client (overview + details endpoints)
- **instagram.py** — Osintgram subprocess orchestration
- **twitter.py** — twscrape client
- **nosint.py** — CSINT platform wrapper
- **jooble.py** — Jooble job API
- **gaia_enrichment.py** — Google Maps cookie-based auth
- **wallapop.py** — Wallapop profile scraper
- **vision.py** — Claude vision for image analysis
- **reverse_image.py** — SerpAPI reverse image lookup
- **platform_check.py** — HTTPS registration validators (Instagram, Twitter, iCloud, GitHub)
## Geocoding & Property Services
- **geocoding.py** — Nominatim (OSM) + Photon address lookup
- **catastro.py** — Spanish property registry (Catastro)
- **mitma.py** — Spanish property ministry data
- **serpavi.py** — Serpapi reverse address lookup
## Configuration
```python
```
## Data Flow Example
## Naming Conventions
- **Module names**: lowercase, underscores (e.g., `osint_web`, `gaia_enrichment`)
- **Signal kinds**: lowercase, snake_case (e.g., `risk_flag`, `contact`)
- **Signal tags**: lowercase, no spaces (e.g., `linkedin`, `instagram`, `email`)
- **File paths**: slugified with underscores (e.g., `barcelona_es` → case_dir)
- **Cache files**: `{logs_dir}/{case_slug}/cache/{module_slug}.json`
- **Run logs**: `{logs_dir}/{case_slug}/{timestamp_UTC}.json`
## Error Handling & Graceful Degradation
- **Module exception** → caught, logged as `ModuleResult(status="error", gaps=[...])`
- **Missing config** → module returns `status="skipped"` + gap message
- **Unmet requirements** → runner skips module + gap message
- **Cache failure** → non-blocking, skipped silently
- **Log write failure** → non-blocking, warning to stderr
- **LLM failure** → non-blocking, response still valid without summary
## Key Design Decisions
## Testing & Local Development
```bash
```
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
