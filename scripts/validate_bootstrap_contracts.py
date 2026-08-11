#!/usr/bin/env python3
"""Validator for bootstrap control-plane contracts.

Usage:
    python scripts\\validate_bootstrap_contracts.py contracts\\bootstrap\\fixtures\\valid-minimal-windows.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from erasmus.bootstrap_contracts import ValidationResult, validate_bootstrap_contract_file


def _cli_errors(*messages: str) -> None:
    for message in messages:
        print(message)
    sys.exit(1)


def _load_fixture(path: Path) -> dict:
    payload = path.read_text(encoding="utf-8")
    return json.loads(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate bootstrap contract fixtures and schemas.")
    parser.add_argument("fixture_path", metavar="FIXTURE_PATH", help="Path to a bootstrap contract fixture JSON.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output with deterministic fields.",
    )
    args = parser.parse_args(argv)

    fixture_path = Path(args.fixture_path)
    if not fixture_path.exists():
        _cli_errors(f"fixture not found: {fixture_path}")

    try:
        # Load as pure structure to surface JSON parsing errors before contract validation.
        _load_fixture(fixture_path)
    except Exception as exc:
        _cli_errors(f"invalid fixture JSON: {exc}")

    result: ValidationResult = validate_bootstrap_contract_file(fixture_path)
    if not result.ok:
        if args.json:
            print(json.dumps(result.as_dict(), indent=2))
        else:
            print("Bootstrap contract validation failed.")
            for error in result.errors:
                print(f"  [!] {error}")
            if result.warnings:
                print("Warnings:")
                for warning in result.warnings:
                    print(f"  [~] {warning}")
        return 1

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print("Bootstrap contract validation succeeded.")
        print(f"startup_order: {', '.join(result.derived_startup_order)}")
        print(f"shutdown_order: {', '.join(result.derived_shutdown_order)}")
        if result.warnings:
            print("Warnings:")
            for warning in result.warnings:
                print(f"  [~] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
