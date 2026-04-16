# Testing

This document describes the testing practices, framework, coverage, and patterns used in the Nordés codebase.

## Test Framework & Setup

### Framework

- **Test runner:** `pytest` (installed in dev dependencies)
- **Async support:** `pytest-asyncio` (required for `@pytest.mark.asyncio`)
- **Mocking:** `unittest.mock` (built-in; AsyncMock, patch)
- **No configuration file:** `pytest.ini` or `pyproject.toml` pytest settings not explicitly configured in the checked-in files; relies on pytest defaults

### Running Tests

```bash
cd backend
uv sync
pytest tests/
```

## Current Test Coverage

### Existing Tests

Located in `backend/tests/`:

1. **`test_module_property.py`** (474 lines)
   - Comprehensive test suite for `app/pipeline/modules/property.py`
   - Tests module protocol compliance, skip cases, full flow with mocks, numeric estimations, signals/facts, graceful degradation
   - Uses patches for: geocoding, Catastro queries, MITMA/SERPAVI data
   - Covers ~12 test classes with ~40+ test methods

2. **`test_services_catastro.py`**
   - Unit tests for `app/services/catastro.py` (pure functions like `parse_tipo_via`)
   - Parametrized tests with real-world examples (Spanish addresses, catalán, gallego variants)
   - No mocking; tests pure string parsing logic

3. **`test_services_mitma.py`**
   - Tests for MITMA (Spanish housing market data) service
   - Limited test count; likely integration-style with real/mock API data

4. **`test_services_serpavi.py`**
   - Tests for SERPAVI (rental market data) service
   - Similar pattern to MITMA tests

### Test Statistics

- **Total test files:** 4 (excluding venv)
- **Primary focus:** Property module (property valuation) — most comprehensive
- **Coverage areas:** Module protocol, configuration skipping, network mocks, numeric accuracy, signal emission, graceful degradation
- **Untested areas:** Most other modules (linkedin, instagram, twitter, etc.) have no tests

## Testing Patterns

### Async Test Pattern

All tests that call async functions use the `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_ok_status_with_valid_address(self):
    with (
        patch(
            "app.pipeline.modules.property.geocoding.geocode_best_effort",
            new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
        ),
        # ... more patches
    ):
        ctx = _make_ctx()
        result = await PropertyModule().run(ctx)

    assert result.status == "ok"
```

**Key points:**
- Fixtures are created inline (e.g., `_make_ctx()`)
- Multiple patches use context manager nesting (`with (patch(...), patch(...)):`)
- Assertions are outside the patch context (clean after execution)

### Mocking Pattern

```python
with patch(
    "app.pipeline.modules.property.geocoding.geocode_best_effort",
    new=AsyncMock(return_value=(MOCK_GEO_HIT, "nominatim")),
):
    # test code
```

**Pattern:**
- Full import path to the function being patched (module-qualified)
- `AsyncMock` for async functions, regular `Mock` for sync
- `return_value` for normal returns, `side_effect` for exceptions

### Parametrized Tests

Used in `test_services_catastro.py` for testing parsing logic with multiple inputs:

```python
@pytest.mark.parametrize("road, expected_tipo, expected_nombre_contains", [
    ("Calle Gran Vía",         "CL", "GRAN VÍA"),
    ("Avenida Diagonal",       "AV", "DIAGONAL"),
    # ... more test cases
])
def test_parse_tipo_via(road, expected_tipo, expected_nombre_contains):
    tipo, nombre = parse_tipo_via(road)
    assert tipo == expected_tipo
    assert expected_nombre_contains in nombre
```

**Benefits:**
- Reduces boilerplate for testing many variants
- Data-driven; easy to add edge cases
- Output is readable (each case labeled in pytest output)

### Test Helpers

Each test file defines local helpers to reduce boilerplate:

From `test_module_property.py`:

```python
def _make_case(**kwargs) -> Case:
    defaults = dict(case_id="test-001", country="ES", debt_eur=10_000.0, ...)
    defaults.update(kwargs)
    return Case(**defaults)

def _make_ctx(address: str | None = "Calle Gran Vía 1, Madrid", **kwargs) -> Context:
    case = _make_case(address=address, **kwargs)
    return context_from_case(case)
```

**Pattern:**
- Small, focused factories with sensible defaults
- Override only what the test cares about
- Keeps test code concise and readable

### Mock Data

Constants defined at module level:

```python
MOCK_GEO_HIT = {
    "lat": "40.4168",
    "lon": "-3.7038",
    "display_name": "Gran Vía, Madrid, Comunidad de Madrid, España",
    # ...
}

MOCK_INMUEBLE = {
    "tipoBien": "UR",
    "referenciaCatastral": {"referenciaCatastral": "0847106VK4704F0006FI"},
    # ...
}
```

**Pattern:**
- Reusable across multiple test methods
- Realistic structure (matches real API payloads)
- Comments explaining what each mock represents

### Test Organization

Tests are organized into classes by concern:

```python
class TestModuleProtocol:
    def test_has_name(self): ...

class TestSkipCases:
    @pytest.mark.asyncio
    async def test_skips_non_es_country(self): ...

class TestFullFlowMocked:
    """MITMA y SERPAVI usan JSON real. Catastro y geocoding están mockeados."""
    @pytest.mark.asyncio
    async def test_ok_status_with_valid_address(self): ...

class TestEstimations:
    @pytest.mark.asyncio
    async def test_sale_estimate_present_when_sqm_known(self): ...
```

**Grouping:**
- Protocol compliance
- Skip/skip-graceful cases
- Full happy path with mocks
- Numeric accuracy of estimations
- Signal/fact emission
- Error handling and degradation

## Test Assertions

Common assertion patterns:

