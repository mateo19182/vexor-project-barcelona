# Module docs

One file per module/component in the pipeline.

## Infrastructure

| File | Path | Role |
|---|---|---|
| [base.md](base.md) | `app/pipeline/base.py` | Core abstractions: `Context`, `ModuleResult`, `Module` protocol |
| [runner.md](runner.md) | `app/pipeline/runner.py` | Wave-based scheduler, ctx_patch merge, error handling |
| [audit.md](audit.md) | `app/pipeline/audit.py` | Structured event log + CLI summary renderer |
| [synthesis.md](synthesis.md) | `app/pipeline/synthesis.py` | Aggregation + dedup into final `Dossier` |
| [platform_check.md](platform_check.md) | `app/enrichment/platform_check.py` | Shared upstream VM protocol for registration checks |

## Modules

| File | Module | requires | Role |
|---|---|---|---|
| [osint_web.md](osint_web.md) | `osint_web` | `name` | Claude-powered web OSINT — social links, employer, location |
| [boe.md](boe.md) | `boe` | `name` | BOE (Spain official gazette) — legal notices, bankruptcy, embargos |
| [borme.md](borme.md) | `borme` | `name` | BORME (Spain commercial registry) — directorships, dissolutions |
| [breach_scout.md](breach_scout.md) | `breach_scout` | `email` | Breach intelligence — contact discovery & risk flags |
| [nosint.md](nosint.md) | `nosint` | `email` | NoSINT / CSINT — 30+ module email lookup, platform hits & breach flags |
| [xon.md](xon.md) | `xon` | `email` | XposedOrNot — breach lookup, registered services |
| [github_check.md](github_check.md) | `github_check` | `email` | Platform-check VM: GitHub registration |
| [platform_check.md](platform_check.md) | `instagram_check` | `email` | Platform-check VM: Instagram registration |
| [platform_check.md](platform_check.md) | `twitter_check` | `email` | Platform-check VM: Twitter/X registration |
| [platform_check.md](platform_check.md) | `icloud_check` | `email` | Platform-check VM: iCloud registration |
| [image_search.md](image_search.md) | `image_search` | `instagram_handle` | Reverse image OSINT via Google Lens |
| [instagram.md](instagram.md) | `instagram` | `instagram_handle` | Instagram OSINT — posts, captions, location tags |
| [linkedin.md](linkedin.md) | `linkedin` | `linkedin_url` | LinkedIn profile — headline, employer, location, positions |
| [twitter.md](twitter.md) | `twitter` | `twitter_handle` | Twitter/X — bio, location, timeline keyword scan |
| [google_maps_reviews.md](google_maps_reviews.md) | `google_maps_reviews` | `gaia_id` | Google Maps review history — lifestyle signals |
| [property.md](property.md) | `property` | `address` | Spanish real-estate valuation (Catastro + MITMA + SERPAVI) |

## Wave ordering

```
Wave 1 (always run — case seed provides name/email):
  osint_web, boe, borme, breach_scout, nosint, xon,
  github_check, instagram_check, twitter_check, icloud_check

Wave 2+ (unblocked by wave-1 ctx_patches):
  instagram          ← instagram_handle promoted by osint_web
  image_search       ← instagram_handle promoted by osint_web
  linkedin           ← linkedin_url promoted by osint_web
  twitter     ← twitter_handle promoted by osint_web
  google_maps_reviews ← gaia_id from case input
  property           ← address promoted by case or osint_web

Post:
  synthesis          (runs after all waves complete)
```
