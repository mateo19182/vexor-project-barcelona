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

## Data model: two types

All data is either **structured** (Signal) or **unstructured** (Fact / context).

### Signal — the single structured type
`Signal(kind, value, source, confidence, notes?)`. Kinds: `location`, `employer`, `role`, `business`, `asset`, `lifestyle`, `contact`, `affiliation`, `risk_flag`. Value should be short and canonical (e.g. `"Barcelona, ES"`, `"Acme Corp"` — not a sentence). Extra detail goes in `notes`.

Signals **accumulate on `ctx.signals`** as modules complete. Any downstream module can read prior modules' findings via `ctx.best_signals("employer")` etc.

### Fact — unstructured claims
`Fact(claim, source, confidence)`. Free-text claims that don't fit any `SignalKind`. Use sparingly; prefer signals when the data fits a kind.

### Case input
Three kinds of input:

1. **Identity fields** — `name`, `email`, `phone`, `address`, `instagram_handle`, `twitter_handle`, `google_id`. Gate which modules can run via `requires`.
2. **Known signals** — `known_signals: list[Signal]`. Pre-seed the pipeline with structured observations (e.g. known employer). Injected into `ctx.signals` before wave 1.
3. **Unstructured context** — `context: str`. Free-form caller notes passed to the LLM summary and osint_web. Not parsed.

### Module output → ModuleResult
- `signals` — structured observations (accumulated on Context by the runner).
- `facts` — free-text claims.
- `social_links` — discovered profiles: `(platform, url, handle?, confidence)`.
- `ctx_patch` — explicit identity-field writes (only for handle/URL/email — not signals).
- `summary`, `gaps`, `raw` — prose, known unknowns, debug dump.

### How data flows between modules

1. **Signals accumulate on Context.** After each module, the runner appends `result.signals` to `ctx.signals`. Any later module can query them.
2. **Social links auto-promote to identity fields.** The runner promotes the best LinkedIn/Instagram/Twitter links (conf >= 0.6) to `ctx.linkedin_url` / `ctx.instagram_handle` / `ctx.twitter_handle`, unlocking downstream modules automatically.
3. **Identity provenance is multi-value.** `ctx.identity_provenance["email"]` is a `list[AttributedValue]` — every proposal is kept, not just the winner. The primary `ctx.email` field holds the highest-confidence value (for module gating).

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
