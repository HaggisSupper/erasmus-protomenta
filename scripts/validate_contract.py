#!/usr/bin/env python3
"""Governance control-plane validator for agent task contracts.

Usage
-----
    python scripts/validate_contract.py PATH_TO_CONTRACT.json [OPTIONS]

Options
-------
    --head-sha SHA          Current HEAD SHA of the branch (40 hex chars).
                            If omitted, stale-SHA check is skipped and a
                            warning is emitted.
    --branch-writers W1,W2  Comma-separated list of GitHub usernames with
                            write access to the branch.  If omitted, the
                            shared-branch check is skipped.
    --repair-attempts N     Number of materially-similar failed repair
                            attempts so far (default: 0).  When N >= 3,
                            the contract is immediately abandoned.
    --json                  Emit output as JSON instead of human-readable text.

Exit codes
----------
    0   ready
    1   blocked
    2   repair_required
    3   awaiting_human
    4   abandoned
    10  usage error / file not found

Windows (PowerShell)
--------------------
    py -3.12 scripts\\validate_contract.py contracts\\fixtures\\valid_task.json

Deterministic-first: no LLM, no daemon, no Docker, no OAuth.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from any working directory.
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from erasmus.governance import (  # noqa: E402
    ReadinessStatus,
    validate_task_contract_file,
)

_EXIT_CODES: dict[ReadinessStatus, int] = {
    ReadinessStatus.READY: 0,
    ReadinessStatus.BLOCKED: 1,
    ReadinessStatus.REPAIR_REQUIRED: 2,
    ReadinessStatus.AWAITING_HUMAN: 3,
    ReadinessStatus.ABANDONED: 4,
}

_ANSI: dict[str, str] = {
    "ready": "\033[32m",       # green
    "blocked": "\033[31m",     # red
    "repair_required": "\033[33m",  # yellow
    "awaiting_human": "\033[34m",   # blue
    "abandoned": "\033[35m",   # magenta
    "reset": "\033[0m",
}


def _ansi(status: str, text: str) -> str:
    """Wrap text in ANSI colour if stdout is a TTY."""
    if sys.stdout.isatty():
        return f"{_ANSI.get(status, '')}{text}{_ANSI['reset']}"
    return text


def _print_result(result, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    status_str = str(result.status)
    print(f"\nGovernance status: {_ansi(status_str, status_str.upper())}\n")

    if result.errors:
        print("Errors:")
        for e in result.errors:
            print(f"  [!] {e}")
        print()

    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  [~] {w}")
        print()

    if result.provable:
        print("Provable by this validator:")
        for p in result.provable:
            print(f"  [+] {p}")
        print()

    if result.unresolvable:
        print("Requires human judgment (cannot be proven by validator):")
        for u in result.unresolvable:
            print(f"  [?] {u}")
        print()

    if result.repair_count > 0:
        print(f"Repair attempts so far: {result.repair_count} / 3\n")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Deterministic governance validator for agent task contracts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("contract", help="Path to the task contract JSON file.")
    parser.add_argument(
        "--head-sha",
        metavar="SHA",
        default=None,
        help="Current HEAD SHA (40 hex chars). Omit to skip stale-SHA check.",
    )
    parser.add_argument(
        "--branch-writers",
        metavar="W1,W2,...",
        default=None,
        help="Comma-separated GitHub usernames with write access to the branch.",
    )
    parser.add_argument(
        "--repair-attempts",
        metavar="N",
        type=int,
        default=0,
        help="Number of prior materially-similar repair attempts (default: 0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit output as machine-readable JSON.",
    )

    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    if not contract_path.exists():
        print(f"Error: contract file not found: {contract_path}", file=sys.stderr)
        return 10

    writers: list[str] | None = None
    if args.branch_writers:
        writers = [w.strip() for w in args.branch_writers.split(",") if w.strip()]

    result = validate_task_contract_file(
        contract_path,
        current_head_sha=args.head_sha,
        branch_writers=writers,
        repair_attempts=args.repair_attempts,
    )

    _print_result(result, as_json=args.as_json)
    return _EXIT_CODES.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
