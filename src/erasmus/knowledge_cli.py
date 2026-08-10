from __future__ import annotations

import argparse
import json
from pathlib import Path

from .knowledge_system import KnowledgeSystem, OpenAIEmbeddingAdapter
from .runtime import LocalRuntimeConfig, OpenAICompatibleRuntime
from .store import Store


def _print(value) -> None:
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _scope() -> dict:
    return {"visibility": "private", "tenant": "local", "project": None, "domain": None, "labels": []}


def _runtime_adapter(path: str) -> OpenAIEmbeddingAdapter:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return OpenAIEmbeddingAdapter(OpenAICompatibleRuntime(LocalRuntimeConfig.from_mapping(raw)))


def main() -> None:
    parser = argparse.ArgumentParser(prog="erasmus-knowledge")
    parser.add_argument("--db", default="state/erasmus.db")
    parser.add_argument("--artifact-root", default="state/knowledge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")

    policy_register = sub.add_parser("policy-register")
    policy_register.add_argument("policy_set_id")
    policy_register.add_argument("rules_json")
    policy_register.add_argument("--actor", required=True)
    policy_register.add_argument("--authority", default="knowledge:policy-admin")
    policy_activate = sub.add_parser("policy-activate")
    policy_activate.add_argument("policy_set_id")
    policy_activate.add_argument("digest")
    policy_activate.add_argument("--actor", required=True)
    policy_activate.add_argument("--authority", default="knowledge:policy-admin")
    policy_eval = sub.add_parser("policy-evaluate")
    policy_eval.add_argument("operation")
    policy_eval.add_argument("--actor", required=True)
    policy_eval.add_argument("--scope", default=json.dumps(_scope()))
    policy_eval.add_argument("--dry-run", action="store_true")

    source_add = sub.add_parser("source-add")
    source_add.add_argument("path")
    source_add.add_argument("--media-type", required=True)
    source_add.add_argument("--actor", required=True)
    source_add.add_argument("--authority", default="knowledge:source-register")

    candidate_list = sub.add_parser("candidate-list")
    candidate_list.add_argument("--disposition")

    publish = sub.add_parser("publish")
    publish.add_argument("channel")
    publish.add_argument("revision_ids", nargs="+")
    publish.add_argument("--actor", required=True)
    publish.add_argument("--authority", default="knowledge:publish")

    fts_build = sub.add_parser("fts-build")
    fts_build.add_argument("snapshot_id")
    vector_build = sub.add_parser("vector-build")
    vector_build.add_argument("snapshot_id")
    vector_build.add_argument("runtime_config")
    graph_build = sub.add_parser("graph-build")
    graph_build.add_argument("snapshot_id")

    retrieve = sub.add_parser("retrieve")
    retrieve.add_argument("query")
    retrieve.add_argument("--channel", default="private")
    retrieve.add_argument("--limit", type=int, default=8)
    retrieve.add_argument("--actor", required=True)
    retrieve.add_argument("--authority", default="knowledge:read")
    retrieve.add_argument("--runtime-config")

    freshness = sub.add_parser("freshness-assess")
    freshness.add_argument("source_id")
    freshness.add_argument("state")
    freshness.add_argument("materiality")
    freshness.add_argument("--stale-after")
    freshness.add_argument("--actor", required=True)
    freshness.add_argument("--authority", default="knowledge:revalidate")
    invalidate = sub.add_parser("invalidate-source")
    invalidate.add_argument("source_id")
    invalidate.add_argument("reason")
    invalidate.add_argument("--actor", required=True)
    invalidate.add_argument("--authority", default="knowledge:serve-control")

    intake_enqueue = sub.add_parser("intake-enqueue")
    intake_enqueue.add_argument("producer")
    intake_enqueue.add_argument("payload_json")
    intake_enqueue.add_argument("--max-pending", type=int, default=1000)
    intake_enqueue.add_argument("--actor", required=True)
    intake_enqueue.add_argument("--authority", default="knowledge:intake")
    intake_list = sub.add_parser("intake-list")
    intake_list.add_argument("--state")
    for command, enabled in (("intake-start", True), ("intake-stop", False)):
        item = sub.add_parser(command)
        item.set_defaults(intake_enabled=enabled)
        item.add_argument("--actor", required=True)
        item.add_argument("--authority", default="knowledge:intake-admin")

    maintenance = sub.add_parser("maintenance")
    maintenance.add_argument("--actor", default="process:maintenance")
    maintenance.add_argument("--authority", default="knowledge:maintain")

    args = parser.parse_args()
    store = Store(args.db)
    store.init()
    store.init_phase3()
    system = KnowledgeSystem(store, args.artifact_root)

    if args.cmd == "status":
        _print(system.status())
    elif args.cmd == "policy-register":
        rules = json.loads(Path(args.rules_json).read_text(encoding="utf-8"))
        _print({"digest": system.register_policy_set(args.policy_set_id, rules, args.actor, args.authority)})
    elif args.cmd == "policy-activate":
        system.activate_policy_set(args.policy_set_id, args.digest, args.actor, args.authority)
        _print({"contract": "erasmus.knowledge-policy-activation/v1", "policy_set_id": args.policy_set_id, "digest": args.digest, "state": "active"})
    elif args.cmd == "policy-evaluate":
        _print(system.evaluate_policy(args.operation, args.actor, json.loads(args.scope), args.dry_run))
    elif args.cmd == "source-add":
        path = Path(args.path).resolve()
        _print(system.register_source_bytes(path.read_bytes(), str(path), args.media_type, _scope(), args.actor, args.authority))
    elif args.cmd == "candidate-list":
        if args.disposition:
            rows = store.db.execute("SELECT * FROM knowledge_candidates WHERE candidate_disposition=? ORDER BY created_at,candidate_id", (args.disposition,)).fetchall()
        else:
            rows = store.db.execute("SELECT * FROM knowledge_candidates ORDER BY created_at,candidate_id").fetchall()
        _print({"contract": "erasmus.knowledge-candidate-list/v1", "items": [dict(row) for row in rows]})
    elif args.cmd == "publish":
        _print(system.publish_okf_snapshot(args.channel, args.revision_ids, args.actor, args.authority))
    elif args.cmd == "fts-build":
        _print(system.build_fts_projection(args.snapshot_id))
    elif args.cmd == "vector-build":
        _print(system.build_vector_projection(args.snapshot_id, _runtime_adapter(args.runtime_config)))
    elif args.cmd == "graph-build":
        _print(system.build_graph_projection(args.snapshot_id))
    elif args.cmd == "retrieve":
        adapter = _runtime_adapter(args.runtime_config) if args.runtime_config else None
        _print(system.hybrid_retrieve(args.query, args.channel, args.limit, args.actor, args.authority, adapter))
    elif args.cmd == "freshness-assess":
        _print(system.assess_freshness(args.source_id, args.state, args.materiality, args.actor, args.authority, args.stale_after))
    elif args.cmd == "invalidate-source":
        _print(system.invalidate_source(args.source_id, args.reason, args.actor, args.authority))
    elif args.cmd == "intake-enqueue":
        _print(system.enqueue_intake(args.producer, json.loads(args.payload_json), args.actor, args.authority, args.max_pending))
    elif args.cmd == "intake-list":
        _print({"contract": "erasmus.knowledge-intake-list/v1", "items": system.list_intake(args.state)})
    elif args.cmd in {"intake-start", "intake-stop"}:
        system.set_intake_state(args.intake_enabled, args.actor, args.authority)
        _print({"contract": "erasmus.knowledge-intake-control/v1", "enabled": args.intake_enabled})
    elif args.cmd == "maintenance":
        _print(system.run_maintenance(args.actor, args.authority))


if __name__ == "__main__":
    main()
