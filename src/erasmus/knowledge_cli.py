from __future__ import annotations

import argparse
import json
from pathlib import Path

from .knowledge_runtime import KnowledgeRuntime
from .store import Store


def _print(value) -> None:
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog="erasmus-knowledge")
    parser.add_argument("--db", default="state/erasmus.db")
    parser.add_argument("--artifact-root", default="state/knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")

    policy_eval = sub.add_parser("policy-evaluate")
    policy_eval.add_argument("operation")
    policy_eval.add_argument("--actor", required=True)
    policy_eval.add_argument("--scope", default='{"visibility":"private","tenant":"local","project":null,"domain":null,"labels":[]}')
    policy_eval.add_argument("--dry-run", action="store_true")

    source_add = sub.add_parser("source-add")
    source_add.add_argument("path")
    source_add.add_argument("--media-type", required=True)
    source_add.add_argument("--actor", required=True)
    source_add.add_argument("--authority", default="knowledge:source-register")

    candidate_list = sub.add_parser("candidate-list")
    candidate_list.add_argument("--disposition")

    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("query")
    retrieve.add_argument("--channel", default="private")
    retrieve.add_argument("--limit", type=int, default=8)
    retrieve.add_argument("--actor", required=True)
    retrieve.add_argument("--authority", default="knowledge:read")

    maintenance = sub.add_parser("maintenance")
    maintenance.add_argument("--actor", default="process:maintenance")
    maintenance.add_argument("--authority", default="knowledge:maintain")

    args = parser.parse_args()
    store = Store(args.db)
    store.init()
    rt = KnowledgeRuntime(store, args.artifact_root)

    if args.cmd == "status":
        _print(rt.status())
    elif args.cmd == "policy-evaluate":
        _print(rt.evaluate_policy(args.operation, args.actor, json.loads(args.scope), args.dry_run))
    elif args.cmd == "source-add":
        path = Path(args.path).resolve()
        scope = {"visibility":"private","tenant":"local","project":None,"domain":None,"labels":[]}
        _print(rt.register_source_bytes(path.read_bytes(), str(path), args.media_type, scope, args.actor, args.authority))
    elif args.cmd == "candidate-list":
        if args.disposition:
            rows = store.db.execute("SELECT * FROM knowledge_candidates WHERE candidate_disposition=? ORDER BY created_at,candidate_id", (args.disposition,)).fetchall()
        else:
            rows = store.db.execute("SELECT * FROM knowledge_candidates ORDER BY created_at,candidate_id").fetchall()
        _print({"contract":"erasmus.knowledge-candidate-list/v1","items":[dict(row) for row in rows]})
    elif args.cmd == "retrieve":
        _print(rt.retrieve(args.query, args.channel, args.limit, args.actor, args.authority))
    elif args.cmd == "maintenance":
        _print(rt.run_maintenance(args.actor, args.authority))


if __name__ == "__main__":
    main()
