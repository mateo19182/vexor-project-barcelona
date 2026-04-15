"""Local CLI for running the enrichment pipeline without booting the API.

Usage:
    uv run enrich path/to/case.json
    cat case.json | uv run enrich -
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.main import enrich
from app.models import Case


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
    args = parser.parse_args(argv)

    raw = _read_input(args.input)
    case = Case.model_validate_json(raw)
    result = asyncio.run(enrich(case))

    json.dump(result.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
