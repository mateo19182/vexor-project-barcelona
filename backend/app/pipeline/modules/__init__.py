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
from app.pipeline.modules.borme import BormeModule
from app.pipeline.modules.brave_social import BraveSocialModule
from app.pipeline.modules.breach_scout import BreachScoutModule
from app.pipeline.modules.github_check import GithubCheckModule
from app.pipeline.modules.google_gaia_check import GoogleGaiaCheckModule
from app.pipeline.modules.gaia_enrichment import GaiaEnrichmentModule
from app.pipeline.modules.icloud_check import ICloudCheckModule
from app.pipeline.modules.image_search import ImageSearchModule
from app.pipeline.modules.instagram import InstagramModule
from app.pipeline.modules.instagram_check import InstagramCheckModule
from app.pipeline.modules.jooble import JoobleModule
from app.pipeline.modules.lead_verification import LeadVerificationModule
from app.pipeline.modules.linkedin import LinkedInModule
from app.pipeline.modules.nosint import NosintModule
from app.pipeline.modules.osint_web import OsintWebModule
from app.pipeline.modules.property import PropertyModule
from app.pipeline.modules.twitter_check import TwitterCheckModule
from app.pipeline.modules.twitter import TwitterModule
from app.pipeline.modules.twitter_vu import TwitterVuModule
from app.pipeline.modules.uber_hint import UberHintModule
from app.pipeline.modules.vision_batch import VisionBatchModule
from app.pipeline.modules.xon import XposedOrNotModule

REGISTRY: list[Module] = [
    BoeModule(),
    BormeModule(),
    BraveSocialModule(),
    BreachScoutModule(),
    GithubCheckModule(),
    GoogleGaiaCheckModule(),
    GaiaEnrichmentModule(),
    ICloudCheckModule(),
    ImageSearchModule(),
    InstagramModule(),
    InstagramCheckModule(),
    JoobleModule(),
    LeadVerificationModule(),
    LinkedInModule(),
    NosintModule(),
    OsintWebModule(),
    PropertyModule(),
    TwitterCheckModule(),
    TwitterModule(),
    TwitterVuModule(),
    UberHintModule(),
    VisionBatchModule(),
    XposedOrNotModule(),
]
