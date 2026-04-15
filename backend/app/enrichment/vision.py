"""OpenRouter vision client for the Instagram OSINT enrichment step.

Two-pass analysis:
  Pass 1: per-image factual observations (multimodal, batched).
  Pass 2: synthesis into summary + facts + gaps (text-only).
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import httpx

from app.config import settings
from app.models import Fact


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

VISION_MODEL = "google/gemini-3-flash-preview"
FALLBACK_MODEL = "google/gemini-2.0-flash-001"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Bound per-request cost/latency. Gemini Flash handles ~10 images/request comfortably.
BATCH_SIZE = 10
REQUEST_TIMEOUT_S = 90.0


def _b64_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def _call_openrouter(
    messages: list[dict],
    model: str = VISION_MODEL,
    json_mode: bool = True,
) -> str:
    """POST to OpenRouter chat completions. Returns the message content string."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": "https://vexor.ai",
        "X-Title": "Vexor BCN Enrichment",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_json_loose(text: str) -> dict | list:
    """Parse JSON, tolerating code-fence wrappers the model sometimes emits."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Strip ```json ... ``` wrapper
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    return json.loads(stripped)


async def _observe_batch(
    batch: list[tuple[Path, str]],
    handle: str,
) -> list[dict]:
    """Pass 1: send a batch of images; get per-image observations."""
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"You are analyzing Instagram photos from the account @{handle} "
                "for an OSINT investigation supporting a debt collector.\n\n"
                "For each image below, output a JSON object with:\n"
                '  - "source": the exact source string I provide for that image\n'
                '  - "observations": list of factual statements about visible '
                "content (objects, locations, landmarks, text/signage, brands, "
                "vehicles, clothing, lifestyle indicators)\n"
                '  - "confidence": a single 0.0-1.0 confidence for the overall '
                "observation set\n\n"
                'Respond ONLY with JSON of the form {"images": [...]}. '
                "Do NOT speculate beyond what is visible. If an image is "
                "unreadable, return an empty observations list for it."
            ),
        }
    ]
    for path, source in batch:
        try:
            b64 = _b64_image(path)
        except OSError:
            continue
        content.append({"type": "text", "text": f"Image source: {source}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    raw = await _call_openrouter([{"role": "user", "content": content}])
    parsed = _parse_json_loose(raw)
    if isinstance(parsed, dict):
        return parsed.get("images", []) or []
    if isinstance(parsed, list):
        return parsed
    return []


async def _synthesize(
    observations: list[dict],
    captions: list[str],
    handle: str,
    profile_info: dict | None,
) -> tuple[str, list[Fact], list[str]]:
    """Pass 2: fold per-image observations + captions + profile into summary+facts."""
    prompt = (
        f"You are synthesizing OSINT findings for Instagram account @{handle}.\n\n"
        "Given the per-image observations, post captions, and profile info below, "
        "produce a JSON object with these keys:\n"
        '  - "summary": 2-3 sentence factual summary of what this account '
        "reveals about the person (lifestyle, location hints, employment/business, "
        "assets visible in photos).\n"
        '  - "facts": list of objects with {"claim": str, "source": str, '
        '"confidence": float 0.0-1.0}. EVERY claim MUST cite a source '
        "(an image URL/filename from the observations, or \"caption\" if from "
        "a caption, or \"profile_info\" if from profile data).\n"
        '  - "gaps": list of strings describing what could NOT be determined '
        "or where evidence is too weak to draw a conclusion.\n\n"
        "Be honest. Do NOT infer beyond the evidence. Prefer fewer well-sourced "
        "facts over many speculative ones. Output valid JSON only.\n\n"
        f"=== OBSERVATIONS ===\n{json.dumps(observations, indent=2)}\n\n"
        f"=== CAPTIONS ===\n{json.dumps(captions, indent=2)}\n\n"
        f"=== PROFILE INFO ===\n{json.dumps(profile_info, indent=2)}\n"
    )

    raw = await _call_openrouter(
        [{"role": "user", "content": prompt}],
        json_mode=True,
    )
    data = _parse_json_loose(raw)
    if not isinstance(data, dict):
        return "", [], ["Synthesis response was not a JSON object"]

    summary = str(data.get("summary", "")).strip()
    gaps = [str(g) for g in (data.get("gaps") or []) if g]

    facts: list[Fact] = []
    for raw_fact in data.get("facts") or []:
        if not isinstance(raw_fact, dict):
            continue
        claim = str(raw_fact.get("claim", "")).strip()
        source = str(raw_fact.get("source", "")).strip()
        if not claim or not source:
            continue
        try:
            confidence = float(raw_fact.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        facts.append(Fact(claim=claim, source=source, confidence=confidence))

    return summary, facts, gaps


async def analyze_images(
    images: list[tuple[Path, str]],
    captions: list[str],
    handle: str,
    profile_info: dict | None,
) -> tuple[str, list[Fact], list[str]]:
    """Two-pass vision analysis.

    images: list of (local_path, source_url_or_filename) tuples.
    Returns (summary, facts, gaps).
    """
    gaps: list[str] = []

    if not images and not captions and not profile_info:
        return "", [], ["No Instagram media or metadata available to analyze"]

    _log(
        f"[vision] analyzing {len(images)} image(s), "
        f"{len(captions)} caption(s), profile_info={'yes' if profile_info else 'no'} "
        f"with {VISION_MODEL}"
    )

    observations: list[dict] = []
    if images:
        total_batches = (len(images) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(images), BATCH_SIZE):
            batch_idx = i // BATCH_SIZE + 1
            batch = images[i : i + BATCH_SIZE]
            _log(
                f"[vision] batch {batch_idx}/{total_batches}: "
                f"sending {len(batch)} image(s)..."
            )
            t0 = time.monotonic()
            try:
                batch_obs = await _observe_batch(batch, handle)
            except httpx.HTTPStatusError as e:
                elapsed = time.monotonic() - t0
                _log(
                    f"[vision] batch {batch_idx}/{total_batches} FAILED "
                    f"in {elapsed:.1f}s: HTTP {e.response.status_code}"
                )
                gaps.append(
                    f"Vision call failed for batch {batch_idx}: "
                    f"HTTP {e.response.status_code}"
                )
                continue
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                elapsed = time.monotonic() - t0
                _log(
                    f"[vision] batch {batch_idx}/{total_batches} FAILED "
                    f"in {elapsed:.1f}s: {type(e).__name__}"
                )
                gaps.append(
                    f"Vision call failed for batch {batch_idx}: {type(e).__name__}"
                )
                continue
            elapsed = time.monotonic() - t0
            _log(
                f"[vision] batch {batch_idx}/{total_batches} done in "
                f"{elapsed:.1f}s ({len(batch_obs)} observation set(s) returned)"
            )
            observations.extend(batch_obs)

    _log(f"[vision] synthesizing facts from {len(observations)} observation(s)...")
    t0 = time.monotonic()
    try:
        summary, facts, synth_gaps = await _synthesize(
            observations, captions, handle, profile_info
        )
    except httpx.HTTPStatusError as e:
        elapsed = time.monotonic() - t0
        _log(f"[vision] synthesis FAILED in {elapsed:.1f}s: HTTP {e.response.status_code}")
        gaps.append(f"Synthesis call failed: HTTP {e.response.status_code}")
        return "", [], gaps
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        elapsed = time.monotonic() - t0
        _log(f"[vision] synthesis FAILED in {elapsed:.1f}s: {type(e).__name__}")
        gaps.append(f"Synthesis call failed: {type(e).__name__}")
        return "", [], gaps

    elapsed = time.monotonic() - t0
    _log(
        f"[vision] synthesis done in {elapsed:.1f}s "
        f"({len(facts)} fact(s), {len(synth_gaps)} synthesis gap(s))"
    )

    gaps.extend(synth_gaps)
    return summary, facts, gaps
