"""Jooble job-search enrichment.

Calls the Jooble API to find active job listings that match a person's
LinkedIn headline (job title) in their reported city. The results help a
debt collector assess:

  * Whether the claimed role actually has an active job market locally.
  * What salary range similar professionals earn (income proxy).
  * Whether the debtor is likely employed vs. in a saturated/non-existent market.

API contract (POST http://jooble.org/api/<key>):
  Request body: {"keywords": "<job title>", "location": "<city>"}
  Response:     {"totalCount": N, "jobs": [{title, company, location,
                  salary, snippet, link, updated}, ...]}
"""

from __future__ import annotations

import http.client
import json
import sys
from typing import Any

# The API key provided is registered on es.jooble.org. Other regional
# subdomains (fr., pl., etc.) return 403 with this key, so we always
# use es.jooble.org regardless of the debtor's country. Jooble still
# accepts any location string — "Paris", "Warsaw", etc. — and searches
# its global index via the ES endpoint.
_JOOBLE_HOST = "es.jooble.org"
JOOBLE_TIMEOUT_S = 15


def _host_for_country(country_code: str | None) -> str:  # noqa: ARG001
    return _JOOBLE_HOST


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _extract_job_title(headline: str) -> str:
    """Strip the company part from a LinkedIn headline.

    Most LinkedIn headlines follow "<Title> at <Company>" or similar
    separators. We take only the part before the separator so the Jooble
    query is tighter.

    Examples:
      "CEO at LinkedIn"           → "CEO"
      "Software Engineer @ Google"→ "Software Engineer"
      "Desarrollador Web en Acme" → "Desarrollador Web"
      "Freelance Consultant"      → "Freelance Consultant"
    """
    for sep in (" at ", " en ", " @ ", " | ", " · ", " - "):
        lower = headline.lower()
        idx = lower.find(sep.lower())
        if idx != -1:
            return headline[:idx].strip()
    return headline.strip()


def _fetch_sync(api_key: str, body_str: str, host: str) -> dict[str, Any]:
    """Blocking HTTP call to Jooble. Runs in a thread executor."""
    headers = {"Content-type": "application/json"}
    try:
        conn = http.client.HTTPConnection(host, timeout=JOOBLE_TIMEOUT_S)
        conn.request("POST", f"/api/{api_key}", body_str, headers)
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
        conn.close()
    except Exception as exc:
        return {"jobs": [], "total_count": 0, "errors": [f"HTTP error: {exc}"]}

    if status != 200:
        return {
            "jobs": [],
            "total_count": 0,
            "errors": [f"Jooble returned HTTP {status}"],
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"jobs": [], "total_count": 0, "errors": [f"Bad JSON: {exc}"]}

    jobs_raw = data.get("jobs") or []
    total = data.get("totalCount") or len(jobs_raw)

    jobs = [
        {
            "title": j.get("title", "").strip(),
            "company": j.get("company", "").strip(),
            "location": j.get("location", "").strip(),
            "salary": j.get("salary", "").strip(),
            "snippet": j.get("snippet", "").strip(),
            "link": j.get("link", "").strip(),
            "updated": j.get("updated", "").strip(),
        }
        for j in jobs_raw
    ]

    return {"jobs": jobs, "total_count": total, "errors": []}


async def enrich_jooble(
    headline: str,
    city: str,
    api_key: str,
    max_results: int = 10,
    country_code: str | None = None,
) -> dict[str, Any]:
    """Search Jooble for jobs matching *headline* in *city*.

    Always returns a dict — never raises. On failure the dict has an
    ``errors`` list and empty ``jobs``.
    """
    import asyncio

    job_title = _extract_job_title(headline)
    host = _host_for_country(country_code)
    body = json.dumps(
        {"keywords": job_title, "location": city, "resultonpage": max_results}
    )

    _log(f"[jooble] searching '{job_title}' in '{city}' via {host}…")

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_sync, api_key, body, host
        )
    except Exception as exc:
        return {
            "job_title_used": job_title,
            "jobs": [],
            "total_count": 0,
            "errors": [f"Executor error: {exc}"],
        }

    result["job_title_used"] = job_title
    _log(
        f"[jooble] got {result['total_count']} total / "
        f"{len(result['jobs'])} returned, "
        f"{len(result['errors'])} error(s)"
    )
    return result
