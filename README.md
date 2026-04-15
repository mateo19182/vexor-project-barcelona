# Vexor × Project Barcelona

AI enrichment pipeline for debtor cases. Takes a minimal case and returns actionable signals with traceable sources.

## Setup

```bash
cd backend
cp .env.example .env   # fill in API keys (see below)
uv sync
```

**Required keys** (`.env`):

| Key | Required for |
|-----|-------------|
| `ANTHROPIC_API_KEY` | Web OSINT module (Claude) |
| `OPENROUTER_API_KEY` | vision analysis |
| `HIKERAPI_TOKEN` | Instagram data fetching |

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

## Modules

| Module | Requires | Wave | Data source |
|--------|----------|------|-------------|
| `osint_web` | `name` | 1 | Claude web search + fetch |
| `xon` | `email` | 1 | XposedOrNot — breach & registration history |
| `instagram` | `instagram_handle` | 2 | Osintgram (handle may be found by wave 1) |

**Wave 1** modules run in parallel. `instagram` waits for wave 1 to finish since `osint_web` may discover the handle from the name.

## Audit logs

Every run is persisted to `backend/logs/{case_id}/{timestamp}.json`. To tail the live audit stream during a CLI run:

```bash
uv run enrich case.json 2>&1 1>/dev/null   # stderr only (audit)
uv run enrich case.json 2>/dev/null         # stdout only (JSON result)
```
