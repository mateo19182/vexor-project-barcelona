# Code Conventions

This document describes the code style, naming patterns, and architectural conventions used across the Nordés codebase.

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
  ```python
  def best(self, kind: str, tag: str | None = None) -> Signal | None:
  def all(self, kind: str, tag: str | None = None) -> list[Signal]:
  async def run(self, ctx: Context) -> ModuleResult: ...
  ```

### Docstrings

- **Module-level docstrings:** Every `.py` file has a docstring at the top explaining purpose
- **Class/method docstrings:** Used selectively for complex logic or API surfaces
- **Format:** Prose with examples, not strict Google/NumPy format
- Example from `base.py`:
  ```python
  """Core abstractions for the enrichment pipeline.

  Design in one sentence: each module declares what signal (kind, tag) pairs it
  needs; the runner figures out what can run in parallel based on those
  declarations. All structured data flows through signals — no separate identity
  fields, no ContextPatch.
  """
  ```

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
  - Primary kinds: `name`, `address`, `location`, `employer`, `role`, `business`, `asset`, `lifestyle`, `contact`, `affiliation`, `risk_flag`
  - Lowercase, single-word or underscore-separated: `risk_flag`, `asset`
- **Signal tags:** Used to disambiguate within a kind (e.g., `contact:linkedin`, `contact:instagram`)
- **Source URLs:** Every Signal must have a full URL or reference backing the observation

## Architectural Patterns

### Module Structure

Every enrichment module follows this protocol (defined in `base.py`):

```python
class <Name>Module:
    name: str = "module_name"
    requires: tuple[tuple[str, str | None], ...] = (("kind", "tag"), ...)
    
    async def run(self, ctx: Context) -> ModuleResult: ...
```

**Key patterns:**
- Class attributes `name` and `requires` are **required** (not in `__init__`)
- `run()` is always **async** even if it doesn't use await
- Always returns a `ModuleResult` (never raises; exceptions are caught by the runner)
- `requires` is a tuple of `(kind, tag)` pairs; runner gates scheduling based on these

**Example from `linkedin.py`:**
```python
class LinkedInModule:
    name = "linkedin"
    requires: tuple[tuple[str, str | None], ...] = (("contact", "linkedin"),)

    async def run(self, ctx: Context) -> ModuleResult:
        # ... implementation
        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary_line,
            facts=facts,
            signals=signals,
            gaps=gaps,
            raw=data,
        )
```

### Signals & Context Flow

- **Context** (`base.py`): Mutable blackboard passed through the pipeline
  - Contains the original `Case` + accumulated `signals` (list)
  - Methods: `best(kind, tag)`, `all(kind, tag)`, `has(kind, tag)`
  - Modules read prior findings via these helpers; runner gates scheduling based on `requires`
- **Signals**: Structured, provenance-tagged observations
  - Every Signal must have: `kind`, `value`, `source`, `confidence`, optionally `tag` and `notes`
  - `value`: Short canonical form (e.g., "Barcelona, ES", "Acme Corp")
  - `source`: Full URL or reference — **no hallucinated facts**
  - `confidence`: Float 0.0–1.0
