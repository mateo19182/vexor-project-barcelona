# Nordés Codebase Structure

**Complete directory and file layout for the debt enrichment pipeline.**

---

## Root Directory

```
/Users/pedro/Desktop/Code/Nordés/
├── backend/                          # Python FastAPI service (main focus)
├── frontend/                          # TBD (not yet scaffolded)
├── CLAUDE.md                         # Project charter + conventions
└── ... (config, docs, agent, etc.)
```

---

## Backend Application

```
backend/
├── pyproject.toml                    # Project metadata, dependencies, scripts
├── .env.example                      # Template for environment variables
├── .env                              # (user-local, git-ignored)
├── uv.lock                          # Dependency lock file (uv)
│
└── app/                              # Main application package
    │
    ├── __init__.py                   # Package marker
    ├── main.py                       # FastAPI app + HTTP routes
    ├── cli.py                        # CLI entry point (uv run enrich)
    ├── config.py                     # Settings (Pydantic) + env vars
    ├── models.py                     # Data models (Case, Signal, ModuleResult, etc.)
    │
    ├── pipeline/                     # Core orchestration
    │   ├── __init__.py               # (empty)
    │   ├── base.py                   # Module protocol, Context, ModuleResult
    │   ├── runner.py                 # Wave-based scheduler (main orchestration)
    │   ├── synthesis.py              # Dossier aggregation + deduplication
    │   ├── llm_summary.py            # Claude-based summary generation
    │   ├── audit.py                  # Event logging + run log persistence
    │   ├── cache.py                  # Per-module result caching
    │   │
    │   └── modules/                  # Individual enrichment modules (19 total)
    │       ├── __init__.py           # REGISTRY: list of all module instances
    │       │
    │       ├── boe.py                # Boletín Oficial del Estado (Spain)
    │       ├── borme.py              # Spanish Mercantile Registry
    │       ├── brave_social.py       # Brave Search for social profiles
    │       ├── breach_scout.py       # Breach database lookups
    │       ├── github_check.py       # GitHub handle validation
    │       ├── gaia_enrichment.py    # Google Maps (GAIA)
    │       ├── icloud_check.py       # iCloud registration check
    │       ├── image_search.py       # Reverse image search (SerpAPI)
    │       ├── instagram.py          # Instagram OSINT (Osintgram)
    │       ├── instagram_check.py    # Instagram handle validation
    │       ├── jooble.py             # Job market salary estimation
    │       ├── linkedin.py           # LinkedIn enrichment (LinkdAPI)
    │       ├── nosint.py             # CSINT platform wrapper
    │       ├── osint_web.py          # Web search + LLM orchestration
    │       ├── property.py           # Spanish property registry (Catastro)
    │       ├── twitter_check.py      # Twitter/X handle validation
    │       ├── twitter.py            # Twitter/X timeline enrichment
    │       ├── wallapop.py           # Wallapop (Spanish classifieds)
    │       └── xon.py                # Xposed or Not (breach check)
    │
    ├── enrichment/                   # Support utilities for external APIs
    │   ├── __init__.py               # (empty)
    │   ├── linkedin.py               # LinkdAPI client
    │   ├── instagram.py              # Osintgram wrapper
    │   ├── twitter.py                # twscrape client
    │   ├── nosint.py                 # CSINT platform client
    │   ├── jooble.py                 # Jooble API wrapper
    │   ├── gaia_enrichment.py        # Google Maps cookie-based enrichment
    │   ├── wallapop.py               # Wallapop scraper
    │   ├── vision.py                 # Claude vision for images
    │   ├── reverse_image.py          # SerpAPI reverse lookup
    │   └── platform_check.py         # HTTPS registration validators
    │
    └── services/                     # Geographic + property data services
        ├── __init__.py               # (empty)
        ├── geocoding.py              # Nominatim (OSM) + Photon
        ├── catastro.py               # Spanish property registry API
        ├── mitma.py                  # Spanish property ministry
        └── serpavi.py                # Serpapi reverse address lookup
```

