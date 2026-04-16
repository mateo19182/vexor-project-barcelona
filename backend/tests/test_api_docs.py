"""Endpoint schema validation tests.

Validates that all API endpoints return the documented shapes,
the OpenAPI schema is complete, and the dark-themed Swagger UI loads.
No external API calls are made.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MINIMAL_CASE = {
    "case_id": "TEST-001",
    "signals": [
        {"kind": "name", "value": "Test User", "source": "test", "confidence": 1.0}
    ],
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data == {"status": "ok"}


def test_modules_schema():
    r = client.get("/modules")
    assert r.status_code == 200
    data = r.json()
    assert "modules" in data
    modules = data["modules"]
    assert len(modules) >= 20, f"Expected >= 20 modules, got {len(modules)}"
    for m in modules:
        assert "name" in m, f"Module missing 'name': {m}"
        assert "requires" in m, f"Module missing 'requires': {m}"
        assert isinstance(m["requires"], list)


def test_openapi_schema_has_tags():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "tags" in schema
    assert len(schema["tags"]) >= 4, f"Expected >= 4 tags, got {len(schema['tags'])}"
    assert schema["info"]["version"] == "1.0.0"

    paths = schema["paths"]
    expected_paths = [
        "/health",
        "/modules",
        "/enrich",
        "/enrich/stream",
        "/enrich/{module_name}",
        "/cases",
        "/cases/{case_id}/runs/{filename}",
        "/enrich-csv",
    ]
    for p in expected_paths:
        assert p in paths, f"Missing path in OpenAPI schema: {p}"


def test_docs_dark_theme():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "#09090B" in body, "Dark background color not found"
    assert "swagger-ui" in body, "Swagger UI container not found"
    assert "Inter" in body, "Inter font not found"


def test_cases_schema():
    r = client.get("/cases")
    assert r.status_code == 200
    data = r.json()
    assert "cases" in data
    assert isinstance(data["cases"], list)
    for case in data["cases"]:
        assert "case_id" in case
        assert "runs" in case


def test_enrich_missing_body():
    r = client.post("/enrich")
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"


def test_enrich_single_unknown_module():
    r = client.post("/enrich/nonexistent_module", json=MINIMAL_CASE)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"


def test_enrich_csv_no_file():
    r = client.post("/enrich-csv")
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"
