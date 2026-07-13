"""Read-only JSON CLI for the governed SQLite query capability."""
from __future__ import annotations

import argparse
import json
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("query")
    args = parser.parse_args()
    statement = args.query.lstrip().upper()
    if not statement.startswith(("SELECT ", "PRAGMA ", "WITH ")):
        raise SystemExit("only read-only SELECT, PRAGMA, or WITH statements are allowed")
    db = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in db.execute(args.query).fetchall()]
    finally:
        db.close()
    print(json.dumps(rows, sort_keys=True))


if __name__ == "__main__":
    main()
