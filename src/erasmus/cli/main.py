from __future__ import annotations

import argparse
import json

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

    mission = sub.add_parser("mission-create")
    mission.add_argument("--title", required=True)
    mission.add_argument("--objective", required=True)
    mission.add_argument("--success", default="Defined outcome achieved")
    mission.add_argument("--risk", type=float, default=0.0)

    review = sub.add_parser("review")
    review.add_argument("--proposition", required=True)

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
        ]
        output = {
            table: store.db.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }
        print(json.dumps(output, indent=2))
    elif args.cmd == "sleep":
        print(json.dumps(consolidate(store), indent=2))
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


if __name__ == "__main__":
    main()
