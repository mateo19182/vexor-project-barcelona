"""Local CLI for running the enrichment pipeline without booting the API.

Usage:
    uv run enrich path/to/case.json
    cat case.json | uv run enrich -
    uv run enrich case.json --only boe borme       # just those modules
    uv run enrich --list                           # print module names

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
from app.pipeline.modules import REGISTRY


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
        nargs="?",
        help="Path to a JSON file with a Case, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List every registered module (name + required inputs) and exit.",
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
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        metavar="MODULE",
        help=(
            "Run only the named module(s) (e.g. `--only boe borme`). "
            "Dependencies aren't auto-included; unmet `requires` → skipped."
        ),
    )
    args = parser.parse_args(argv)

    if args.list:
        for m in REGISTRY:
            req = ", ".join(m.requires) if m.requires else "—"
            print(f"{m.name:<22} requires: {req}")
        return 0

    if not args.input:
        parser.error("input is required unless --list is passed")

    # `fresh`: None (flag absent) → use cache everywhere
    #         []  (flag alone)   → recompute every module
    #         [...] (with names) → recompute only those modules
    if args.fresh is None:
        fresh: bool | set[str] = False
    elif len(args.fresh) == 0:
        fresh = True
    else:
        fresh = set(args.fresh)

    only = set(args.only) if args.only else None

    raw = _read_input(args.input)
    case = Case.model_validate_json(raw)
    try:
        result = asyncio.run(run_enrichment(case, fresh=fresh, only=only))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not args.no_summary:
        sys.stderr.write(render_summary(result))
        sys.stderr.write("\n")

    json.dump(result.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
