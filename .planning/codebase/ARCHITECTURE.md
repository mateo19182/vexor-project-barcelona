# Nordés Codebase Architecture

**Project**: Barcelona — Vexor × Project Europe Hackathon  
**Focus**: Pipeline-based OSINT enrichment for debt collection intelligence  
**Core Abstraction**: Wave-scheduled modules with dependency injection via signals

---

## High-Level Pattern

The system implements a **signal-based enrichment pipeline** where:
- **Input** → `Case` (minimal debtor data: name, country, debt amount, legal history)
- **Execution** → Wave-based dependency scheduler running enrichment modules in parallel
- **Output** → `EnrichmentResponse` (dossier + module results + audit trail)

```
┌─────────────┐
│   Case      │
│ (Input)     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│ Context (mutable blackboard)        │
│ - case                              │
│ - signals[] (accumulates)           │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│ Pipeline Runner (Wave-based Scheduler)          │
│ ┌───────────────────────────────────────────┐   │
│ │ Wave N: Run all ready modules in parallel │   │
│ │ - Module requires checking                │   │
│ │ - Cache hit/miss logic                    │   │
│ │ - Async execution + exception handling    │   │
│ └───────────────────────────────────────────┘   │
│ - Accumulate signals into Context               │
│ - Emit audit events (live + replay)             │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ Synthesis Pass                  │
│ - Dedupe signals by (kind,      │
│   tag, value)                   │
│ - Aggregate facts, gaps         │
│ - Build Dossier                 │
└──────┬──────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│ LLM Summary (Optional)          │
│ - Claude condenses dossier      │
│ - Factual only, no coaching     │
└──────┬──────────────────────────┘
       │
       ▼
┌──────────────────────┐
│ EnrichmentResponse   │
│ (HTTP/CLI output)    │
└──────────────────────┘
```

---

## Core Layers

### 1. API & Entry Points

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/main.py`

Routes:
- `POST /enrich` — Run full pipeline with optional `fresh` + `only` query params
- `POST /enrich/{module_name}` — Run single module by name
- `GET /modules` — List all registered modules and their `requires`
- `GET /health` — Service health check

The `/enrich` endpoint calls `run_enrichment(case, fresh=..., only=...)` which orchestrates the entire flow.

**CLI Entry**: `/Users/pedro/Desktop/Code/Nordés/backend/app/cli.py`
- Command: `uv run enrich <case.json> [--fresh [MOD..]] [--only MOD..]`
- Supports stdin (`-`) and module listing (`--list`)

### 2. Data Models

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/models.py`

Core abstractions:

#### `Case` (Pydantic BaseModel)
- **Identity**: `case_id`, `country` (ISO-2 code)
- **Debt**: `debt_eur`, `debt_origin`, `debt_age_months`
- **History**: `call_attempts`, `call_outcome`, `legal_asset_finding`
- **Signals**: `signals: list[Signal]` — caller-provided observations
- **Context**: unstructured notes about the debtor

#### `Signal`
The canonical structured data type — all findings flow through signals.
- `kind: SignalKind` — categorical: name, address, location, employer, role, business, asset, lifestyle, contact, affiliation, risk_flag
- `tag: str | None` — distinguishes signals within a kind (e.g., `contact:email`, `contact:instagram`)
- `value: str` — short canonical form (e.g., "Barcelona, ES", "Acme Corp")
- `source: str` — full URL or reference
- `confidence: float` — 0.0–1.0
- `notes: str | None` — extra detail

