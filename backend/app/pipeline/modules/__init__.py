"""Module registry.

Add a new module in two steps:
  1. Create `app/pipeline/modules/<name>.py` with a class whose instance
     satisfies the `Module` protocol (name, requires, async run).
  2. Append an instance of it to REGISTRY below.

That's it — the runner picks up dependencies automatically from `requires`.
"""

from __future__ import annotations

from app.pipeline.base import Module
from app.pipeline.modules.boe import BoeModule
from app.pipeline.modules.breach_scout import BreachScoutModule
from app.pipeline.modules.google_maps import GoogleMapsModule
from app.pipeline.modules.icloud_check import ICloudCheckModule
from app.pipeline.modules.image_search import ImageSearchModule
from app.pipeline.modules.instagram import InstagramModule
from app.pipeline.modules.instagram_check import InstagramCheckModule
from app.pipeline.modules.osint_web import OsintWebModule
from app.pipeline.modules.property import PropertyModule
from app.pipeline.modules.twitter_check import TwitterCheckModule
from app.pipeline.modules.xon import XposedOrNotModule

REGISTRY: list[Module] = [
    BoeModule(),
    BreachScoutModule(),
    GoogleMapsModule(),
    ICloudCheckModule(),
    ImageSearchModule(),
    InstagramModule(),
    InstagramCheckModule(),
    OsintWebModule(),
    PropertyModule(),
    TwitterCheckModule(),
    XposedOrNotModule(),
]
