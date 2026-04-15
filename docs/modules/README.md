# Module docs

One file per module/component in the pipeline.

| File | Path | Role |
|---|---|---|
| [base.md](base.md) | `app/pipeline/base.py` | Core abstractions: `Context`, `ModuleResult`, `Module` protocol |
| [runner.md](runner.md) | `app/pipeline/runner.py` | Wave-based scheduler, ctx_patch merge, error handling |
| [osint_web.md](osint_web.md) | `app/pipeline/modules/osint_web.py` | Claude-powered web OSINT (wave 1) |
| [instagram.md](instagram.md) | `app/pipeline/modules/instagram.py` | Instagram OSINT adapter (wave 2+) |
| [audit.md](audit.md) | `app/pipeline/audit.py` | Structured event log + CLI summary renderer |
| [synthesis.md](synthesis.md) | `app/pipeline/synthesis.py` | Aggregation + dedup into final `Dossier` |

## Wave ordering

```
Wave 1:  osint_web          (requires: name — always set)
Wave 2:  instagram          (requires: instagram_handle — may be promoted by osint_web)
Post:    synthesis           (runs after all waves complete)
```
