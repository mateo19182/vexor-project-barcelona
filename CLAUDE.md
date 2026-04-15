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

## Conventions
- Keep it small. This is a 24h hackathon — favor working end-to-end over layered abstractions.
- Every enrichment claim must carry its source. No hallucinated facts.
- If we find nothing, say so explicitly — don't fabricate.
