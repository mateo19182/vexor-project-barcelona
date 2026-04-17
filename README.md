# Vexor × Project Barcelona

AI enrichment pipeline for debtor cases. Takes a minimal case record and returns a sourced dossier a human collector can act on immediately.

<img width="2140" height="1366" alt="pic" src="https://github.com/user-attachments/assets/971f6653-577b-4be2-88ba-cf3853d99849" />

## What it does

A debt servicer starts with almost nothing: a name, a country, a debt amount, and a string of failed call attempts. This pipeline fans out across 23 OSINT modules, then synthesizes everything into a collector-ready dossier where every claim links back to its source.

## How the pipeline works

### Signals: the single data currency

All structured data flows through **Signals** — typed observations with provenance:

```
Signal(kind, tag, value, source, confidence, notes)
```

`kind` is one of: `name`, `address`, `location`, `employer`, `role`, `business`, `asset`, `lifestyle`, `contact`, `affiliation`, `risk_flag`. `tag` disambiguates within a kind (e.g. `contact:email`, `contact:linkedin`, `contact:instagram`). `value` is short and canonical ("Barcelona, ES", "Acme Corp" — not a sentence). Every signal carries a `source` URL and a `confidence` from 0 to 1.

Signals accumulate on a shared **Context** blackboard as modules complete. Any module can query what prior modules found via `ctx.best("employer")` or `ctx.all("contact", "email")`.

### Wave-based scheduling

Modules declare what signals they need to run — not which modules they depend on. The runner groups them into waves:

```
Case input seeds Context with initial signals (name, email, phone, etc.)
        │
        ▼
  ┌─ Wave 1 ──► modules whose requires are already satisfied
  │                 (run concurrently via asyncio.gather)
  │                 signals + social_links merged into Context
  │
  ├─ Wave 2 ──► modules newly unblocked by wave-1 signals
  │                 (same: concurrent run, merge)
  │
  ├─ Wave 3+ ─► ...repeat until nothing new unlocks
  │
  └─► Synthesis ──► Dossier ──► LLM Summary ──► EnrichmentResponse
```

If a module's requirements are never met, it ends as `skipped` with an explicit gap explaining what was missing.

### Structured (machine-consumed)

| Field | Description |
|---|---|
| `signals` | Typed observations — deduplicated by `(kind, tag, value)` in synthesis, highest confidence wins |
| `facts` | Free-text claims with source and confidence — for things that don't fit a signal kind |
| `summary` | Prose description of what the module found |
| `gaps` | What couldn't be verified and why |
| `raw` | Debug exhaust (API response counts, error traces) |

### Final response

Synthesis merges all module results into a **Dossier** (deduped signals, concatenated facts and gaps), then an LLM (Claude Sonnet) produces a structured briefing:

- **Executive brief** — who is this person, what the debt looks like, key findings (readable in 10 seconds)
- **Approach context** — lifestyle/economic signals and conversational entry points
- **Key facts** — sourced bullet points
- **Unanswered questions** — what the pipeline couldn't find
- **Confidence level** — high / moderate / low

The `EnrichmentResponse` bundles: the raw dossier, an enriched dossier (structured for a collector dashboard), the LLM summary, per-module results, lead verification, and a full audit log.

## Setup

```bash
cd backend
cp .env.example .env   # fill in API keys
uv sync
```

## Run

**API server:**
```bash
cd backend
uv run uvicorn app.main:app
```

**CLI:**
```bash
cd backend
uv run enrich ../samples/geohotz.json
```

**Single module:**
```bash
echo '{"case_id":"test","email":"user@example.com"}' | uv run enrich - --only nosint --fresh nosint
```

**API call:**
```bash
curl -s -X POST http://localhost:8000/enrich \
  -H 'Content-Type: application/json' \
  -d @samples/geohotz.json
```

## Caching

Module results are cached to `backend/logs/{case_id}/cache/{module_name}.json`. Cached signals are still accumulated on Context so downstream modules see the same state.

```bash
uv run enrich case.json --fresh            # bypass all caches
uv run enrich case.json --fresh nosint     # bypass specific module
```

## Audit logs

Every run persists the full `EnrichmentResponse` to `backend/logs/{case_id}/{timestamp}.json`.

```bash
uv run enrich case.json 2>&1 1>/dev/null   # stderr only (live audit stream)
uv run enrich case.json 2>/dev/null         # stdout only (JSON result)
```
