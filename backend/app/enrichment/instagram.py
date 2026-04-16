"""Instagram OSINT enrichment step.

Runs the sibling Osintgram tool as a subprocess to download a target's feed
photos, profile picture, stories, captions, and profile info — then calls a
vision model via OpenRouter to extract structured facts tied to sources.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from app.config import settings
from app.enrichment.vision import analyze_images
from app.models import InstagramEnrichment


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

OSINTGRAM_COMMANDS: tuple[str, ...] = ("info", "captions", "propic", "photos", "stories")
COMMAND_TIMEOUT_S = 120.0
MAX_IMAGES_TO_ANALYZE = 10


def _has_cached_data(target_dir: Path) -> bool:
    """True if the handle's output dir already has meaningful Osintgram data.

    Any .jpg or .json counts — we don't re-download if a previous Osintgram
    run (manual or backend) already populated the folder. The user can force
    a refresh by deleting `<output_dir>/<handle>/`.
    """
    if not target_dir.is_dir():
        return False
    for entry in target_dir.iterdir():
        if entry.suffix.lower() in (".jpg", ".json"):
            return True
    return False

# Base64 alphabet used by Instagram for converting media PKs to shortcodes.
_SHORTCODE_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


def _media_pk_to_shortcode(media_pk: int) -> str:
    if media_pk <= 0:
        return ""
    shortcode = ""
    n = media_pk
    while n > 0:
        shortcode = _SHORTCODE_ALPHABET[n % 64] + shortcode
        n //= 64
    return shortcode


def _filename_to_source(handle: str, path: Path) -> str:
    """Turn e.g. georgehotz_3482648287635127189_4038382.jpg into an IG URL."""
    name = path.stem  # strip .jpg
    if not name.startswith(f"{handle}_"):
        return path.name
    rest = name[len(handle) + 1 :]
    # Pattern: <media_pk>_<owner_pk> OR just <media_pk> (stories).
    m = re.match(r"^(\d+)(?:_\d+)?$", rest)
    if not m:
        return path.name
    try:
        media_pk = int(m.group(1))
    except ValueError:
        return path.name
    shortcode = _media_pk_to_shortcode(media_pk)
    if not shortcode:
        return path.name
    return f"https://www.instagram.com/p/{shortcode}/"


async def _run_osintgram(
    command: str, handle: str, output_dir: Path
) -> tuple[bool, str]:
    """Run one Osintgram command as a subprocess. Returns (ok, error_detail)."""
    # Osintgram reads HIKERAPI_TOKEN from os.environ (case-sensitive, upper).
    # Our settings hold it under `hikerapi_token` from the .env file; push it
    # into the subprocess env so the HikerCLI backend is actually selected.
    subprocess_env = os.environ.copy()
    if settings.hikerapi_token:
        subprocess_env["HIKERAPI_TOKEN"] = settings.hikerapi_token

    try:
        proc = await asyncio.create_subprocess_exec(
            settings.osintgram_python,
            "main.py",
            handle,
            "-c",
            command,
            "-j",
            "-f",
            "-o",
            str(output_dir),
            cwd=settings.osintgram_root,
            env=subprocess_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return False, f"Osintgram not found at {settings.osintgram_python}"
    except OSError as e:
        return False, f"Failed to start Osintgram: {e}"

    try:
        # HikerCLI.get_user_photo() prompts "how many photos" via input().
        # Send "\n" (= empty = download all) so it doesn't block on EOF.
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=b"\n"), timeout=COMMAND_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return False, f"Command '{command}' timed out after {COMMAND_TIMEOUT_S:.0f}s"

    combined = (stdout_b or b"").decode("utf-8", errors="replace") + (
        stderr_b or b""
    ).decode("utf-8", errors="replace")
    lowered = combined.lower()

    if proc.returncode != 0:
        if "private profile" in lowered:
            return False, "Profile is private"
        if "non exist" in lowered or "not exist" in lowered:
            return False, f"Instagram user '{handle}' not found"
        if "challenge" in lowered:
            return False, "Instagram login challenge/2FA required"
        if "throttled" in lowered or "rate" in lowered and "limit" in lowered:
            return False, "Instagram rate-limited the session"
        return False, f"Command '{command}' failed (exit {proc.returncode})"

    # Osintgram's config helpers call sys.exit(0) when required credentials
    # are missing — they print an "Error: ... cannot be blank" / "missing X
    # field" message to stdout and bail with exit code 0. Detect that so we
    # don't report a silent success.
    if "cannot be blank" in lowered or (
        "missing" in lowered and "field" in lowered and "credentials.ini" in lowered
    ):
        return False, (
            "Osintgram credentials missing — set HIKERAPI_TOKEN "
            "(via hikerapi_token in backend/.env) or fill config/credentials.ini"
        )
    if "error:" in lowered and ("token" in lowered or "credential" in lowered):
        return False, f"Osintgram config error: {combined.strip().splitlines()[0][:200]}"

    # Some Osintgram commands print errors but exit 0. Heuristic check.
    if "sorry! no results" in lowered and command not in ("stories", "photos"):
        # Harmless for media commands; noteworthy for metadata commands.
        return True, ""

    return True, ""


def _collect_outputs(
    scratch: Path, handle: str
) -> tuple[list[tuple[Path, str]], int, list[str], dict | None]:
    """Return (images_with_sources, video_count, captions, profile_info)."""
    target_dir = scratch / handle
    if not target_dir.is_dir():
        return [], 0, [], None

    all_files = sorted(target_dir.iterdir())

    jpgs = [p for p in all_files if p.suffix.lower() == ".jpg"]
    # Put the propic first so it gets prioritized if we hit the cap.
    propic_name = f"{handle}_propic.jpg"
    propic = [p for p in jpgs if p.name == propic_name]
    other = [p for p in jpgs if p.name != propic_name]
    # Newest-first for the feed photos (filenames contain media PKs that are
    # roughly chronological; largest = newest).
    other.sort(key=lambda p: p.name, reverse=True)
    ordered = propic + other
    ordered = ordered[:MAX_IMAGES_TO_ANALYZE]

    images: list[tuple[Path, str]] = []
    for p in ordered:
        if p.name == propic_name:
            source = f"{handle}_propic.jpg (profile picture)"
        else:
            source = _filename_to_source(handle, p)
        images.append((p, source))

    video_count = sum(1 for p in all_files if p.suffix.lower() == ".mp4")

    # Captions land in <handle>_followings.json due to an Osintgram bug. Also
    # check the expected <handle>_captions.json in case it gets fixed upstream.
    captions: list[str] = []
    for candidate in (
        target_dir / f"{handle}_captions.json",
        target_dir / f"{handle}_followings.json",
    ):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("captions"), list):
            captions = [str(c) for c in data["captions"] if c]
            break

    profile_info: dict | None = None
    info_path = target_dir / f"{handle}_info.json"
    if info_path.is_file():
        try:
            loaded = json.loads(info_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                profile_info = loaded
        except (OSError, json.JSONDecodeError):
            pass

    return images, video_count, captions, profile_info


async def enrich_instagram(
    *, handle: str, case_id: str = ""
) -> InstagramEnrichment:
    """Run the Instagram OSINT enrichment step for one handle.

    Always returns an InstagramEnrichment (never raises) — any failures are
    recorded in `gaps` so the collector can see exactly what we couldn't find.
    """
    handle = handle.strip().lstrip("@")
    if not handle:
        return InstagramEnrichment(
            summary="No Instagram handle provided for this case.",
            gaps=["No Instagram handle provided"],
        )

    _log(f"[instagram] enrichment for @{handle} (case {case_id})")
    t_total = time.monotonic()

    # Share one output dir across all cases keyed by handle, so two cases
    # with the same Instagram handle don't trigger two full downloads.
    # Resolve to absolute because Osintgram is launched with cwd changed.
    output_base = Path(settings.osintgram_output_dir).resolve()
    output_base.mkdir(parents=True, exist_ok=True)
    target_dir = output_base / handle

    gaps: list[str] = []
    if _has_cached_data(target_dir):
        _log(f"[instagram] cache HIT at {target_dir} — skipping Osintgram downloads")
        gaps.append(
            f"Used cached Osintgram data for @{handle} "
            f"(delete {target_dir} to force a refresh)"
        )
    else:
        _log(f"[instagram] cache MISS — running {len(OSINTGRAM_COMMANDS)} Osintgram command(s)")
        for idx, cmd in enumerate(OSINTGRAM_COMMANDS, start=1):
            _log(f"[instagram] ({idx}/{len(OSINTGRAM_COMMANDS)}) osintgram '{cmd}'...")
            t0 = time.monotonic()
            ok, detail = await _run_osintgram(cmd, handle, output_base)
            elapsed = time.monotonic() - t0
            if ok:
                _log(f"[instagram] ({idx}/{len(OSINTGRAM_COMMANDS)}) '{cmd}' OK in {elapsed:.1f}s")
            else:
                _log(
                    f"[instagram] ({idx}/{len(OSINTGRAM_COMMANDS)}) '{cmd}' "
                    f"FAIL in {elapsed:.1f}s: {detail}"
                )
                gaps.append(f"Osintgram '{cmd}': {detail}")
                # Hard-stop conditions — no point running further commands.
                if detail in ("Profile is private",) or "not found" in detail:
                    _log("[instagram] hard-stop: aborting remaining commands")
                    break
                if "challenge" in detail.lower() or "credentials" in detail.lower():
                    _log("[instagram] hard-stop: aborting remaining commands")
                    break

    _log(f"[instagram] collecting outputs from {target_dir}...")
    images, video_count, captions, profile_info = _collect_outputs(output_base, handle)
    _log(
        f"[instagram] collected: {len(images)} image(s), {video_count} video(s), "
        f"{len(captions)} caption(s), profile_info={'yes' if profile_info else 'no'}"
    )

    if not images and not captions and profile_info is None:
        return InstagramEnrichment(
            summary=f"Could not retrieve any Instagram data for @{handle}.",
            gaps=gaps or [f"No data retrieved for @{handle}"],
            image_count=0,
            video_count=video_count,
        )

    extra_context: dict = {}
    if captions:
        extra_context["captions"] = captions
    if profile_info:
        extra_context["profile_info"] = profile_info

    summary, facts, vision_gaps = await analyze_images(
        images=images,
        subject=f"Instagram account @{handle}",
        extra_context=extra_context or None,
    )
    gaps.extend(vision_gaps)

    if video_count:
        gaps.append(
            f"{video_count} video(s) were downloaded but not analyzed "
            "(vision pass processes still images only)"
        )

    if not summary:
        summary = (
            f"Retrieved {len(images)} image(s) and {len(captions)} caption(s) "
            f"for @{handle} but synthesis did not produce a summary."
        )

    _log(
        f"[instagram] done in {time.monotonic() - t_total:.1f}s total "
        f"({len(facts)} fact(s), {len(gaps)} gap(s))"
    )

    return InstagramEnrichment(
        summary=summary,
        facts=facts,
        gaps=gaps,
        raw_captions=captions,
        profile_info=profile_info,
        image_count=len(images),
        video_count=video_count,
    )
