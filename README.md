# Vexor × Project Barcelona

AI enrichment pipeline for debtor cases. Takes a minimal case record and returns a sourced dossier a human collector can act on immediately.

## What it does

A debt servicer starts with almost nothing: a name, a country, a debt amount, and a string of failed call attempts. This pipeline takes that sparse record and fans out across multiple OSINT sources in parallel, then synthesizes the findings into a single collector-ready dossier.

**Pipeline modules** (run in dependency-ordered waves, concurrently within each wave)

Each module emits typed `Signal` objects (location, employer, asset, lifestyle, risk_flag, etc.) with a `source` URL and a `confidence` score. A final synthesis step merges all module outputs into a `Dossier`, and an LLM produces a prose summary with key facts.

- Every claim carries its source. Nothing is fabricated.
- If a module finds nothing, it says so explicitly — gaps are first-class output.
- Module results are cached per case; rerunning skips live calls unless `--fresh` is passed.

## Setup

```bash
cd backend
cp .env.example .env   # fill in API keys (see below)
uv sync
```

## Run

**API server:**
```bash
cd backend
uv run uvicorn app.main:app
```

**CLI**
```bash
cd backend
uv run enrich ../samples/geohotz.json
```

## Enrich via API

```bash
curl -s -X POST http://localhost:8000/enrich \
  -H 'Content-Type: application/json' \
  -d @samples/geohotz.json
```

## Audit logs

Every run is persisted to `backend/logs/{case_id}/{timestamp}.json`. To tail the live audit stream during a CLI run:

```bash
uv run enrich case.json 2>&1 1>/dev/null   # stderr only (audit)
uv run enrich case.json 2>/dev/null         # stdout only (JSON result)
```
