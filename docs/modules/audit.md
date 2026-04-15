# audit — Pipeline audit log

`backend/app/pipeline/audit.py`

## Overview

Structured event stream for one pipeline run. The runner calls `AuditLog.record(...)` at every orchestration step; each call appends a typed `AuditEvent` to an in-memory list **and** streams a formatted line to stderr for live progress.

The full event list travels back on `EnrichmentResponse.audit_log`.

## AuditLog

```python
class AuditLog(BaseModel):
    events: list[AuditEvent]
    _started_at: float  # monotonic anchor — private, not serialized
```

### `record(kind, *, module, wave, message, stream, **detail)`

Creates and appends an `AuditEvent`. `elapsed_s` is computed from the run's wall-clock anchor. `detail` captures any extra structured data (field names, confidence values, counts, etc.).

Event kinds emitted by the runner:

| kind | When |
|---|---|
| `pipeline_started` | Before wave 1 |
| `wave_started` | Each wave |
| `module_completed` | After each module (ok / error / skipped) |
| `ctx_patch_applied` | When a patch field is written to Context |
| `ctx_patch_rejected` | When a patch field is rejected (lower confidence) |
| `pipeline_completed` | After the last wave |

## render_summary

`render_summary(response)` produces a compact end-of-run summary for CLI stderr:

- Status counts (ok / skipped / error) and total wall time
- Per-module: status, duration, signal/fact/gap counts
- Context writes (applied and rejected patches)
- All gaps

This is distinct from the live stream — it's a single block printed at the end.
