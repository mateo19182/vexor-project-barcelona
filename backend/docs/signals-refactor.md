# Signals refactor — unified data model

## Problem

The pipeline has two parallel systems for the same thing:

1. **Identity fields** — `ctx.email`, `ctx.instagram_handle`, etc. Fixed set of 8
   string fields on Context. Modules read them directly, write them via
   `ContextPatch`, and the runner gates scheduling via `requires`.

2. **Signals** — `Signal(kind, value, source, confidence)`. Open-ended typed
   observations that accumulate on `ctx.signals`. Modules emit them in
   `ModuleResult.signals`.

An email *is* a contact signal. A location *is* a location signal. An instagram
handle *is* a contact signal. The identity fields are just signals with a
gating side-effect — but they have their own model (`ContextPatch`), their own
merge logic (`_apply_patch`), their own provenance store
(`identity_provenance`), and their own auto-promotion path
(`_auto_promote_social_links`). That's three systems doing one job.

## Design: everything is a signal

### Signal gets a `tag` field

```python
class Signal(BaseModel):
    kind: SignalKind          # "contact", "location", "employer", ...
    value: str                # "maria@gmail.com", "Barcelona, ES", ...
    source: str               # URL or reference
    confidence: float         # 0.0–1.0
    notes: str | None = None
    tag: str | None = None    # NEW — sub-kind qualifier
```

`tag` distinguishes signals within a kind:
- `Signal(kind="contact", tag="email", value="maria@gmail.com", ...)`
- `Signal(kind="contact", tag="instagram", value="maria_lopez", ...)`
- `Signal(kind="contact", tag="twitter", value="marialop", ...)`
- `Signal(kind="contact", tag="phone", value="+34612345678", ...)`
- `Signal(kind="contact", tag="linkedin", value="https://linkedin.com/in/maria", ...)`
- `Signal(kind="location", value="Barcelona, ES", ...)`  — tag optional
- `Signal(kind="employer", value="Acme Corp", ...)`

`tag` is optional. Most signal kinds don't need it — `employer`, `location`,
`role`, `lifestyle`, `asset`, `risk_flag` are fine without. `contact` uses it
to distinguish email vs phone vs handle.

### Multiple values are natural

Since signals are a list, multiple values for the same kind+tag just
coexist:

```python
ctx.signals = [
    Signal(kind="contact", tag="email", value="maria@gmail.com",  source="case_input", confidence=1.0),
    Signal(kind="contact", tag="email", value="m.lopez@work.com", source="nosint.org",  confidence=0.8),
    Signal(kind="contact", tag="email", value="mlop99@yahoo.es",  source="breach_db",   confidence=0.6),
]

ctx.all("contact", "email")   # → all 3, sorted by confidence desc
ctx.best("contact", "email")  # → the gmail one (conf 1.0)
```

No merge logic, no overwrite rules. All values are kept. Consumers pick
what they need.

### Context becomes a signal store

```python
class Context(BaseModel):
    case: Case
    signals: list[Signal] = []

    def best(self, kind: str, tag: str | None = None) -> Signal | None:
        """Highest-confidence signal matching kind (and tag if given)."""
        ...

    def all(self, kind: str, tag: str | None = None) -> list[Signal]:
        """All signals matching kind+tag, sorted by confidence desc."""
        ...

    def has(self, kind: str, tag: str | None = None) -> bool:
        """True if at least one signal matches."""
        ...
```

No more `ctx.email`, `ctx.instagram_handle`, `ctx.linkedin_url`, etc. No more
`identity_provenance`. No more `ContextPatch`. Just `ctx.signals`.

### `requires` checks signals

```python
class LinkedInModule:
    name = "linkedin"
    requires = (("contact", "linkedin"),)  # (kind, tag) tuples

    async def run(self, ctx: Context) -> ModuleResult:
        url = ctx.best("contact", "linkedin").value
        ...
```

The runner checks:
```python
def _is_ready(ctx: Context, module: Module) -> bool:
    return all(ctx.has(kind, tag) for kind, tag in module.requires)
```

`requires` becomes `tuple[tuple[str, str | None], ...]` — a tuple of
`(kind, tag?)` pairs. Common patterns:
- `requires = (("contact", "email"),)` — needs an email
- `requires = (("contact", "instagram"),)` — needs an instagram handle
- `requires = (("contact", "linkedin"),)` — needs a linkedin URL
- `requires = (("name", None),)` — needs a name signal

### `name` and `address` become signal kinds

Extend `SignalKind`:
```python
SignalKind = Literal[
    "name",          # NEW — subject's name
    "address",       # NEW — physical address
    "location",
    "employer",
    "role",
    "business",
    "asset",
    "lifestyle",
    "contact",       # email, phone, handles — use tag to distinguish
    "affiliation",
    "risk_flag",
]
```

Now `requires` is uniform:
- `requires = (("name", None),)` — needs any name signal
- `requires = (("address", None),)` — needs an address
- `requires = (("contact", "email"),)` — needs an email

### Case input — all structured data is signals

```python
class Case(BaseModel):
    case_id: str

    # Debt/case metadata — not signals, just context for the LLM.
    country: str | None = None
    debt_eur: float | None = None
    debt_origin: str | None = None
    debt_age_months: int | None = None
    call_attempts: int | None = None
    call_outcome: str | None = None
    legal_asset_finding: str | None = None

    # Everything the caller knows — structured.
    signals: list[Signal] = []

    # Everything the caller knows — unstructured.
    context: str | None = None

    # Property metadata (not a signal, used by the property module directly).
    property_sqm: float | None = None
    property_typology: str | None = None
```

