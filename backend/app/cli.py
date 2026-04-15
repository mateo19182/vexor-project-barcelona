"""Local CLI for running the enrichment pipeline without booting the API.

Usage:
    uv run enrich path/to/case.json
    cat case.json | uv run enrich -

Stdout is JSON (pipe-friendly). Stderr carries the live audit stream during
the run and a compact summary block at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.main import run_enrichment
from app.models import Case
from app.pipeline.audit import render_summary


def _read_input(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    return Path(source).read_text()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enrich",
        description="Run the debtor enrichment pipeline on a local case JSON.",
    )
    parser.add_argument(
        "input",
        help="Path to a JSON file with a Case, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip the end-of-run audit summary on stderr.",
    )
    parser.add_argument(
        "--fresh",
        nargs="*",
        default=None,
        metavar="MODULE",
        help=(
            "Bypass the per-module result cache. With no args, every module "
            "recomputes. Pass one or more module names (e.g. "
            "`--fresh osint_web instagram`) to invalidate only those."
        ),
    )
    args = parser.parse_args(argv)

    # `fresh`: None (flag absent) → use cache everywhere
    #         []  (flag alone)   → recompute every module
    #         [...] (with names) → recompute only those modules
    if args.fresh is None:
        fresh: bool | set[str] = False
    elif len(args.fresh) == 0:
        fresh = True
    else:
        fresh = set(args.fresh)

    raw = _read_input(args.input)
    case = Case.model_validate_json(raw)
    result = asyncio.run(run_enrichment(case, fresh=fresh))

    if not args.no_summary:
        sys.stderr.write(render_summary(result))
        sys.stderr.write("\n")

    json.dump(result.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
