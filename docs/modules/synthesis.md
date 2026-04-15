# synthesis — Final synthesis pass

`backend/app/pipeline/synthesis.py`

## Overview

Aggregates every module's output into a single `Dossier` after all waves complete.

```python
async def synthesize(ctx: Context, results: list[ModuleResult]) -> Dossier
```

## Current behavior (stub)

1. Collects all `facts` from every module result.
2. Collects all `signals` and deduplicates them by `(kind, value)` — case/trim insensitive, keeping the highest-confidence copy.
3. Collects all `gaps`.
4. Stitches per-module summaries (from `status="ok"` modules) into a single space-joined summary. Falls back to `"No enrichment data recovered for case {id}."` if nothing succeeded.

## Signal deduplication

`_dedupe_signals` keeps one entry per `(kind, value)` pair, picking the highest confidence. This collapses cases like `osint_web` and `instagram` both reporting the same location with slightly different confidence scores.
