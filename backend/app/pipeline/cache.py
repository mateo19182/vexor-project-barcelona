"""Per-module result cache.

Each module's last successful result is saved to
`{logs_dir}/{case_id}/cache/{module_name}.json`. On re-run the same case,
the runner loads the cached `ModuleResult` instead of calling
`module.run(...)` — saving the expensive work (LLM tool loops, Osintgram
downloads, breach API calls).

Invalidation:
  * `fresh=True` on the runner skips the cache for all modules.
  * To recompute a single module, delete its cache file.
  * `error` and `skipped` results are never cached.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.pipeline.base import ModuleResult

# Match `_slug` in audit.py so run logs and cache share the same directory.
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    s = _SAFE_SLUG.sub("_", value).strip("._-") or "x"
    return s[:128]


def cache_path(logs_dir: str | Path, case_id: str, module_name: str) -> Path:
    return Path(logs_dir) / _slug(case_id) / "cache" / f"{_slug(module_name)}.json"


def load_cached(
    logs_dir: str | Path, case_id: str, module_name: str
) -> ModuleResult | None:
    """Return a cached result for this (case, module), or None if absent/corrupt."""
    path = cache_path(logs_dir, case_id, module_name)
    if not path.is_file():
        return None
    try:
        return ModuleResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_cached(
    logs_dir: str | Path, case_id: str, result: ModuleResult
) -> Path | None:
    """Persist `result` so the next run of this (case, module) can skip work.

    Returns the path written, or None if the write failed — callers should
    treat caching as best-effort and never fail a run on a cache error.
    """
    path = cache_path(logs_dir, case_id, result.name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            result.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        return path
    except OSError:
        return None
