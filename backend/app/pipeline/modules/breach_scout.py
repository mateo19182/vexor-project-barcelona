"""Breach intelligence scout module.

Queries a breach-intelligence API (host configured via BREACH_INTEL_HOST) for
records associated with the debtor's name, email, or phone number.

Key value for debt collection:
  * Discovers contact vectors (email, phone) not on file -> emitted as signals
  * Surfaces account aliases and usernames -> social profile leads
  * Flags breach exposure as a risk signal

Runs in wave 1 (requires only `name`) alongside osint_web, so it can emit
email/phone signals before later modules need them.

Two modes:
  * Authenticated  — POST /api/v1/query_detail_batch with unmasked scopes
  * Unauthenticated — POST /api/v1/query (masked breach list, less useful)

The provider is intentionally opaque — source URLs use only the host value.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from typing import Any

import httpx

from app.config import settings
from app.models import Fact, Signal
from app.pipeline.base import Context, ModuleResult

_TIMEOUT = 20.0
_SCOPES = ["email", "phone", "real_name", "user_name"]
# Guard against enormous responses (famous people can have thousands of records).
_MAX_RESPONSE_MB = 5
_MAX_RESPONSE_BYTES = _MAX_RESPONSE_MB * 1024 * 1024
_MAX_RECORDS = 100

_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}([-/]\d{2})?$")
_PHONE_IN_TEXT_RE = re.compile(r"\+\d[\d\s]{6,}")
_ROLE_PREFIXES = [
    "Sole Administrator",
    "General Manager",
    "Commercial Director",
    "Financial Manager",
    "Member of the Board",
    "Administrator",
    "Director",
    "Secretary",
    "Manager",
]


def _log(msg: str) -> None:
    print(f"[breach_scout] {msg}", file=sys.stderr, flush=True)


def _is_email(value: str) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _is_phone(value: str) -> bool:
    if _DATE_RE.match(value.strip()):
        return False
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
    """Extract known breach-record fields from a single record dict."""
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

    for alt, canonical in (
        ("username", "user_name"),
        ("name", "real_name"),
        ("date", "breach_date"),
        ("breach_name", "breach"),
        ("site", "domain"),
    ):
        if alt in normalised:
            _add(canonical, normalised[alt])

    # Extract from nested source dict (batch response records)
    src = normalised.get("source")
    if isinstance(src, dict):
        _add("domain", src.get("domain"))
        _add("breach_date", src.get("breach_date"))
        _add("breach", src.get("title"))

    nested = normalised.get("results") or []
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                sub = _extract_fields(item)
                for k in found:
                    found[k].extend(sub[k])

    for k in found:
        seen: set[str] = set()
        deduped = []
        for v in found[k]:
            if v not in seen:
                seen.add(v)
                deduped.append(v)
        found[k] = deduped

    return found


def _parse_other_info(text: str) -> dict[str, str | None]:
    """Parse other_info for business name, role, and embedded phone number.

    Bureau van Dijk records use patterns like:
      "Sole Administrator Hotel Natureza Monte Blanco Sl.  +34 981714428"
      "Motivos Singulares Sl"
      "General Manager Serviocio Madrid Sur Sl  +34 916245811"
    """
    result: dict[str, str | None] = {"business": None, "role": None, "phone": None}
    if not text or not text.strip():
        return result

    remainder = text.strip()

    # Extract phone at the end (e.g. "+34 981714428")
    phone_match = _PHONE_IN_TEXT_RE.search(remainder)
    if phone_match:
        result["phone"] = re.sub(r"\s+", "", phone_match.group().strip())
        remainder = remainder[:phone_match.start()].strip()

    if not remainder:
        return result

    # Check for role prefix
    for prefix in _ROLE_PREFIXES:
        if remainder.lower().startswith(prefix.lower()):
            result["role"] = prefix
            remainder = remainder[len(prefix):].strip()
            break

    # Whatever remains is the business name — skip if it looks like a person name
    # (no company suffix like Sl, Sa, Slu, etc.)
    if remainder:
        cleaned = remainder.rstrip(". ").strip()
        # BvD company names typically end with a legal suffix
        _has_biz_suffix = bool(re.search(
            r"\b(sl|sa|slu|sll|sc|cb|coop|gmbh|ltd|inc|corp|llc|ag)\b",
            cleaned, re.IGNORECASE,
        ))
        if _has_biz_suffix or result["role"]:
            result["business"] = cleaned

    return result


class BreachScoutModule:
    name = "breach_scout"
    requires: tuple[tuple[str, str | None], ...] = (("name", None),)

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
        name_sig = ctx.best("name")
        email_sig = ctx.best("contact", "email")
        phone_sig = ctx.best("contact", "phone")

        name_val = name_sig.value if name_sig else ""
        email_val = email_sig.value if email_sig else ""
        phone_val = phone_sig.value if phone_sig else ""

        keywords: list[str] = []
        seen_kw: set[str] = set()
        for kw in (name_val, email_val, phone_val):
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
                raw["mode"] = "unauthenticated"
                url = f"{host}/api/v1/query"
                payload = {"keyword": name_val}
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

        # -- parse response --
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

        records: list[Any] = []
        if isinstance(response, dict):
            # Batch format: {code, msg, data: [{keyword, data: [...records], total_count}, ...]}
            top_data = response.get("data")
            if isinstance(top_data, list):
                for keyword_group in top_data:
                    if isinstance(keyword_group, dict):
                        inner = keyword_group.get("data")
                        if isinstance(inner, list):
                            records.extend(inner)
            if not records:
                records = [response]
        elif isinstance(response, list):
            records = response

        if len(records) > _MAX_RECORDS:
            _log(f"capping {len(records)} records to {_MAX_RECORDS}")
            records = records[:_MAX_RECORDS]

        if not records:
            _log("empty result set — no breach records found")
            gaps.append("No breach records found for the supplied identifiers")
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"No breach records found for {name_val}.",
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
        all_businesses: dict[str, list[str]] = {}  # company name -> [roles]

        for record in records:
            if not isinstance(record, dict):
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

            # Parse other_info for business associations and embedded phones
            other_info_raw = record.get("other_info") or ""
            if isinstance(other_info_raw, str) and other_info_raw.strip():
                parsed_info = _parse_other_info(other_info_raw)
                if parsed_info["phone"] and parsed_info["phone"] not in all_phones:
                    all_phones.append(parsed_info["phone"])
                if parsed_info["business"]:
                    biz = parsed_info["business"]
                    if biz not in all_businesses:
                        all_businesses[biz] = []
                    if parsed_info["role"] and parsed_info["role"] not in all_businesses[biz]:
                        all_businesses[biz].append(parsed_info["role"])

            for s in _extract_strings(record):
                if _is_email(s) and s not in all_emails:
                    all_emails.append(s)
                elif _is_phone(s) and s not in all_phones:
                    all_phones.append(s)

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
            f"{len(all_usernames)} username(s), {len(all_businesses)} business(es)"
        )

        # -- build signals / facts --
        breach_label = ", ".join((all_breaches + all_domains)[:5]) or "breach database"

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
        ctx_email_lower = email_val.lower()
        new_emails = [e for e in all_emails if e.lower() != ctx_email_lower]
        for email in new_emails:
            signals.append(Signal(
                kind="contact",
                tag="email",
                value=email,
                source=source_base,
                confidence=0.70,
                notes="Email address recovered from breach records",
            ))
        # Emit the first discovered email as a contact signal if none existed
        if new_emails and not email_val:
            signals.append(Signal(
                kind="contact",
                tag="email",
                value=new_emails[0],
                source=source_base,
                confidence=0.55,
                notes="First email discovered from breach records",
            ))
            _log(f"emitting email signal: {new_emails[0]}")

        # Contact signals — phones discovered
        ctx_phone_digits = "".join(c for c in phone_val if c.isdigit())
        new_phones = [
            p for p in all_phones
            if "".join(c for c in p if c.isdigit()) != ctx_phone_digits
        ]
        for phone in new_phones:
            signals.append(Signal(
                kind="contact",
                tag="phone",
                value=phone,
                source=source_base,
                confidence=0.70,
                notes="Phone number recovered from breach records",
            ))
        if new_phones and not phone_val:
            signals.append(Signal(
                kind="contact",
                tag="phone",
                value=new_phones[0],
                source=source_base,
                confidence=0.55,
                notes="First phone discovered from breach records",
            ))
            _log(f"emitting phone signal: {new_phones[0]}")

        # Contact signals — usernames / aliases
        for username in all_usernames[:10]:
            signals.append(Signal(
                kind="contact",
                value=username,
                source=source_base,
                confidence=0.65,
                notes="Username / alias found in breach records — may correspond to social profiles",
            ))

        # Business association signals
        for biz, roles in all_businesses.items():
            role_note = ", ".join(roles) if roles else "associated"
            signals.append(Signal(
                kind="business",
                value=biz,
                source=source_base,
                confidence=0.80,
                notes=f"Role(s): {role_note}. Found in breach intelligence records.",
            ))

        if not signals and not facts:
            gaps.append("Breach records returned but no actionable contact or risk data could be extracted")
            return ModuleResult(
                name=self.name,
                status="no_data",
                summary=f"Breach records found for {name_val} but contained no usable contact or risk fields.",
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
        if all_businesses:
            biz_names = list(all_businesses.keys())
            summary_parts.append(f"{len(biz_names)} business association(s): {', '.join(biz_names[:3])}")

        return ModuleResult(
            name=self.name,
            status="ok",
            summary=" | ".join(summary_parts),
            signals=signals,
            facts=facts,
            gaps=gaps,
            raw=raw,
            duration_s=time.monotonic() - t0,
        )
