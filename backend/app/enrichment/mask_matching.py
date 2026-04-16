"""Mask-matching algorithm for lead contact verification.

Compares known contact data (email, phone) against masked versions returned
by platform-check APIs (Twitter VU, Uber Hint) to assess whether the lead's
contact information is still current.

Mask formats observed:
  Twitter email: ``sl****@p*********.***``  — first chars of each segment visible
  Twitter phone: ``94``                     — last 2 digits only
  Uber phone:   ``********64``              — last 2 digits, rest starred
  Uber email:   ``j***@g****.***``          — similar to Twitter (when available)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MatchResult:
    """Outcome of comparing one known value against one mask."""

    result: str  # "compatible", "incompatible", "inconclusive"
    reason: str
    mask: str
    platform: str
    field: str  # "email" or "phone"


# ---------------------------------------------------------------------------
# Email mask matching
# ---------------------------------------------------------------------------

def match_email_mask(email: str, mask: str, platform: str) -> MatchResult:
    """Compare a known email against a masked email.

    Mask format: visible chars + ``*`` replacements, structure (``@``, ``.``)
    preserved.  E.g. ``sl****@p*********.***``.
    """
    email = email.strip().lower()
    mask = mask.strip().lower()

    if not mask or not email or "@" not in mask or "@" not in email:
        return MatchResult("inconclusive", "Invalid format", mask, platform, "email")

    e_local, e_domain = email.rsplit("@", 1)
    m_local, m_domain = mask.rsplit("@", 1)

    mismatches: list[str] = []
    matches: list[str] = []

    # --- Local part ---
    # Extract visible prefix (chars before first *)
    m_local_prefix = _visible_prefix(m_local)
    if m_local_prefix:
        if e_local.startswith(m_local_prefix):
            matches.append(f"local prefix '{m_local_prefix}' matches")
        else:
            mismatches.append(
                f"local prefix '{m_local_prefix}' != '{e_local[:len(m_local_prefix)]}'"
            )

    # Check local part length (stars + visible = total)
    m_local_len = len(m_local)
    if m_local_len > 0 and abs(len(e_local) - m_local_len) > 1:
        mismatches.append(f"local length {len(e_local)} vs mask {m_local_len}")

    # --- Domain ---
    # Domain may be partially masked: ``p*********.***`` or ``g****.***``
    # Split both by dots and compare segment-by-segment.
    e_parts = e_domain.split(".")
    m_parts = m_domain.split(".")

    if len(e_parts) != len(m_parts):
        mismatches.append(
            f"domain segments {len(e_parts)} vs mask {len(m_parts)}"
        )
    else:
        for i, (ep, mp) in enumerate(zip(e_parts, m_parts)):
            mp_prefix = _visible_prefix(mp)
            if mp_prefix:
                if ep.startswith(mp_prefix):
                    matches.append(f"domain[{i}] prefix '{mp_prefix}' matches")
                else:
                    mismatches.append(
                        f"domain[{i}] prefix '{mp_prefix}' != '{ep[:len(mp_prefix)]}'"
                    )
            # Check segment length
            if len(mp) > 0 and abs(len(ep) - len(mp)) > 1:
                mismatches.append(
                    f"domain[{i}] length {len(ep)} vs mask {len(mp)}"
                )

    if mismatches:
        return MatchResult(
            "incompatible",
            "; ".join(mismatches),
            mask, platform, "email",
        )
    if matches:
        return MatchResult(
            "compatible",
            "; ".join(matches),
            mask, platform, "email",
        )
    return MatchResult("inconclusive", "No visible chars to compare", mask, platform, "email")


# ---------------------------------------------------------------------------
# Phone mask matching
# ---------------------------------------------------------------------------

def match_phone_mask(phone: str, mask: str, platform: str) -> MatchResult:
    """Compare a known phone against a masked phone.

    Two formats:
      - Suffix-only: ``94`` or ``64`` — just last N digits
      - Starred:     ``********64`` — stars + last N digits
    """
    # Normalize: strip spaces, dashes, parens, plus
    phone_digits = re.sub(r"[^\d]", "", phone)
    mask_clean = mask.strip()

    if not mask_clean or not phone_digits:
        return MatchResult("inconclusive", "Empty value", mask, platform, "phone")

    # Extract visible suffix digits from mask
    # For "********64" → "64", for "94" → "94"
    suffix = mask_clean.lstrip("*").strip()
    # If the mask is pure digits (no stars), treat whole thing as suffix
    if not suffix:
        # All stars? Inconclusive
        return MatchResult("inconclusive", "Mask is fully obscured", mask, platform, "phone")

    if not suffix.isdigit():
        return MatchResult("inconclusive", f"Non-digit suffix: {suffix!r}", mask, platform, "phone")

    if phone_digits.endswith(suffix):
        return MatchResult(
            "compatible",
            f"last {len(suffix)} digits '{suffix}' match",
            mask, platform, "phone",
        )
    else:
        actual_suffix = phone_digits[-len(suffix):] if len(phone_digits) >= len(suffix) else phone_digits
        return MatchResult(
            "incompatible",
            f"last {len(suffix)} digits '{suffix}' != '{actual_suffix}'",
            mask, platform, "phone",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _visible_prefix(segment: str) -> str:
    """Return the leading non-``*`` characters of a mask segment."""
    prefix = []
    for ch in segment:
        if ch == "*":
            break
        prefix.append(ch)
    return "".join(prefix)