- **Facts**: Free-text claims with source (use when observation doesn't fit a `SignalKind`)
- **SocialLinks**: Converted to `contact` signals by the runner during synthesis

### Wave-Based Scheduling

- **Pipeline runner** (`runner.py`): Orchestrates parallel execution via waves
  - Each wave: finds modules with all `requires` met → runs concurrently via `asyncio.gather()`
  - After each wave: signals accumulated, social_links converted to contact signals
  - If no module is ready but work remains: emit skipped with explicit gaps
  - If a module raises: caught and emitted as `status="error"` with exception in gaps
  - One bad module never poisons the pipeline

**Key runner functions:**
- `_missing_requirements(ctx, module)` → list of unmet (kind, tag) pairs
- `_social_links_to_signals(links)` → convert SocialLinks to contact Signals (confidence floor: 0.6)
- `_accumulate_signals(ctx, result)` → append module's signals + converted social_links
- `run_pipeline(ctx, modules, audit, ...)` → orchestrates the full wave-based execution

### Error Handling & Graceful Degradation

- **No exceptions escape modules:** Every module returns a `ModuleResult` with `status` in `["ok", "skipped", "error"]`
- **Gaps instead of failures:** When a module can't produce data, it adds entries to `gaps[]` (human-readable explanations)
  - Example from `linkedin.py`: `gaps=["linkedin: LINKDAPI_API_KEY not configured — skipping"]`
  - Example from `runner.py`: `gaps=[f"skipped: missing inputs [{', '.join(missing)}]"]`
- **Configuration-based skipping:** Modules check for required API keys/env vars and self-skip gracefully
  ```python
  if not settings.linkdapi_api_key:
      return ModuleResult(
          name=self.name,
          status="skipped",
          gaps=["linkedin: LINKDAPI_API_KEY not configured — skipping"],
      )
  ```
- **No silent failures:** Every "nothing happened" scenario documents itself in `gaps`

### Result Caching

- **Cache location:** `{logs_dir}/{case_id}/cache/{module_name}.json`
- **Cache policy:**
  - Only `"ok"` and `"no_data"` results are cached
  - `"error"` and `"skipped"` never cached (triggers retry on next run)
  - On cache hit: module's signals still accumulated (context unchanged vs. live run)
- **Invalidation:**
  - `fresh=True` in runner → skip all caches
  - `fresh={"module_a", "module_b"}` → skip only named modules
  - Manual: delete cache file to force recompute

### Async Patterns

- **All I/O is async:** HTTP calls, subprocess launches, and other I/O use async/await
- **Blocking code in executors:** CPU-intensive or legacy sync code (e.g., Jooble HTTP in `jooble.py`) runs in `asyncio.get_event_loop().run_in_executor()`
- **No blocking in the hot path:** Main pipeline threads never block waiting for sync I/O

## Data Models

### Pydantic Models

All structured data uses Pydantic (`pydantic>=2.8`):
- **Case**: Input debtor profile (minimal)
- **Signal**: Structured observation (kind, value, source, confidence, tag, notes)
- **Fact**: Free-text claim with source
- **SocialLink**: Social media profile (platform, url, handle, confidence)
- **ModuleResult**: Standard return shape for every module
- **Dossier**: Synthesized final view (summary, facts, signals, gaps)
- **LlmSummary**: LLM-generated summary for downstream consumers
- **AuditEvent & EnrichmentResponse**: Pipeline telemetry

**Validation:**
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
  - `from app.config import settings`
  - `from app.pipeline.base import Context, ModuleResult`
  - `from app.models import Signal, Fact, Case`
- **No relative imports:** Never use `from . import` or `from .. import`
- **Grouping order** (implicit):
  1. Standard library (`asyncio`, `sys`, `json`, `time`, etc.)
  2. Third-party (`pydantic`, `httpx`, `fastapi`, `anthropic`, etc.)
  3. Local `app` imports

## Logging & Debugging

- **Stderr for live output:** `print(..., file=sys.stderr, flush=True)` for progress/debug output
- **No logging library:** Uses direct `print` to stderr; captured in audit logs and run logs
- **Private log helper:** `_log(msg)` in many modules for consistency
- **Structured audit events:** Pipeline orchestration emits `AuditEvent` objects (kind, elapsed_s, module, message, detail)
  - Events travel with the response; both streamed to stderr and persisted to JSON logs

## File Organization

- `backend/app/`:
  - `main.py` — FastAPI app + HTTP routes
  - `models.py` — Pydantic data models
  - `config.py` — Settings (env-based)
  - `pipeline/`:
    - `base.py` — Core abstractions (Context, Module protocol, ModuleResult)
    - `runner.py` — Wave-based scheduler
    - `audit.py` — Event logging
    - `cache.py` — Result caching
    - `synthesis.py` — Final dossier aggregation
    - `llm_summary.py` — LLM-generated summary
    - `modules/` — Individual enrichment modules
  - `enrichment/` — Low-level enrichment logic (API calls, parsing, etc.)

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