```python
# Status checks
assert result.status == "ok"
assert result.name == "property"

# Structure checks
assert isinstance(result, ModuleResult)
assert isinstance(result.signals, list)

# Presence checks
assert len(result.signals) >= 1
assert "asset" in {s.kind for s in result.signals}

# Numeric precision (pytest.approx)
assert est["venta_total_eur_low"] == pytest.approx(90 * 5286.2 * 0.80, rel=0.01)

# String checks
assert any("ES" in g for g in result.gaps)
assert "0847106VK4704F0006FI" in all_claims

# Range checks
assert 0.0 <= sig.confidence <= 1.0
```

## What's NOT Tested

The following areas have **no test coverage**:

### Modules

- `instagram.py` — No tests
- `linkedin.py` — No tests
- `twitter.py` — No tests
- `wallapop.py` — No tests
- `gaia_enrichment.py` — No tests
- `jooble.py` — No tests
- `breach_scout.py` — No tests
- `icloud_check.py` — No tests
- `instagram_check.py` — No tests
- `image_search.py` — No tests
- `xon.py` — No tests
- `boe.py` — No tests
- `nosint.py` — No tests

### Core Pipeline

- `runner.py` — Wave-based scheduling, caching, signal accumulation — **untested**
- `synthesis.py` — Dossier deduplication and aggregation — **untested**
- `audit.py` — Event logging and formatting — **untested**
- `cache.py` — Caching logic — **untested**
- `llm_summary.py` — LLM summary generation — **untested**

### API & Orchestration

- `main.py` — FastAPI routes and orchestration — **untested**
- Integration tests for the `/enrich` and `/enrich/{module_name}` endpoints — **none**

### Enrichment Layer

- Individual enrichment functions in `app/enrichment/` — mostly **untested**
- Examples: `enrich_linkedin()`, `enrich_instagram()`, `fetch_gaia()`, `search_wallapop()`, etc.

## Why Limited Coverage

1. **Hackathon time constraint:** 24-hour project; focus on working end-to-end over comprehensive testing
2. **External dependencies:** Many tests would require mocking complex APIs (Instagram, LinkedIn, Google, etc.); high effort for 24h
3. **Property module prioritized:** Most complex numerical logic; highest ROI on test investment
4. **Manual testing:** CLI and API integration likely tested manually during hackathon

## Test Dependencies

From `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "ruff>=0.6",
]
```

**Note:** `pytest` and `pytest-asyncio` are **NOT** listed in dev dependencies, but they're used in test files. This suggests:
- They may be installed separately in the test environment
- Or tests are run in an environment with `uv sync` (which installs all direct deps, not just listed ones)
- This is an oversight in `pyproject.toml` — testing dependencies should be explicitly listed

## Recommendations for Expanding Tests

### High Priority

1. **Core pipeline (`runner.py`)** — Add tests for:
   - Wave scheduling and concurrency
   - Signal accumulation across waves
   - Dependency resolution
   - Cache hit/miss scenarios
   - Error isolation (one bad module doesn't poison the pipeline)

2. **Synthesis (`synthesis.py`)** — Add tests for:
   - Signal deduplication (case-insensitive, trim-insensitive)
   - Confidence picking (highest wins in dedup)
   - Dossier assembly from multiple modules

3. **API integration (`main.py`)** — Add tests for:
   - `/enrich` POST endpoint with various Cases
   - `fresh` parameter variants
   - `only` parameter filtering
   - Error handling (unknown module, invalid Case)

### Medium Priority

4. **Audit logging (`audit.py`)** — Add tests for:
   - Event recording and elapsed_s tracking
   - Streaming format correctness
   - Summary rendering

5. **LinkedIn module (`linkedin.py`)** — Add tests for:
   - LinkdAPI response parsing
   - Signal emission accuracy
   - Graceful handling of missing data

6. **Instagram module (`instagram.py`)** — Add tests for:
   - Integration with `enrich_instagram()`
   - Raw data in ModuleResult

### Lower Priority

7. **Jooble, Twitter, Wallapop, etc.** — Similar pattern to LinkedIn/Instagram

## Test Infrastructure Notes

### No CI/CD Configuration

- No `.github/workflows/` or similar CI pipeline
- No automated test execution on commits
- Tests must be run locally by developers

### Pytest Plugins Needed

For the existing tests to run, the test environment must have:
- `pytest`
- `pytest-asyncio`

These should be added to `pyproject.toml` under `[dependency-groups] dev = [...]`

### Example: Installing Test Dependencies

```bash
cd backend
uv add --group dev pytest pytest-asyncio
uv sync
pytest tests/
```

## Debugging Tests

### Verbose Output

```bash
pytest tests/ -v  # verbose: show each test name
pytest tests/ -vv  # extra verbose: show test parameters
```

### Capture Output

```bash
pytest tests/ -s  # show stdout/stderr during tests
```

### Single Test

```bash
pytest tests/test_module_property.py::TestModuleProtocol::test_has_name -v
```

### Specific Parametrized Case

```bash
pytest tests/test_services_catastro.py::test_parse_tipo_via[Calle\ Gran\ Vía-CL-GRAN\ VÍA] -v
```

## Summary

- **Coverage:** Property module well-tested; rest of system untested
- **Framework:** pytest + pytest-asyncio
- **Patterns:** Async tests, patch mocking, parametrized tests, test helpers, mock data constants
- **Gap:** No integration tests, no API endpoint tests, no CLI tests
- **Recommendation:** Expand core pipeline and API tests before expanding module coverage

**Test files to review:**
- `backend/tests/test_module_property.py` — most comprehensive example
- `backend/tests/test_services_catastro.py` — parametrized unit tests
- `backend/tests/test_services_mitma.py` — integration-style tests
- `backend/tests/test_services_serpavi.py` — similar to MITMA
