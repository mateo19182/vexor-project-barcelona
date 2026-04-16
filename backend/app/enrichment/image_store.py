"""Centralized image storage for the enrichment pipeline.

All modules that handle images (Instagram, Google Maps, Twitter, reverse image
search) funnel their downloads through this module so every image ends up in a
predictable location:

    photos/{case_id}/{platform}/filename.jpg

The vision_batch module later walks this tree to analyze everything at once.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import httpx

from app.config import settings


def _log(msg: str) -> None:
    print(f"[image_store] {msg}", file=sys.stderr, flush=True)


# Resolve once at import time; overridable via PHOTOS_DIR env if needed later.
PHOTOS_ROOT = Path(settings.logs_dir).resolve().parent / "photos"


def get_photos_dir(case_id: str, platform: str) -> Path:
    """Return (and create) the directory for a given case + platform."""
    d = PHOTOS_ROOT / case_id / platform
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_all_images(case_id: str) -> list[tuple[Path, str]]:
    """Return all (path, '{platform}/{filename}') pairs for a case."""
    case_dir = PHOTOS_ROOT / case_id
    if not case_dir.is_dir():
        return []
    images: list[tuple[Path, str]] = []
    for platform_dir in sorted(case_dir.iterdir()):
        if not platform_dir.is_dir():
            continue
        platform = platform_dir.name
        for f in sorted(platform_dir.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                images.append((f, f"{platform}/{f.name}"))
    return images


async def download_image(url: str, dest: Path, *, timeout: float = 30.0) -> bool:
    """Download an image URL to dest. Returns True on success."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            _log(f"saved {dest.name} ({len(resp.content)} bytes)")
            return True
    except Exception as e:  # noqa: BLE001
        _log(f"download failed for {url[:80]}: {e}")
        return False


def copy_image(src: Path, dest: Path) -> bool:
    """Copy a local image file to dest. Returns True on success."""
    try:
        shutil.copy2(src, dest)
        return True
    except OSError as e:
        _log(f"copy failed {src} -> {dest}: {e}")
        return False
