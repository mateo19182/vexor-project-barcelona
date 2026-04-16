"""Username-finder module — discovery layer for social profiles.

Architecture
------------
This module sits at layer 1 of a three-layer verification stack:

  1. Discovery (this module)
     Asks: "does username X exist on platform Y?"
     Uses sherlock-project to probe ~16 curated platforms in seconds.
     Emits SocialLinks for every hit.

  2. Profile enrichment  (instagram.py, twitter.py, linkedin.py, …)
     The runner auto-converts SocialLinks → contact signals, which unlock
     these modules in the next wave. They fetch the actual profile content
     (bio, posts, location, photo) and validate whether it matches the
     subject's known signals.

  3. Photo cross-reference  (image_search.py)
     Reverse-image searches the profile photo to confirm identity.

This module does NOT validate. A hit means the username is registered on a
platform — not that it belongs to the subject. Identity confirmation is the
downstream modules' responsibility.

Wave scheduling
---------------
Requires ``contact:enrichment_ran`` in addition to ``name``. Both
``NosintModule`` and ``OsintWebModule`` emit this sentinel at the end of
their runs, so username_finder is always scheduled after them (wave 2+).
This guarantees it sees all handles those modules discovered.

Username sources (priority order)
----------------------------------
1. Handles already on Context from nosint / osint_web / case input.
   Any contact signal with a known tag (twitter, instagram, …) contributes
   its value.  Values that are full profile URLs are parsed to extract the
   bare username.
2. Candidates derived from the subject's full name (heuristics for
   Spanish / Portuguese / French naming conventions).

Platform selection
------------------
We probe only ~16 platforms that have intelligence value for debt collection:
those with dedicated pipeline modules (Instagram, Twitter, LinkedIn, TikTok,
GitHub) or that reveal lifestyle / income / location signals (YouTube,
Twitch, Patreon, Telegram, Snapchat, Bluesky, Pinterest, Behance, Dribbble,
Medium, GitLab).

Confidence rubric
-----------------
  0.85 — confirmed a username already known from a prior enrichment step
  0.55 — confirmed a username derived from the subject's name
"""

from __future__ import annotations

import asyncio
import re
import sys
import time

from app.models import SocialLink
from app.pipeline.base import Context, ModuleResult

# ── Runtime limits ────────────────────────────────────────────────────────────

_MAX_USERNAMES = 8          # probed in a single subprocess call
_SHERLOCK_TIMEOUT_S = 90    # wall-clock cap for the whole call
_SITE_TIMEOUT_S = "10"      # per-site HTTP timeout passed to sherlock

# ── Platform curation ─────────────────────────────────────────────────────────
#
# Only check platforms with real intelligence value for debt collection.
# Keeps runtime to ~5-15 s and output signal:noise high.
#
# Tier 1 — have dedicated pipeline modules that will verify the hit:
#   Twitter, Instagram, LinkedIn, TikTok, GitHub
# Tier 2 — lifestyle / income / location signals:
#   YouTube, Twitch, Patreon, Telegram, Snapchat, Bluesky, Pinterest
# Tier 3 — professional identity (useful for photo cross-reference):
#   Behance, Dribbble, Medium, GitLab

_SITES_TO_CHECK: list[str] = [
    # Tier 1
    "Twitter", "Instagram", "LinkedIn", "TikTok", "GitHub",
    # Tier 2
    "YouTube", "Twitch", "Patreon", "Telegram", "Snapchat", "Bluesky", "Pinterest",
    # Tier 3
    "Behance", "Dribbble", "Medium", "GitLab",
]

# Tags we read from Context to collect pre-known handles.
_HANDLE_TAGS = ("twitter", "instagram", "linkedin", "github", "tiktok",
                "facebook", "youtube", "telegram")