---

## Key Files & Their Roles

### Entry Points

| File | Role | Usage |
|------|------|-------|
| `main.py` | FastAPI routes | `uvicorn app.main:app --reload` |
| `cli.py` | CLI interface | `uv run enrich case.json` |
| `pyproject.toml` | Project config | `uv sync`, dependencies |

### Data Models

| File | Contains |
|------|----------|
| `models.py` | Case, Signal, Fact, ModuleResult, Dossier, LlmSummary, EnrichmentResponse, AuditEvent |
| `config.py` | Settings (env vars) |

### Pipeline Core

| File | Responsibility |
|------|-----------------|
| `pipeline/base.py` | Module protocol, Context, ModuleResult |
| `pipeline/runner.py` | Wave-based scheduler, dependency resolution, caching |
| `pipeline/synthesis.py` | Dossier building, signal deduplication |
| `pipeline/llm_summary.py` | Claude summary generation |
| `pipeline/audit.py` | Event logging, run log persistence |
| `pipeline/cache.py` | Per-module result caching |

### Modules (19)

Each module lives in its own file:
- `pipeline/modules/{name}.py` — Class implementing Module protocol
- Registered in `pipeline/modules/__init__.py` as a module instance

### Enrichment Wrappers

Each external API/tool gets a dedicated wrapper:
- `enrichment/{platform}.py` — API client, parsing, error handling

### Services

Shared utility layers:
- `services/geocoding.py` — Address lookup (Nominatim, Photon)
- `services/catastro.py` — Spanish property registry
- `services/mitma.py` — Property ministry data
- `services/serpavi.py` — Reverse address lookup

---

## File Conventions

### Naming

- **Module files**: `{service_name}.py` (lowercase, underscores)
  - E.g., `osint_web.py`, `gaia_enrichment.py`, `breach_scout.py`
  
- **Class names**: PascalCase + `Module` suffix
  - E.g., `LinkedInModule`, `BoeModule`, `PropertyModule`
  
- **Module instance name**: lowercase (without "Module" suffix)
  - E.g., `LinkedInModule()` → registered as `name="linkedin"`
  
- **API/enrichment files**: Match the service/platform name
  - E.g., `enrichment/linkedin.py`, `enrichment/instagram.py`

### Directory Structure Philosophy

1. **`pipeline/`** — Orchestration only. No external API calls.
   - `base.py` → Protocols and data structures
   - `runner.py` → Scheduling logic
   - `synthesis.py` → Dossier building
   - `audit.py` → Logging
   - `cache.py` → Result caching
   - `modules/` → Individual enrichment tasks

2. **`enrichment/`** — External API clients. No orchestration.
   - One file per API/tool
   - Parse + classify results
   - Modules call these functions

3. **`services/`** — Shared utilities (geocoding, property data).
   - One file per service category

4. **Root `app/`** — Configuration, data models, entry points.

---

## Signal & Module Dependencies

### Signal Kinds

```python
SignalKind = Literal[
    "name",          # subject's name
    "address",       # physical address
    "location",      # current/frequent residence or region
    "employer",      # company or organization affiliation
    "role",          # job title / position
    "business",      # ownership / directorship / self-employment
    "asset",         # bank account, vehicle, property, crypto, etc.
    "lifestyle",     # travel, luxury goods, hobbies
    "contact",       # email, phone, handles → tag distinguishes
    "affiliation",   # clubs, associations, education
    "risk_flag",     # data breach hit, criminal record, sanctions
]
```

### Contact Tags

Within `kind="contact"`, `tag` values:
- `email`, `phone`, `instagram`, `linkedin`, `twitter`, `github`, `facebook`, `tiktok`, `gaia_id`, `icloud_email`

### Modules & Their Requirements

(See `ARCHITECTURE.md` for full descriptions)