#### `Fact`
Free-text claim extracted from enrichment (when Signal doesn't fit).
- `claim`, `source`, `confidence`

#### `ModuleResult`
Standard return shape for every module.
- `name`, `status` ("ok" | "skipped" | "error"), `summary`
- `signals: list[Signal]` — structured findings
- `facts: list[Fact]` — unstructured claims
- `social_links: list[SocialLink]` — platform profiles (auto-converted to contact signals)
- `gaps: list[str]` — missing data / errors
- `raw: dict` — module-specific debug exhaust
- `duration_s: float` — wall-clock execution time

#### `Dossier`
Synthesized final view across all modules.
- `summary: str`, `facts`, `signals`, `gaps`

#### `LlmSummary`
Optional Claude-generated summary for downstream voice agent.
- `summary: str` — prose, facts only
- `key_facts: list[str]` — bullet points

#### `EnrichmentResponse`
HTTP/CLI output wrapping everything.
- `case_id`, `status` ("enriched" | "no_data"), `dossier`, `llm_summary`
- `modules: list[ModuleResult]` — per-module output
- `audit_log: list[AuditEvent]` — execution timeline

#### `AuditEvent`
One structured event from the pipeline.
- `kind: EventKind` — pipeline_started, pipeline_completed, wave_started, module_completed, module_cache_hit
- `elapsed_s: float` — seconds since pipeline start
- `module`, `wave`, `message`, `detail`

### 3. Pipeline Base Abstractions

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/base.py`

#### `Context` (Pydantic BaseModel)
Mutable blackboard passed through the pipeline.
- `case: Case` — read-only input
- `signals: list[Signal]` — accumulated by runner after each wave
- **Query methods**:
  - `best(kind, tag=None) → Signal | None` — highest-confidence match
  - `all(kind, tag=None) → list[Signal]` — all matches sorted by confidence desc
  - `has(kind, tag=None) → bool` — existence check

#### `Module` Protocol
Any class satisfying this protocol becomes a module:
```python
@runtime_checkable
class Module(Protocol):
    name: str
    requires: tuple[tuple[str, str | None], ...]  # (kind, tag) pairs
    async def run(self, ctx: Context) -> ModuleResult: ...
```

The `requires` tuple gates scheduling: a module only runs when all its `(kind, tag)` pairs have at least one matching signal on `ctx.signals`.

#### `ModuleResult`
Described above; returned by every module's `run()` method.

### 4. Pipeline Orchestration

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/runner.py`

The `run_pipeline(ctx, modules, audit, logs_dir, fresh)` function implements a **wave-based scheduler**:

1. **Wave Loop**: While modules are pending:
   - Find all "ready" modules (all `requires` satisfied)
   - If none ready → emit skipped results for remaining modules + break
   - Run all ready modules concurrently via `asyncio.gather()`
   - Catch exceptions per module → `status="error"` with gap
   - Convert each result's `social_links` to `contact:*` signals
   - Accumulate all signals into `ctx.signals`
   - Persist ok/no_data results to cache (unless `fresh` flag)
   - Emit audit events for each completion

2. **Caching**:
   - Cache path: `{logs_dir}/{case_id_slug}/cache/{module_name_slug}.json`
   - Load cached result if available (unless `fresh=True` or module in `fresh` set)
   - Cache is keyed by (case_id, module_name) — reused across runs
   - Only ok/no_data cached; error/skipped always recompute

3. **Audit Trail**: Every meaningful event calls `audit.record(kind, module=..., wave=..., message=..., **detail)`, which both appends an `AuditEvent` and streams to stderr.

4. **Dependency Conversion**:
   - `SocialLink` instances (platform, url, handle, confidence) are automatically converted to `Signal(kind="contact", tag=..., value=handle_or_url, ...)`
   - Mapping: instagram→instagram, twitter→twitter, x→twitter, linkedin→linkedin, github→github, facebook→facebook, tiktok→tiktok
   - Confidence floor: 0.6 (links below this threshold are dropped)

### 5. Synthesis & LLM Summary

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/synthesis.py`

`synthesize(ctx, results) → Dossier`:
- Dedupes signals by `(kind, tag, value.lower().strip())`, keeping highest confidence
- Collects all facts and gaps from all results
- Concatenates summaries from ok results
- Returns `Dossier`

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/llm_summary.py`

`generate_llm_summary(ctx, dossier) → LlmSummary | None`:
- Uses Claude Sonnet 4.6 with JSON schema output
- Reads dossier + case facts + confirmed signals (≥70% confidence)
- Returns factual summary + key bullets
- Rules: facts only, no speculation, no coaching, one fact per bullet
- Returns None if API key missing or parse fails (non-blocking)

### 6. Audit Logging & Persistence

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/audit.py`

`AuditLog` class:
- Records events during pipeline execution
- `record(kind, module=..., wave=..., message=..., stream=True, **detail)` both stores and streams to stderr
- `render_summary(response) → str` produces a compact end-of-run report

`write_run_log(response, logs_dir) → Path`:
- Persists entire `EnrichmentResponse` to `{logs_dir}/{case_id_slug}/{timestamp_UTC}.json`
- One file per run; re-runs accumulate side-by-side

### 7. Caching Layer

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/cache.py`

- `cache_path(logs_dir, case_id, module_name) → Path`
- `load_cached(logs_dir, case_id, module_name) → ModuleResult | None`
- `save_cached(logs_dir, case_id, result) → Path | None`

Cache invalidation:
- `fresh=True` skips cache for all modules
- `fresh={"module_name", ...}` skips for named modules
- Delete cache file manually to force refresh

---

## Enrichment Modules

All modules live in `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/`.

**Registry**: `/Users/pedro/Desktop/Code/Nordés/backend/app/pipeline/modules/__init__.py`

Current modules (19 total):
1. **boe.py** — Spain's Official State Gazette (Brave Search)
   - Requires: name
   - Finds: risk_flag, role signals
2. **borme.py** — Spanish Mercantile Registry
   - Requires: name
3. **brave_social.py** — Brave Search for social profiles
   - Requires: name
4. **breach_scout.py** — Breach database API
   - Requires: email | phone
5. **github_check.py** — GitHub handle validation
   - Requires: contact:github
6. **gaia_enrichment.py** — Google Maps reviews / GAIA data
   - Requires: (empty, standalone)
7. **icloud_check.py** — iCloud registration validation
   - Requires: contact:icloud_email
8. **image_search.py** — Reverse image lookup (SerpAPI)
   - Requires: (empty)
9. **instagram.py** — Instagram OSINT (Osintgram)
   - Requires: contact:instagram
10. **instagram_check.py** — Instagram handle validation
    - Requires: contact:instagram
11. **jooble.py** — Job market salary estimation
    - Requires: role
12. **linkedin.py** — LinkedIn profile enrichment (LinkdAPI)
    - Requires: contact:linkedin
13. **nosint.py** — CSINT platform (30+ modules)
    - Requires: email | phone | username
14. **osint_web.py** — Web search + LLM orchestration
    - Requires: name
    - Emits: contact:* signals (instagram, twitter, linkedin, email, etc.)
15. **property.py** — Spanish property registry (Catastro)
    - Requires: location
16. **twitter_check.py** — Twitter handle validation
    - Requires: contact:twitter
17. **twitter.py** — Twitter/X timeline enrichment (twscrape)
    - Requires: contact:twitter
18. **wallapop.py** — Wallapop (Spanish classifieds) profile
    - Requires: contact:*
19. **xon.py** — Xposed or Not (breach check)
    - Requires: email

### Module Anatomy

Each module is a class instance satisfying the `Module` protocol:

```python
class SampleModule:
    name = "sample"
    requires = (("kind", "tag"), ...)  # gates scheduling
    
    async def run(self, ctx: Context) -> ModuleResult:
        # Read signals from ctx.best(), ctx.all(), ctx.has()
        # Call enrichment functions from app.enrichment.*
        # Return ModuleResult(name, status, summary, signals, facts, gaps, raw)
```

**Pattern**:
- Check required config (`settings.api_key`)
- Skip cleanly if config missing → `status="skipped"` + gap
- Query ctx for input signals
- Call external API or service
- Parse + classify results into signals/facts
- Return `ModuleResult`

---

## Enrichment Service Layer

Support utilities live in `/Users/pedro/Desktop/Code/Nordés/backend/app/enrichment/`.

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

---

## Geocoding & Property Services

Support layer in `/Users/pedro/Desktop/Code/Nordés/backend/app/services/`.

- **geocoding.py** — Nominatim (OSM) + Photon address lookup
- **catastro.py** — Spanish property registry (Catastro)
- **mitma.py** — Spanish property ministry data
- **serpavi.py** — Serpapi reverse address lookup

---

## Configuration

**File**: `/Users/pedro/Desktop/Code/Nordés/backend/app/config.py`

Pydantic `Settings` class reads from `.env` or environment:

```python
class Settings:
    anthropic_api_key: str
    clay_api_key: str
    openrouter_api_key: str
    exa_api_key: str
    brave_api_key: str
    serper_api_key: str
    hikerapi_token: str
    
    osintgram_root: str = "../Osintgram"
    osintgram_python: str = "../Osintgram/venv/bin/python"
    osintgram_output_dir: str = "../Osintgram/output"
    
    breach_intel_host: str
    breach_intel_api_key: str
    
    platform_check_host: str = "163.5.221.166"
    platform_check_proxy: str
    instagram_check_port: str
    instagram_check_api_key: str
    # ... (twitter, icloud, github)
    
    logs_dir: str = "logs"
    nominatim_user_agent: str
    catastro_api_key: str
    
    twitter_username: str
    twitter_password: str
    twitter_cookies: str  # JSON; overrides password
    
    linkdapi_api_key: str
    nosint_api_key: str
    jooble_api_key: str
    google_session_cookies: str
```

All keys are optional; modules skip cleanly if not configured.

---

## Data Flow Example

**Scenario**: Enriching "María López" from Spain

1. **Case Input**:
   ```json
   {
     "case_id": "vx-001",
     "country": "ES",
     "debt_eur": 1240,
     "signals": [
       {"kind": "name", "value": "María López", "source": "case_input", "confidence": 1.0}
     ]
   }
   ```

2. **Context Creation**:
   ```
   Context(case=..., signals=[Signal(kind="name", value="María López", ...)])
   ```

3. **Wave 1** (ready: boe, borme, brave_social, osint_web):
   - `boe` finds BOE entries → emits `Signal(kind="risk_flag")` + facts
   - `osint_web` searches web + LLM → emits `Signal(kind="contact", tag="instagram")`, `Signal(kind="contact", tag="linkedin")`
   - After wave: ctx.signals now includes contact:instagram, contact:linkedin

4. **Wave 2** (ready: instagram, linkedin, instagram_check, twitter_check, ...):
   - `linkedin` fetches LinkdAPI → emits `Signal(kind="employer")`, `Signal(kind="role")`
   - `instagram` runs Osintgram → emits facts about lifestyle
   - After wave: ctx.signals includes employer, role, location

5. **Wave 3** (ready: property, jooble, ...):
   - `property` geocodes + queries Catastro → emits `Signal(kind="asset")`
   - `jooble` estimates salary range → emits fact

6. **Synthesis**:
   - Dedupe signals by (kind, tag, value)
   - Collect all facts, gaps
   - Build `Dossier`

7. **LLM Summary**:
   - Claude reads Dossier + confirmed signals
   - Outputs prose + key bullets

8. **Response**:
   ```json
   {
     "case_id": "vx-001",
     "status": "enriched",
     "dossier": { "summary": "...", "signals": [...], "facts": [...] },
     "llm_summary": { "summary": "...", "key_facts": [...] },
     "modules": [...],
     "audit_log": [...]
   }
   ```

---

## Naming Conventions

- **Module names**: lowercase, underscores (e.g., `osint_web`, `gaia_enrichment`)
- **Signal kinds**: lowercase, snake_case (e.g., `risk_flag`, `contact`)
- **Signal tags**: lowercase, no spaces (e.g., `linkedin`, `instagram`, `email`)
- **File paths**: slugified with underscores (e.g., `barcelona_es` → case_dir)
- **Cache files**: `{logs_dir}/{case_slug}/cache/{module_slug}.json`
- **Run logs**: `{logs_dir}/{case_slug}/{timestamp_UTC}.json`

---

## Error Handling & Graceful Degradation

- **Module exception** → caught, logged as `ModuleResult(status="error", gaps=[...])`
- **Missing config** → module returns `status="skipped"` + gap message
- **Unmet requirements** → runner skips module + gap message
- **Cache failure** → non-blocking, skipped silently
- **Log write failure** → non-blocking, warning to stderr
- **LLM failure** → non-blocking, response still valid without summary

**Philosophy**: One broken module doesn't poison the pipeline. Always return something.

---

## Key Design Decisions

1. **Signals as the universal data type**: No bespoke context mutations or patches. All findings flow through the uniform Signal model.

2. **Wave-based scheduling**: Automatic dependency resolution based on require tuples. Simpler than explicit DAG definition; scales with module count.

3. **Caching at module result level**: Not at intermediate step level. Whole result is cached; if you want to invalidate, you delete the file.

4. **Social links → signals conversion**: Automatic in the runner. Modules don't think about contact signals; they emit social_links, and the runner unlocks downstream modules.

5. **Async-first**: All module runs are concurrent within a wave. No blocking I/O.

6. **Audit trail as first-class citizen**: Events live on the response, enabling both live stderr streaming and post-hoc replay without re-running.

7. **LLM summary as optional**: Full response is valid without it. Allows front-end to render while summary is still being generated (if async).

8. **Defensible sources**: Every signal and fact must carry a `source` URL. No hallucinations.

---

## Testing & Local Development

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
# or
uv run enrich case.json --fresh --only boe borme
uv run enrich --list
```

No automated tests in the codebase yet; hackathon project with manual E2E validation.