# Regexes to recover a bare username from a URL-valued contact signal.
# The runner stores sl.url when sl.handle is absent; these patterns fix that.
_URL_HANDLE_RE: list[re.Pattern[str]] = [
    re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,50})/?$"),
    re.compile(r"instagram\.com/([A-Za-z0-9_.]{1,50})/?$"),
    re.compile(r"github\.com/([A-Za-z0-9\-]{1,39})/?$"),
    re.compile(r"tiktok\.com/@?([A-Za-z0-9_.]{1,50})/?$"),
    re.compile(r"facebook\.com/([A-Za-z0-9.]{1,50})/?$"),
    re.compile(r"linkedin\.com/in/([A-Za-z0-9\-]{1,100})/?$"),
    re.compile(r"youtube\.com/(?:user|c|@)/([A-Za-z0-9_.\-]{1,100})/?$"),
    re.compile(r"t\.me/([A-Za-z0-9_]{5,50})/?$"),
]
_GENERIC_SEGMENTS = {"home", "about", "help", "login", "signup", "explore", "channel"}

# ── Diacritic normalisation ───────────────────────────────────────────────────

_DIACRITICS = str.maketrans(
    "áàäâãéèëêíìïîóòöôõúùüûñçß",
    "aaaaaeeeeiiiiooooouuuuncs",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _handle_from_value(value: str) -> str:
    """Return the bare username from a value that may be a full profile URL."""
    if value.startswith("http"):
        for pattern in _URL_HANDLE_RE:
            m = pattern.search(value)
            if m:
                handle = m.group(1).lstrip("@")
                if handle.lower() not in _GENERIC_SEGMENTS:
                    return handle
    return value.lstrip("@").strip()


def _derive_usernames(full_name: str) -> list[str]:
    """Heuristic username candidates from a full name.

    Covers the most common patterns in Spanish / Portuguese / French names.
    Output is lowercase ASCII, no special characters.
    """
    name = full_name.lower().translate(_DIACRITICS)
    parts = re.split(r"[\s\-_]+", name)
    parts = [re.sub(r"[^a-z0-9]", "", p) for p in parts if p]
    if not parts:
        return []

    candidates: list[str] = []
    if len(parts) == 1:
        candidates.append(parts[0])
    else:
        first, *rest = parts
        last = rest[-1]
        candidates += [
            f"{first}{last}",      # marialopez
            f"{first}.{last}",     # maria.lopez
            f"{first[0]}{last}",   # mlopez
            f"{last}{first}",      # lopezm
            f"{last}.{first}",     # lopez.maria
        ]

    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique[:_MAX_USERNAMES]


def _parse_stdout(stdout: str) -> dict[str, list[tuple[str, str]]]:
    """Parse sherlock stdout → ``{username: [(platform, url), ...]}``.

    Sherlock v0.16 format:

        [*] Checking username alice on:
        [+] Twitter: https://twitter.com/alice
        [+] GitHub: https://github.com/alice
        [*] Results: 2 found.
    """
    results: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None

    for line in stdout.splitlines():
        m = re.search(r"(?:Checking username|Searching for) ['\"]?(\S+?)['\"]? on", line)
        if m:
            current = m.group(1)
            results.setdefault(current, [])
            continue
        m = re.match(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
        if m and current is not None:
            results[current].append((m.group(1).strip(), m.group(2).rstrip(".,)")))

    return results


# ── Module ────────────────────────────────────────────────────────────────────

class UsernameFinderModule:
    name = "username_finder"

    # Requires the enrichment_ran sentinel so this module is scheduled in a
    # later wave, after both NosintModule and OsintWebModule have completed.
    # By then all handles they discovered are already on ctx.signals.
    requires: tuple[tuple[str, str | None], ...] = (
        ("name", None),
        ("contact", "enrichment_ran"),
    )

    async def run(self, ctx: Context) -> ModuleResult:
        t0 = time.monotonic()

        # ── 1. Collect usernames ───────────────────────────────────────────
        usernames: list[str] = []
        known_handles: set[str] = set()

        # Priority 1: handles confirmed by earlier modules (nosint, osint_web)
        # or provided in the case input.  _handle_from_value extracts the bare
        # username when the contact signal stores a full profile URL.
        for tag in _HANDLE_TAGS:
            sig = ctx.best("contact", tag)
            if sig and sig.value:
                handle = _handle_from_value(sig.value)
                if handle and handle not in usernames:
                    usernames.append(handle)
                    known_handles.add(handle)

        # Priority 2: heuristic candidates derived from the subject's name.
        name_sig = ctx.best("name")
        if name_sig:
            for candidate in _derive_usernames(name_sig.value):
                if candidate not in usernames and len(usernames) < _MAX_USERNAMES:
                    usernames.append(candidate)

        if not usernames:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["username_finder: no usernames to probe"],
                duration_s=time.monotonic() - t0,
            )

        # ── 2. Run sherlock ────────────────────────────────────────────────
        cmd = [
            sys.executable, "-m", "sherlock_project",
            "--print-found",
            "--no-color",
            "--no-txt",
            "--timeout", _SITE_TIMEOUT_S,
            *(f"--site={site}" for site in _SITES_TO_CHECK),
            *usernames,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=_SHERLOCK_TIMEOUT_S
            )
        except FileNotFoundError:
            return ModuleResult(
                name=self.name,
                status="skipped",
                gaps=["username_finder: sherlock-project not installed — pip install sherlock-project"],
                duration_s=time.monotonic() - t0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            return ModuleResult(
                name=self.name,
                status="error",
                gaps=[f"username_finder: subprocess timed out after {_SHERLOCK_TIMEOUT_S}s"],
                duration_s=time.monotonic() - t0,
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")

        # ── 3. Build output ────────────────────────────────────────────────
        parsed = _parse_stdout(stdout_text)

        social_links: list[SocialLink] = []
        raw: dict[str, list[str]] = {}

        for username in usernames:
            hits = parsed.get(username, [])
            if not hits:
                continue

            # Known handles get higher confidence: sherlock is confirming an
            # already-attributed identity across more platforms.
            # Derived handles get lower confidence: we don't yet know this
            # username belongs to the subject — downstream modules verify.
            base_conf = 0.85 if username in known_handles else 0.55
            urls: list[str] = []

            for platform_name, url in hits:
                # Don't re-emit a SocialLink for a (tag, username) pair we
                # already know — avoid duplicating what nosint/osint_web found.
                from app.pipeline.runner import _PLATFORM_TO_TAG  # local import to avoid cycle
                tag = _PLATFORM_TO_TAG.get(platform_name.lower())
                if tag and username in known_handles:
                    existing = ctx.best("contact", tag)
                    if existing and _handle_from_value(existing.value) == username:
                        urls.append(url)
                        continue  # already on context, skip

                social_links.append(SocialLink(
                    platform=platform_name.lower(),
                    url=url,
                    handle=username,
                    confidence=base_conf,
                ))
                urls.append(url)

            if urls:
                raw[username] = urls

        if not social_links:
            return ModuleResult(
                name=self.name,
                status="ok",
                summary=(
                    f"username_finder: probed {len(usernames)} username(s) "
                    f"across {len(_SITES_TO_CHECK)} platforms — no new profiles found."
                ),
                gaps=["username_finder: no new profiles found beyond what was already known"],
                raw={"usernames_probed": usernames, "sites_checked": _SITES_TO_CHECK},
                duration_s=time.monotonic() - t0,
            )

        total_hits = sum(len(v) for v in raw.values())
        summary = (
            f"username_finder: {total_hits} profile(s) found across "
            f"{len(raw)} username(s) on {len(_SITES_TO_CHECK)} curated platforms "
            f"({', '.join(list(raw.keys())[:3])}"
            f"{'...' if len(raw) > 3 else ''})."
        )

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=summary,
            social_links=social_links,
            gaps=[],
            raw={
                "usernames_probed": usernames,
                "sites_checked": _SITES_TO_CHECK,
                "found_by_username": raw,
            },
            duration_s=time.monotonic() - t0,
        )