| Module | Requires | Emits |
|--------|----------|-------|
| boe | name | risk_flag, role |
| borme | name | (varies) |
| brave_social | name | social_links |
| breach_scout | email \| phone | risk_flag |
| github_check | contact:github | signals |
| gaia_enrichment | (none) | signals, facts |
| icloud_check | contact:icloud_email | signals |
| image_search | (none) | facts |
| instagram | contact:instagram | facts, lifestyle signals |
| instagram_check | contact:instagram | signals |
| jooble | role | facts, role signals |
| linkedin | contact:linkedin | employer, role, location |
| nosint | email \| phone \| username | signals |
| osint_web | name | contact signals, social_links |
| property | location | asset, address signals |
| twitter_check | contact:twitter | signals |
| twitter | contact:twitter | facts, lifestyle signals |
| wallapop | contact:* | signals, facts |
| xon | email | risk_flag |

---

## Runtime Artifacts

### Logs Directory

```
logs/
└── {case_id_slug}/
    ├── {timestamp_UTC}.json          # Full EnrichmentResponse (run log)
    ├── {timestamp_UTC}.json          # (subsequent runs accumulate)
    └── cache/
        ├── {module_slug}.json        # Cached ModuleResult
        ├── {module_slug}.json        # (one per module)
        └── ...
```

**Case ID slugging**: Alphanumeric + `._-` only; rest → underscores. Max 128 chars.  
**Module slugging**: Same rules.  
**Timestamp**: UTC, `YYYYMMDDTHHMMSSZ` format.

### Cache Invalidation

- Manual: Delete `cache/{module_slug}.json`
- Fresh run: Pass `--fresh` to CLI or `fresh=True` to `/enrich?fresh=true`
- Fresh specific modules: `--fresh mod1 mod2` or `?fresh=mod1&fresh=mod2`

---

## Environment Variables

**Source**: `.env` (user-local) or `pyproject.toml` defaults

```bash
# LLM & Platform APIs
ANTHROPIC_API_KEY=sk-...
CLAY_API_KEY=...
OPENROUTER_API_KEY=...
EXA_API_KEY=...
BRAVE_API_KEY=...
SERPER_API_KEY=...

# Breach Intelligence
BREACH_INTEL_HOST=...
BREACH_INTEL_API_KEY=...

# Platform Checks (Instagram, Twitter, iCloud, GitHub)
PLATFORM_CHECK_HOST=163.5.221.166
PLATFORM_CHECK_PROXY=...
INSTAGRAM_CHECK_PORT=...
INSTAGRAM_CHECK_API_KEY=...
TWITTER_CHECK_PORT=...
TWITTER_CHECK_API_KEY=...
ICLOUD_CHECK_PORT=...
ICLOUD_CHECK_API_KEY=...
GITHUB_CHECK_PORT=19185
GITHUB_CHECK_API_KEY=...

# Osintgram (Instagram OSINT)
OSINTGRAM_ROOT=../Osintgram
OSINTGRAM_PYTHON=../Osintgram/venv/bin/python
OSINTGRAM_OUTPUT_DIR=../Osintgram/output
HIKERAPI_TOKEN=...

# LinkedIn (LinkdAPI)
LINKDAPI_API_KEY=...

# CSINT Platform
NOSINT_API_KEY=...

# Jooble (Job Market)
JOOBLE_API_KEY=...

# Twitter/X (twscrape)
TWITTER_USERNAME=...
TWITTER_PASSWORD=...
TWITTER_COOKIES=...  # JSON dict; overrides password

# Google Maps / GAIA
GOOGLE_SESSION_COOKIES=...  # JSON dict of cookies

# Geocoding & Property
NOMINATIM_USER_AGENT=VexorBCN-Enrichment/0.1 (...)
CATASTRO_API_KEY=...

# Runtime
LOGS_DIR=logs
```

All keys are optional. Modules skip cleanly if not configured.

---

## Key Abstractions & Patterns

### Module Registration

