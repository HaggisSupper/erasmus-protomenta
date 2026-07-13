"""Pinned entrypoint for the governed pytest capability."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *(sys.argv[1:] or ["tests"])],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