No more `name`, `email`, `phone`, `address`, `instagram_handle`,
`twitter_handle`, `google_id` fields on Case. All structured data about
the subject arrives as signals.

Example input JSON:
```json
{
  "case_id": "C002",
  "country": "ES",
  "debt_eur": 2077,
  "debt_origin": "personal_loan",
  "debt_age_months": 12,
  "call_attempts": 1,
  "call_outcome": "rings_out",
  "signals": [
    {"kind": "name",    "value": "Mateo Amado Ares",        "source": "case_input", "confidence": 1.0},
    {"kind": "contact", "value": "+34674527164",             "source": "case_input", "confidence": 1.0, "tag": "phone"},
    {"kind": "contact", "value": "mateoamadoares@gmail.com", "source": "case_input", "confidence": 1.0, "tag": "email"},
    {"kind": "address", "value": "A Coruña, Oleiros, Spain", "source": "case_input", "confidence": 1.0},
    {"kind": "employer","value": "Acme Corp",                "source": "case_input", "confidence": 1.0}
  ],
  "context": "Debtor mentioned having family in Málaga during the last call."
}
```

`context_from_case` just passes signals through:
```python
def context_from_case(case: Case) -> Context:
    return Context(case=case, signals=list(case.signals))
```

### ContextPatch and _apply_patch go away

Modules no longer "patch" identity fields. They return signals. The runner
appends them to `ctx.signals`. If a module discovers an email, it emits:

```python
Signal(kind="contact", tag="email", value="maria2@gmail.com",
       source="https://nosint.org", confidence=0.8)
```

No merging, no confidence-beats, no provenance tracking. All values are kept.
`ctx.best("contact", "email")` returns the highest-confidence one when a
module needs to pick.

### Social link auto-promotion simplifies

`SocialLink` stays as a convenience type in `ModuleResult` (it's useful for
the API response). But the runner converts them to signals:

```python
_PLATFORM_TO_TAG: dict[str, str] = {
    "linkedin": "linkedin",
    "instagram": "instagram",
    "twitter": "twitter",
    "x": "twitter",
    "github": "github",
    "facebook": "facebook",
    "tiktok": "tiktok",
}

def _social_links_to_signals(links: list[SocialLink]) -> list[Signal]:
    out = []
    for sl in links:
        tag = _PLATFORM_TO_TAG.get(sl.platform.lower())
        if tag:
            out.append(Signal(
                kind="contact", tag=tag,
                value=sl.handle or sl.url,
                source=sl.url,
                confidence=sl.confidence,
            ))
    return out
```

No more `_enrich_patch`, `_auto_promote_social_links`, `ContextPatch` — just
signals.

### Module access patterns

Before:
```python
# linkedin module
url = ctx.linkedin_url or ""
username = extract_username(url)
```

After:
```python
# linkedin module
url = ctx.best("contact", "linkedin").value
username = extract_username(url)
```

Before:
```python
# twitter module
handle = (ctx.twitter_handle or "").strip().lstrip("@")
```

After:
```python
# twitter module
handle = ctx.best("contact", "twitter").value.strip().lstrip("@")
```

Before:
```python
# nosint module
email = ctx.email
```

After:
```python
# nosint module
email = ctx.best("contact", "email").value
```

Before (checking what prior modules found):
```python
# osint_web prompt
for kind in ("employer", "role", "location"):
    for s in ctx.best_signals(kind):
        ...
```

After:
```python
# osint_web prompt — identity + observations all in one place
for s in ctx.all("contact", "email"):
    lines.append(f"Known email: {s.value}")
for s in ctx.all("employer"):
    lines.append(f"Known employer: {s.value}")
```

## What goes away

| Before                        | After                     |
|-------------------------------|---------------------------|
| `ContextPatch` model          | gone                      |
| `_apply_patch()`              | gone                      |
| `_enrich_patch()`             | gone                      |
| `_auto_promote_social_links()`| `_social_links_to_signals()` (simpler) |
| `identity_provenance` dict    | gone — `ctx.all()` replaces it |
| 8 identity fields on Context  | gone — `ctx.best()` replaces them |
| 8 identity fields on Case     | gone — `case.signals` replaces them |
| `ctx_patch` on ModuleResult   | gone                      |
| `context_from_case` seeding   | trivial passthrough       |
| `AliasChoices` on Case fields | gone — no more field aliases |

## What stays

- `Signal` — gains a `tag` field, otherwise same.
- `Fact` — unchanged, still the unstructured type.
- `SocialLink` — stays on `ModuleResult` for API display, auto-converted to signals by runner.
- `ModuleResult.signals` — unchanged, modules emit signals same as before.
- `Case.context` — unchanged, unstructured caller notes.
- Wave scheduling — same logic, checks signals instead of fields.
- Synthesis — same, dedupes signals by `(kind, tag, value.lower())`.

## Migration path

1. Add `tag` to `Signal`.
2. Add `name` and `address` to `SignalKind`.
3. Rewrite `Case`: drop identity fields, keep `signals` + `context` + debt metadata.
4. Rewrite `Context`: drop identity fields + provenance, add `best()` / `all()` / `has()`.
5. Rewrite `context_from_case`: trivial passthrough.
6. Drop `ContextPatch`, `_apply_patch`, `_enrich_patch`, `identity_provenance`.
7. Update runner: just append signals + convert social_links. No more patch logic.
8. Update `requires` on each module to use `(kind, tag)` tuples.
9. Update each module's `run()` to use `ctx.best()` instead of `ctx.email` etc.
10. Update synthesis dedupe key to include `tag`.
11. Update LLM summary to read signals.
12. Update sample JSON files to new format.

Steps 8-9 touch every module but each change is mechanical (one-line).