**File**: `pipeline/modules/__init__.py`

```python
from app.pipeline.modules.boe import BoeModule
# ... (import all modules)

REGISTRY: list[Module] = [
    BoeModule(),
    BormeModule(),
    # ... (all 19 modules in dependency order)
]
```

Order in REGISTRY is preserved in API responses.

### Module Class Anatomy

```python
class SampleModule:
    name = "sample"                          # str
    requires = (("kind", "tag"), ...)       # tuple of (str, str|None) pairs
    
    async def run(self, ctx: Context) -> ModuleResult:
        # 1. Validate config (settings.api_key)
        # 2. Check required inputs (ctx.best, ctx.has)
        # 3. Call enrichment function(s)
        # 4. Parse + classify results
        # 5. Return ModuleResult
```

### Signal Creation

```python
Signal(
    kind="employer",
    value="Acme Corp",
    source="https://...",
    confidence=0.85,
    notes="Found on LinkedIn",
    tag=None  # optional; distinguishes within a kind
)
```

### Fact Creation

```python
Fact(
    claim="LinkedIn headline: Senior Manager",
    source="https://linkedin.com/...",
    confidence=0.80
)
```

---

## Testing & Development Workflow

### Local Setup

```bash
cd backend
uv sync                                  # Install dependencies
uv run uvicorn app.main:app --reload     # Start API on http://localhost:8000
```

### CLI Testing

```bash
uv run enrich sample_case.json
uv run enrich case.json --fresh          # Bypass cache
uv run enrich case.json --only boe borme # Run specific modules
uv run enrich --list                     # List all modules + requires
cat case.json | uv run enrich -          # From stdin
```

### API Testing

```bash
# Full enrichment
curl -X POST http://localhost:8000/enrich \
  -H "Content-Type: application/json" \
  -d @case.json

# Single module
curl -X POST http://localhost:8000/enrich/linkedin?fresh=true \
  -H "Content-Type: application/json" \
  -d @case.json

# List modules
curl http://localhost:8000/modules

# Health check
curl http://localhost:8000/health
```

### Output Format

**Stdout/API Response**:
- JSON: `EnrichmentResponse` (Pydantic model_dump)

**Stderr**:
- Live audit stream (one line per event)
- End-of-run summary block

---

## Deployment Notes

- **Language**: Python 3.12+
- **Package manager**: `uv`
- **Web framework**: FastAPI
- **Async**: asyncio
- **Data validation**: Pydantic v2
- **No database**: Stateless service. Results cached to filesystem.

**Docker** (not yet implemented):
- Base: Python 3.12 slim
- Deps: Install via `uv sync`
- ENTRYPOINT: `uvicorn app.main:app`
- Mount volume for `/app/logs` and `/app/.env`

---

## Related Directories (Non-Core)

```
.agent/                 # Agent documentation (meta)
.planning/              # Planning docs
  └── codebase/         # This directory
      ├── ARCHITECTURE.md
      └── STRUCTURE.md
frontend/               # TBD
```

---

## Summary

**Total files**: ~50 Python modules + config/docs

**Organized by responsibility**:
1. **Pipeline orchestration** → `pipeline/{base,runner,synthesis,audit,cache}.py`
2. **Individual modules** → `pipeline/modules/{name}.py` (19 files)
3. **External API clients** → `enrichment/{platform}.py` (10 files)
4. **Shared services** → `services/{category}.py` (4 files)
5. **Configuration & models** → `config.py`, `models.py`
6. **Entry points** → `main.py`, `cli.py`

**Layering**:
- HTTP/CLI → main.py, cli.py
- Pipeline execution → pipeline/runner.py
- Module discovery → pipeline/modules/__init__.py
- Module logic → pipeline/modules/{name}.py
- External APIs → enrichment/{platform}.py
- Shared utilities → services/{category}.py

**Naming convention**: `lowercase_snake_case` for files and functions; `PascalCase` for classes.
