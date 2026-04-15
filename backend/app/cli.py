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

from app.main import enrich
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
    args = parser.parse_args(argv)

    raw = _read_input(args.input)
    case = Case.model_validate_json(raw)
    result = asyncio.run(enrich(case))

    if not args.no_summary:
        sys.stderr.write(render_summary(result))
        sys.stderr.write("\n")

    json.dump(result.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
