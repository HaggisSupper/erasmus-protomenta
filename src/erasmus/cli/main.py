from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path

from erasmus.checkpoint import load_latest_checkpoint
from erasmus.missions import create_mission
from erasmus.review import tenth_man_prompt
from erasmus.sleep import consolidate
from erasmus.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="erasmus")
    parser.add_argument("--db", default="state/erasmus.db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("sleep")
    sub.add_parser("checkpoint")
    sub.add_parser("integrity")

    mission = sub.add_parser("mission-create")
    mission.add_argument("--title", required=True)
    mission.add_argument("--objective", required=True)
    mission.add_argument("--success", default="Defined outcome achieved")
    mission.add_argument("--risk", type=float, default=0.0)

    review = sub.add_parser("review")
    review.add_argument("--proposition", required=True)

    backup_cmd = sub.add_parser("backup", help="Back up the database to a file.")
    backup_cmd.add_argument("dest", help="Destination file path.")

    restore_cmd = sub.add_parser("restore", help="Restore the database from a backup.")
    restore_cmd.add_argument("src", help="Source backup file path.")

    args = parser.parse_args()
    store = Store(args.db)
    store.init()

    if args.cmd == "init":
        print(f"initialized {args.db}")

    elif args.cmd == "status":
        tables = [
            "events",
            "propositions",
            "missions",
            "experience_candidates",
            "immune_state",
            "checkpoints",
            "sessions",
        ]
        output = {
            table: store.db.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608
            ).fetchone()[0]
            for table in tables
        }
        versions = [
            row[0]
            for row in store.db.execute(
                "SELECT version FROM schema_version ORDER BY version"
            ).fetchall()
        ]
        output["schema_versions"] = versions
        print(json.dumps(output, indent=2))

    elif args.cmd == "sleep":
        print(json.dumps(consolidate(store), indent=2))

    elif args.cmd == "checkpoint":
        cp = load_latest_checkpoint(store)
        if cp is None:
            print(json.dumps(None))
        else:
            print(json.dumps(asdict(cp), indent=2))

    elif args.cmd == "integrity":
        results = store.integrity_check()
        print(json.dumps(results, indent=2))

    elif args.cmd == "mission-create":
        print(
            create_mission(
                store,
                args.title,
                args.objective,
                args.success,
                args.risk,
            )
        )

    elif args.cmd == "review":
        print(tenth_man_prompt(args.proposition))

    elif args.cmd == "backup":
        dest = Path(args.dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup_db = sqlite3.connect(str(dest))
        try:
            store.db.backup(backup_db)
        finally:
            backup_db.close()
        print(f"backed up to {dest}")

    elif args.cmd == "restore":
        src = Path(args.src)
        if not src.exists():
            raise SystemExit(f"error: backup file not found: {src}")
        src_db = sqlite3.connect(str(src))
        try:
            src_db.backup(store.db)
        finally:
            src_db.close()
        print(f"restored from {src}")


if __name__ == "__main__":
    main()
