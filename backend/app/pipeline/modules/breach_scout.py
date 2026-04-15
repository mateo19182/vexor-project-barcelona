"""Breach intelligence scout module.

Queries a breach-intelligence API (host configured via BREACH_INTEL_HOST) for
records associated with the debtor's name, email, or phone number.

Key value for debt collection:
  * Discovers contact vectors (email, phone) not on file → patched into ctx
  * Surfaces account aliases and usernames → social profile leads
  * Flags breach exposure as a risk signal

Runs in wave 1 (requires only `name`) alongside osint_web, so it can promote
emails and phones to Context before later modules need them.

Two modes:
  * Authenticated  — POST /api/v1/query_detail_batch with unmasked scopes
  * Unauthenticated — POST /api/v1/query (masked breach list, less useful)

The provider is intentionally opaque — source URLs use only the host value.
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import httpx

from app.config import settings
from app.models import AttributedValue, ContextPatch, Fact, Signal
from app.pipeline.base import Context, ModuleResult

_TIMEOUT = 20.0
_SCOPES = ["email", "phone", "real_name", "user_name"]
# Guard against enormous responses (famous people can have thousands of records).
# JSON parsing is synchronous — off-loaded to a thread, but we still cap records
# to avoid CPU-bound extraction blocking for too long.
_MAX_RESPONSE_MB = 5
_MAX_RESPONSE_BYTES = _MAX_RESPONSE_MB * 1024 * 1024
_MAX_RECORDS = 100


def _log(msg: str) -> None:
    print(f"[breach_scout] {msg}", file=sys.stderr, flush=True)


def _is_email(value: str) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _is_phone(value: str) -> bool:
    digits = "".join(c for c in value if c.isdigit())
    return len(digits) >= 7 and (value.startswith("+") or value[0].isdigit())


def _extract_strings(obj: Any, seen: set[str] | None = None) -> list[str]:
    """Recursively collect all string leaf values from a JSON-like object."""
    if seen is None:
        seen = set()
    results: list[str] = []
    if isinstance(obj, str):
        if obj and obj not in seen:
            seen.add(obj)
            results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_extract_strings(v, seen))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_extract_strings(item, seen))
    return results


def _extract_fields(record: dict[str, Any]) -> dict[str, list[str]]:
    """Extract known breach-record fields from a single record dict.

    Handles both flat dicts and nested `results` arrays. Field names are
    normalised to lowercase to tolerate different API conventions.
    """
    found: dict[str, list[str]] = {
        "email": [], "phone": [], "real_name": [], "user_name": [],
        "breach": [], "domain": [], "breach_date": [],
    }

    def _add(key: str, val: Any) -> None:
        if isinstance(val, str) and val.strip():
            found[key].append(val.strip())
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    found[key].append(v.strip())

    normalised = {k.lower(): v for k, v in record.items()}

    for key in list(found.keys()):
        _add(key, normalised.get(key))

    # also handle common alternate field names
    for alt, canonical in (
        ("username", "user_name"),
        ("name", "real_name"),
        ("date", "breach_date"),
        ("breach_name", "breach"),
        ("site", "domain"),
    ):
        if alt in normalised:
            _add(canonical, normalised[alt])

    # recurse into nested `results` list if present
    nested = normalised.get("results") or []
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                sub = _extract_fields(item)
                for k in found:
                    found[k].extend(sub[k])

    # deduplicate preserving order
    for k in found:
        seen: set[str] = set()
        deduped = []
        for v in found[k]:
            if v not in seen:
                seen.add(v)
                deduped.append(v)
        found[k] = deduped

    return found


class BreachScoutModule:
    name = "breach_scout"
    requires: tuple[str, ...] = ("name",)

    async def run(self, ctx: Context) -> ModuleResult:  # noqa: C901
        t0 = time.monotonic()

        host = (settings.breach_intel_host or "").rstrip("/")
        api_key = settings.breach_intel_api_key or ""

        if not host:
            return ModuleResult(
                name=self.name,
                status="skipped",
                summary="Breach intelligence host not configured (BREACH_INTEL_HOST unset).",
                gaps=["BREACH_INTEL_HOST env var not set — module disabled"],
                duration_s=time.monotonic() - t0,
            )

        # Build keyword list: name always; add email/phone if we have them.
        keywords: list[str] = []
        seen_kw: set[str] = set()
        for kw in (ctx.name, ctx.email, ctx.phone):
            if kw and kw not in seen_kw:
                seen_kw.add(kw)
                keywords.append(kw)

        _log(f"querying {len(keywords)} keyword(s): {keywords}")

        signals: list[Signal] = []
        facts: list[Fact] = []
        gaps: list[str] = []
        raw: dict[str, Any] = {"keywords": keywords, "mode": "", "response": None, "status_code": None}

        source_base = host

        async with httpx.AsyncClient() as client:
            if api_key:
                raw["mode"] = "authenticated_batch"
                url = f"{host}/api/v1/query_detail_batch"
                payload: dict[str, Any] = {"keywords": keywords, "scopes": _SCOPES}
                headers = {
                    "X-Auth-Key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                try:
                    resp = await client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
                    raw["status_code"] = resp.status_code
                    raw["response_bytes"] = len(resp.content)
                    _log(f"batch response {resp.status_code} ({len(resp.content):,} bytes)")
                    if resp.status_code == 200:
                        if len(resp.content) > _MAX_RESPONSE_BYTES:
                            _log(f"response exceeds {_MAX_RESPONSE_MB} MB — parsing in thread, records will be capped")
                            gaps.append(f"Response very large ({len(resp.content) // 1024:,} KB) — capped at {_MAX_RECORDS} records")
                        raw["response"] = await asyncio.to_thread(resp.json)
                    else:
                        raw["response_text"] = resp.text[:500]
                except Exception as exc:
                    _log(f"request failed: {exc}")
                    return ModuleResult(
                        name=self.name,
                        status="error",
                        summary=f"Breach intelligence request failed: {exc}",
                        gaps=[f"HTTP error: {exc}"],
                        raw=raw,
                        duration_s=time.monotonic() - t0,
                    )
            else:
                # Unauthenticated path: query by name only (masked results)
                raw["mode"] = "unauthenticated"
                url = f"{host}/api/v1/query"
                payload = {"keyword": ctx.name}
                headers = {"Content-Type": "application/json", "Accept": "application/json"}
                gaps.append(
                    "BREACH_INTEL_API_KEY not set — running in unauthenticated mode; "
                    "results are masked and contact fields are not returned"
                )
                try:
                    resp = await client.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
                    raw["status_code"] = resp.status_code
                    raw["response_bytes"] = len(resp.content)
                    _log(f"unauthenticated response {resp.status_code} ({len(resp.content):,} bytes)")
                    if resp.status_code == 200:
                        raw["response"] = await asyncio.to_thread(resp.json)
                    else:
                        raw["response_text"] = resp.text[:500]
                except Exception as exc:
                    _log(f"request failed: {exc}")
                    return ModuleResult(
                        name=self.name,
                        status="error",
                        summary=f"Breach intelligence request failed: {exc}",
                        gaps=[f"HTTP error: {exc}"],
                        raw=raw,
                        duration_s=time.monotonic() - t0,
                    )

        # ── parse response ─────────────────────────────────────────────────
        response = raw.get("response")
        if raw.get("status_code") != 200 or response is None:
            gaps.append(
                f"Breach intelligence returned status {raw.get('status_code')}; "
                "no data available"
            )
            return ModuleResult(
                name=self.name,
                status="error",
                summary="Breach intelligence lookup returned an error response.",
                gaps=gaps,
                raw=raw,
                duration_s=time.monotonic() - t0,
            )

        # Normalise: the API may return a list (one item per keyword) or a
        # single dict; handle both.
        records: list[Any] = []
        if isinstance(response, list):
            records = response
        elif isinstance(response, dict):
            records = [response]

        if len(records) > _MAX_RECORDS:
            _log(f"capping {len(records)} records to {_MAX_RECORDS}")
            records = records[:_MAX_RECORDS]

        if not records:
            _log("empty result set — no breach records found")
            gaps.append("No breach records found for the supplied identifiers")
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"No breach records found for {ctx.name}.",
                gaps=gaps,
                raw=raw,
                duration_s=time.monotonic() - t0,
            )

        # Collect all fields across every record
        all_emails: list[str] = []
        all_phones: list[str] = []
        all_usernames: list[str] = []
        all_breaches: list[str] = []
        all_domains: list[str] = []

        for record in records:
            if not isinstance(record, dict):
                # flat string values — scan for emails/phones
                for s in _extract_strings(record):
                    if _is_email(s):
                        all_emails.append(s)
                    elif _is_phone(s):
                        all_phones.append(s)
                continue

            fields = _extract_fields(record)
            all_emails.extend(fields["email"])
            all_phones.extend(fields["phone"])
            all_usernames.extend(fields["user_name"])
            all_breaches.extend(fields["breach"])
            all_domains.extend(fields["domain"])

            # Also do a best-effort scan of any remaining string values for
            # emails/phones the API might store under unexpected field names
            for s in _extract_strings(record):
                if _is_email(s) and s not in all_emails:
                    all_emails.append(s)
                elif _is_phone(s) and s not in all_phones:
                    all_phones.append(s)

        # deduplicate everything
        def _dedup(lst: list[str]) -> list[str]:
            seen: set[str] = set()
            return [x for x in lst if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

        all_emails = _dedup(all_emails)
        all_phones = _dedup(all_phones)
        all_usernames = _dedup(all_usernames)
        all_breaches = _dedup(all_breaches)
        all_domains = _dedup(all_domains)

        _log(
            f"parsed: {len(all_breaches)} breach(es), "
            f"{len(all_emails)} email(s), {len(all_phones)} phone(s), "
            f"{len(all_usernames)} username(s)"
        )

        # ── build signals / facts / ctx_patch ─────────────────────────────
        ctx_patch = ContextPatch()

        breach_label = ", ".join((all_breaches + all_domains)[:5]) or "breach database"

        # Risk flag — debtor identity found in breach records
        total_breaches = len(all_breaches) or len(records)
        if total_breaches:
            signals.append(Signal(
                kind="risk_flag",
                value=f"Debtor identifiers found in {total_breaches} breach record(s)",
                source=source_base,
                confidence=0.85,
                notes=f"Breaches: {breach_label}" if breach_label else None,
            ))
            facts.append(Fact(
                claim=f"Identity found in {total_breaches} breach record(s) in the breach intelligence database",
                source=source_base,
                confidence=0.85,
            ))

        # Contact signals — emails discovered
        ctx_email_lower = (ctx.email or "").lower()
        new_emails = [e for e in all_emails if e.lower() != ctx_email_lower]
        for email in new_emails:
            signals.append(Signal(
                kind="contact",
                value=email,
                source=source_base,
                confidence=0.70,
                notes="Email address recovered from breach records",
            ))
        if new_emails and not ctx.email:
            # Promote the first discovered email into Context
            ctx_patch.email = AttributedValue(
                value=new_emails[0],
                source=source_base,
                confidence=0.55,
            )
            _log(f"promoting email to ctx_patch: {new_emails[0]}")

        # Contact signals — phones discovered
        ctx_phone_digits = "".join(c for c in (ctx.phone or "") if c.isdigit())
        new_phones = [
            p for p in all_phones
            if "".join(c for c in p if c.isdigit()) != ctx_phone_digits
        ]
        for phone in new_phones:
            signals.append(Signal(
                kind="contact",
                value=phone,
                source=source_base,
                confidence=0.70,
                notes="Phone number recovered from breach records",
            ))
        if new_phones and not ctx.phone:
            ctx_patch.phone = AttributedValue(
                value=new_phones[0],
                source=source_base,
                confidence=0.55,
            )
            _log(f"promoting phone to ctx_patch: {new_phones[0]}")

        # Contact signals — usernames / aliases
        for username in all_usernames[:10]:  # cap to avoid noise
            signals.append(Signal(
                kind="contact",
                value=username,
                source=source_base,
                confidence=0.65,
                notes="Username / alias found in breach records — may correspond to social profiles",
            ))

        if not signals and not facts:
            gaps.append("Breach records returned but no actionable contact or risk data could be extracted")
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"Breach records found for {ctx.name} but contained no usable contact or risk fields.",
                gaps=gaps,
                raw=raw,
                duration_s=time.monotonic() - t0,
            )

        summary_parts: list[str] = []
        if total_breaches:
            summary_parts.append(f"Found in {total_breaches} breach record(s)")
        if new_emails:
            summary_parts.append(f"{len(new_emails)} new email(s) discovered: {', '.join(new_emails[:3])}")
        if new_phones:
            summary_parts.append(f"{len(new_phones)} new phone(s) discovered: {', '.join(new_phones[:3])}")
        if all_usernames:
            summary_parts.append(f"Aliases/usernames: {', '.join(all_usernames[:3])}")

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=" | ".join(summary_parts),
            signals=signals,
            facts=facts,
            gaps=gaps,
            ctx_patch=ctx_patch,
            raw=raw,
            duration_s=time.monotonic() - t0,
        )
