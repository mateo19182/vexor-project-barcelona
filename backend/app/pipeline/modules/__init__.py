"""Module registry.

Add a new module in two steps:
  1. Create `app/pipeline/modules/<name>.py` with a class whose instance
     satisfies the `Module` protocol (name, requires, async run).
  2. Append an instance of it to REGISTRY below.

That's it — the runner picks up dependencies automatically from `requires`.
"""

from __future__ import annotations

from app.pipeline.base import Module
from app.pipeline.modules.instagram import InstagramModule
from app.pipeline.modules.osint_web import OsintWebModule

REGISTRY: list[Module] = [
    InstagramModule(),
    OsintWebModule(),
]
