from __future__ import annotations

import argparse
import base64
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from erasmus.capability_graph import (
    CapabilityGraph,
    load_manifest,
    validate_manifest,
)
from erasmus.capability_runtime import (
    CapabilityRuntime,
    hash_content,
    query_sqlite_fts,
    validate_json_schema,
)
from erasmus.checkpoint import load_latest_checkpoint
from erasmus.immune import ImmuneCascade
from erasmus.ledger import EpistemicLedger
from erasmus.missions import MissionEngine, create_mission
from erasmus.review import tenth_man_prompt
from erasmus.sleep import consolidate, decide_candidate, sleep_report
from erasmus.store import Store
from erasmus.tool_registry import (
    ToolRegistry,
    load_tool_manifest,
    validate_toolchain_document,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="erasmus")
    parser.add_argument("--db", default="state/erasmus.db")
    parser.add_argument("--tool-cache", default="state/tool-cache")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("sleep")
    sleep_report_cmd = sub.add_parser("sleep-report")
    sleep_report_cmd.add_argument("run_id", type=int)
    sleep_decide = sub.add_parser("sleep-decide")
    sleep_decide.add_argument("candidate_id", type=int)
    sleep_decide.add_argument("decision", choices=("approved", "rejected"))
    sleep_decide.add_argument("target", choices=("belief", "skill"))
    sleep_decide.add_argument("evidence_id", type=int)
    sleep_decide.add_argument("--actor", required=True)
    sleep_decide.add_argument("--authority", required=True)
    sleep_decide.add_argument("--reason", required=True)
    sub.add_parser("checkpoint")
    sub.add_parser("integrity")

    mission = sub.add_parser("mission-create")
    mission.add_argument("--contract")
    mission.add_argument("--title")
    mission.add_argument("--objective")
    mission.add_argument("--success", default="Defined outcome achieved")
    mission.add_argument("--risk", type=float, default=0.0)

    mission_inspect = sub.add_parser("mission-inspect")
    mission_inspect.add_argument("mission_id", type=int)
    mission_authorize = sub.add_parser("mission-authorize")
    mission_authorize.add_argument("mission_id", type=int)
    mission_authorize.add_argument("--actor", required=True)
    mission_authorize.add_argument("--evidence", action="append", default=[])
    mission_authorize.add_argument("--approval-id", type=int)
    mission_authorize.add_argument("--deny", action="store_true")
    for command in (
        "mission-run-one", "mission-pause", "mission-resume",
        "mission-cancel", "mission-rollback",
    ):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("mission_id", type=int)

    review = sub.add_parser("review")
    review.add_argument("--proposition", required=True)

    immune_process = sub.add_parser("immune-process")
    immune_process.add_argument("event")
    immune_process.add_argument("--authority", required=True)
    immune_inspect = sub.add_parser("immune-inspect")
    immune_inspect.add_argument("incident_id", type=int)
    sub.add_parser("immune-agents")
    immune_false_positive = sub.add_parser("immune-false-positive")
    immune_false_positive.add_argument("incident_id", type=int)
    immune_false_positive.add_argument("detector")
    immune_false_positive.add_argument("--agent-id")
    immune_false_positive.add_argument("--reason", required=True)
    immune_false_positive.add_argument("--actor", required=True)
    immune_false_positive.add_argument("--authority", required=True)
    immune_retire = sub.add_parser("immune-retire")
    immune_retire.add_argument("agent_id")
    immune_retire.add_argument("--reason", required=True)
    immune_retire.add_argument("--actor", required=True)
    immune_retire.add_argument("--authority", required=True)

    evidence_add = sub.add_parser("ledger-evidence-add")
    evidence_add.add_argument("content")
    evidence_add.add_argument("--type", required=True)
    evidence_add.add_argument("--source-kind", required=True)
    evidence_add.add_argument("--provenance", required=True)
    evidence_add.add_argument("--trust", required=True)
    evidence_add.add_argument("--effective-date", required=True)
    evidence_add.add_argument("--scope", default="global")
    evidence_add.add_argument("--actor", required=True)
    evidence_add.add_argument("--authority", required=True)
    evidence_add.add_argument("--source-event-id", type=int)
    evidence_add.add_argument("--supersedes-id", type=int)

    ledger_propose = sub.add_parser("ledger-propose")
    ledger_propose.add_argument("statement")
    ledger_propose.add_argument("evidence_id", type=int)
    ledger_propose.add_argument("--status", default="speculative")
    ledger_propose.add_argument("--scope", default="global")
    ledger_propose.add_argument("--actor", required=True)
    ledger_propose.add_argument("--authority", required=True)
    ledger_propose.add_argument("--reason", default="proposed for evaluation")

    ledger_transition = sub.add_parser("ledger-transition")
    ledger_transition.add_argument("proposition_id", type=int)
    ledger_transition.add_argument("operation")
    ledger_transition.add_argument("evidence_id", type=int)
    ledger_transition.add_argument("--target")
    ledger_transition.add_argument("--test-id", type=int)
    ledger_transition.add_argument("--actor", required=True)
    ledger_transition.add_argument("--authority", required=True)
    ledger_transition.add_argument("--reason", required=True)

    ledger_confidence = sub.add_parser("ledger-confidence")
    ledger_confidence.add_argument("proposition_id", type=int)
    ledger_confidence.add_argument("confidence", type=float)
    ledger_confidence.add_argument("evidence_id", type=int)
    ledger_confidence.add_argument("--actor", required=True)
    ledger_confidence.add_argument("--authority", required=True)
    ledger_confidence.add_argument("--reason", required=True)

    ledger_supersede = sub.add_parser("ledger-supersede")
    ledger_supersede.add_argument("proposition_id", type=int)
    ledger_supersede.add_argument("replacement_id", type=int)
    ledger_supersede.add_argument("evidence_id", type=int)
    ledger_supersede.add_argument("--actor", required=True)
    ledger_supersede.add_argument("--authority", required=True)
    ledger_supersede.add_argument("--reason", required=True)

    for command in ("ledger-inspect", "ledger-query"):
        ledger_read = sub.add_parser(command)
        ledger_read.add_argument("proposition_id", type=int)

    backup_cmd = sub.add_parser("backup", help="Back up the database to a file.")
    backup_cmd.add_argument("dest", help="Destination file path.")

    restore_cmd = sub.add_parser("restore", help="Restore the database from a backup.")
    restore_cmd.add_argument("src", help="Source backup file path.")

    graph_validate = sub.add_parser("graph-validate")
    graph_validate.add_argument("manifest")

    graph_import = sub.add_parser("graph-import")
    graph_import.add_argument("manifest")

    sub.add_parser("graph-list")

    graph_inspect = sub.add_parser("graph-inspect")
    graph_inspect.add_argument("capability")

    graph_plan = sub.add_parser("graph-plan")
    graph_plan.add_argument("goal")
    graph_plan.add_argument("--authority", action="append", default=[])
    graph_plan.add_argument("--head-sha")

    graph_export = sub.add_parser("graph-export")
    graph_export.add_argument("dest")

    publisher_register = sub.add_parser("tool-publisher-register")
    publisher_register.add_argument("publishers")
    tool_register = sub.add_parser("tool-register")
    tool_register.add_argument("manifest")
    tool_verify = sub.add_parser("tool-verify")
    tool_verify.add_argument("manifest")
    tool_verify.add_argument("artifact")
    tool_install = sub.add_parser("tool-install")
    tool_install.add_argument("manifest")
    tool_install.add_argument("artifact")
    sub.add_parser("tool-list")
    for command in ("tool-inspect", "tool-activate", "tool-deactivate", "tool-quarantine", "tool-revoke", "tool-uninstall"):
        tool = sub.add_parser(command)
        tool.add_argument("tool_id")
        tool.add_argument("version")
        tool.add_argument("target")
    tool_execute = sub.add_parser("tool-execute")
    tool_execute.add_argument("capability_id")
    tool_execute.add_argument("capability_version")
    tool_execute.add_argument("target")
    tool_execute.add_argument("--authority", action="append", default=[])
    tool_execute.add_argument("--side-effect", action="append", default=[])
    tool_execute.add_argument("args", nargs=argparse.REMAINDER)
    tool_health = sub.add_parser("tool-health")
    tool_health.add_argument("tool_id")
    tool_health.add_argument("version")
    tool_health.add_argument("target")
    tool_health.add_argument("--authority", action="append", default=[])
    tool_export = sub.add_parser("tool-export")
    tool_export.add_argument("dest")
    toolchain_validate = sub.add_parser("toolchain-validate")
    toolchain_validate.add_argument("document", default="TOOLCHAIN.md", nargs="?")
    toolchain_validate.add_argument("--manifests", default="tools/manifests")

    args = parser.parse_args()
    store = Store(args.db)
    store.init()

    if args.cmd == "init":
        print(f"initialized {args.db}")

    elif args.cmd == "status":
        tables = [
            "events",
            "propositions",
            "epistemic_evidence",
            "proposition_transitions",
            "missions",
            "experience_candidates",
            "sleep_runs",
            "sleep_items",
            "sleep_candidates",
            "immune_state",
            "immune_incidents",
            "immune_findings",
            "checkpoints",
            "sessions",
            "capabilities",
            "capability_plans",
            "capability_evidence",
            "tool_manifests",
            "tool_audit",
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

    elif args.cmd == "sleep-report":
        print(json.dumps(sleep_report(store, args.run_id), indent=2))

    elif args.cmd == "sleep-decide":
        promotion_id = decide_candidate(
            store, args.candidate_id, args.decision, args.target, args.evidence_id,
            args.actor, args.authority, args.reason,
        )
        print(json.dumps({"promotion_id": promotion_id}, indent=2))

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
        if args.contract:
            raw_contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
            print(MissionEngine(store).create(raw_contract))
        else:
            if not args.title or not args.objective:
                raise SystemExit("mission-create requires --contract or both --title and --objective")
            print(create_mission(store, args.title, args.objective, args.success, args.risk))

    elif args.cmd == "mission-inspect":
        print(json.dumps(MissionEngine(store).inspect(args.mission_id), indent=2))

    elif args.cmd == "mission-authorize":
        engine = MissionEngine(store)
        if args.approval_id is None:
            engine.authorize(args.mission_id, args.actor, args.evidence)
        else:
            engine.decide_approval(
                args.mission_id, args.approval_id, not args.deny, args.actor
            )
        print(json.dumps(engine.inspect(args.mission_id), indent=2))

    elif args.cmd == "mission-run-one":
        engine = _executable_mission_engine(store, args.mission_id)
        print(json.dumps(engine.run_one(args.mission_id), indent=2))

    elif args.cmd == "mission-pause":
        engine = MissionEngine(store)
        engine.pause(args.mission_id)
        print(json.dumps(engine.inspect(args.mission_id), indent=2))

    elif args.cmd == "mission-resume":
        engine = _executable_mission_engine(store, args.mission_id)
        engine.resume(args.mission_id)
        print(json.dumps(engine.inspect(args.mission_id), indent=2))

    elif args.cmd == "mission-cancel":
        engine = MissionEngine(store)
        engine.cancel(args.mission_id)
        print(json.dumps(engine.inspect(args.mission_id), indent=2))

    elif args.cmd == "mission-rollback":
        engine = _executable_mission_engine(store, args.mission_id)
        print(json.dumps(engine.rollback(args.mission_id), indent=2))

    elif args.cmd == "review":
        print(tenth_man_prompt(args.proposition))

    elif args.cmd == "immune-process":
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        print(json.dumps(ImmuneCascade(store).process(event, args.authority), indent=2))

    elif args.cmd == "immune-inspect":
        print(json.dumps(ImmuneCascade(store).inspect(args.incident_id), indent=2))

    elif args.cmd == "immune-agents":
        print(json.dumps(ImmuneCascade(store).list_agents(), indent=2))

    elif args.cmd == "immune-false-positive":
        cascade = ImmuneCascade(store)
        cascade.record_false_positive(
            args.incident_id, args.detector, args.reason, args.actor,
            args.authority, args.agent_id,
        )
        print(json.dumps(cascade.inspect(args.incident_id), indent=2))

    elif args.cmd == "immune-retire":
        cascade = ImmuneCascade(store)
        cascade.retire_agent(args.agent_id, args.reason, args.actor, args.authority)
        print(json.dumps(cascade.list_agents(), indent=2))

    elif args.cmd == "ledger-evidence-add":
        evidence_id = EpistemicLedger(store).add_evidence(
            args.type, args.content, args.source_kind, json.loads(args.provenance),
            args.trust, args.effective_date, args.scope, args.actor, args.authority,
            args.source_event_id, args.supersedes_id,
        )
        print(json.dumps({"evidence_id": evidence_id}, indent=2))

    elif args.cmd == "ledger-propose":
        proposition_id = EpistemicLedger(store).propose(
            args.statement, args.evidence_id, args.actor, args.authority,
            args.scope, args.status, args.reason,
        )
        print(json.dumps({"proposition_id": proposition_id}, indent=2))

    elif args.cmd == "ledger-transition":
        status = EpistemicLedger(store).transition(
            args.proposition_id, args.operation, args.evidence_id,
            args.actor, args.authority, args.reason, args.target, args.test_id,
        )
        print(json.dumps({"status": status}, indent=2))

    elif args.cmd == "ledger-confidence":
        ledger = EpistemicLedger(store)
        ledger.record_confidence(
            args.proposition_id, args.confidence, args.evidence_id,
            args.actor, args.authority, args.reason,
        )
        print(json.dumps(ledger.inspect(args.proposition_id), indent=2))

    elif args.cmd == "ledger-supersede":
        ledger = EpistemicLedger(store)
        ledger.supersede(
            args.proposition_id, args.replacement_id, args.evidence_id,
            args.actor, args.authority, args.reason,
        )
        print(json.dumps(ledger.inspect(args.proposition_id), indent=2))

    elif args.cmd == "ledger-inspect":
        print(json.dumps(EpistemicLedger(store).inspect(args.proposition_id), indent=2))

    elif args.cmd == "ledger-query":
        print(json.dumps(EpistemicLedger(store).query(args.proposition_id), indent=2))

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

    elif args.cmd == "graph-validate":
        errors = validate_manifest(load_manifest(args.manifest))
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        if errors:
            raise SystemExit(1)

    elif args.cmd == "graph-import":
        graph = CapabilityGraph(store.db)
        source = Path(args.manifest)
        if source.is_dir():
            graph.import_bundle(source)
        else:
            graph.import_manifest(load_manifest(source))
        print(json.dumps({"imported": args.manifest, "capabilities": len(graph.list_capabilities())}, indent=2))

    elif args.cmd == "graph-list":
        print(json.dumps(CapabilityGraph(store.db).list_capabilities(), indent=2))

    elif args.cmd == "graph-inspect":
        capability_id, separator, version = args.capability.partition("@")
        print(json.dumps(CapabilityGraph(store.db).inspect(
            capability_id, version if separator else None
        ), indent=2))

    elif args.cmd == "graph-plan":
        plans = CapabilityGraph(store.db).plan(
            args.goal, set(args.authority), args.head_sha
        )
        print(json.dumps([
            {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "steps": [asdict(step) for step in plan.steps],
            }
            for plan in plans
        ], indent=2))
        if not plans:
            raise SystemExit("no valid plan for the declared goal and authority")

    elif args.cmd == "graph-export":
        destination = Path(args.dest)
        CapabilityGraph(store.db).export_bundle(destination)
        print(f"exported to {destination}")

    elif args.cmd == "tool-publisher-register":
        registry = ToolRegistry(store.db, args.tool_cache)
        publishers = json.loads(Path(args.publishers).read_text(encoding="utf-8"))["publishers"]
        for publisher in publishers:
            registry.trust_publisher(
                publisher["key_id"], base64.b64decode(publisher["public_key"]), publisher["owner"]
            )
        print(json.dumps({"trusted_publishers": len(publishers)}, indent=2))

    elif args.cmd == "tool-register":
        ToolRegistry(store.db, args.tool_cache).register(load_tool_manifest(args.manifest))
        print(f"registered {args.manifest}")

    elif args.cmd == "tool-verify":
        manifest = load_tool_manifest(args.manifest)
        ToolRegistry(store.db, args.tool_cache).verify(manifest, args.artifact, manifest["target"])
        print(f"verified {manifest['tool_id']}@{manifest['version']}")

    elif args.cmd == "tool-install":
        manifest = load_tool_manifest(args.manifest)
        path = ToolRegistry(store.db, args.tool_cache).install(manifest, args.artifact)
        print(path)

    elif args.cmd == "tool-list":
        print(json.dumps(ToolRegistry(store.db, args.tool_cache).list(), indent=2))

    elif args.cmd == "tool-inspect":
        print(json.dumps(ToolRegistry(store.db, args.tool_cache).inspect(
            args.tool_id, args.version, args.target
        ), indent=2))

    elif args.cmd == "tool-activate":
        ToolRegistry(store.db, args.tool_cache).activate(args.tool_id, args.version, args.target)
        print(f"activated {args.tool_id}@{args.version}")

    elif args.cmd == "tool-deactivate":
        ToolRegistry(store.db, args.tool_cache).deactivate(args.tool_id, args.version, args.target)
        print(f"deactivated {args.tool_id}@{args.version}")

    elif args.cmd in {"tool-quarantine", "tool-revoke"}:
        lifecycle = "quarantined" if args.cmd == "tool-quarantine" else "revoked"
        ToolRegistry(store.db, args.tool_cache).set_lifecycle(
            args.tool_id, args.version, args.target, lifecycle
        )
        print(f"{lifecycle} {args.tool_id}@{args.version}")

    elif args.cmd == "tool-uninstall":
        ToolRegistry(store.db, args.tool_cache).uninstall(args.tool_id, args.version, args.target)
        print(f"uninstalled {args.tool_id}@{args.version}")

    elif args.cmd == "tool-execute":
        completed = ToolRegistry(store.db, args.tool_cache).execute(
            args.capability_id, args.capability_version, args.target,
            set(args.authority), set(args.side_effect), args.args, Path.cwd(),
        )
        print(json.dumps({"returncode": completed.returncode, "stdout": completed.stdout,
                          "stderr": completed.stderr}, indent=2))
        raise SystemExit(completed.returncode)

    elif args.cmd == "tool-health":
        registry = ToolRegistry(store.db, args.tool_cache)
        inspected = registry.inspect(args.tool_id, args.version, args.target)
        manifest = inspected["manifest"]
        capability = manifest["capabilities"][0]
        completed = registry.execute(
            capability["id"], capability["version"], args.target, set(args.authority),
            set(manifest["side_effects"]), manifest["health_check"], Path.cwd(),
        )
        print(json.dumps({"healthy": completed.returncode == 0}, indent=2))
        raise SystemExit(completed.returncode)

    elif args.cmd == "tool-export":
        destination = Path(args.dest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(ToolRegistry(store.db, args.tool_cache).export(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"exported to {destination}")

    elif args.cmd == "toolchain-validate":
        errors = validate_toolchain_document(args.document, args.manifests)
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
        if errors:
            raise SystemExit(1)


def _executable_mission_engine(store: Store, mission_id: int) -> MissionEngine:
    """Bind reviewed in-process references; lifecycle state remains authoritative."""
    inspection = MissionEngine(store).inspect(mission_id)
    runtime = CapabilityRuntime(store)
    handlers = {
        "validate_json_schema": ("jsonschema_validator", validate_json_schema),
        "hash_content": ("sha256_hasher", hash_content([Path.cwd()])),
        "query_sqlite_fts": ("sqlite_fts_reader", query_sqlite_fts([Path.cwd()])),
    }
    steps = inspection["contract"]["steps"]
    invocations = [*steps, *(step["rollback"] for step in steps if step.get("rollback"))]
    configured: set[tuple[str, str]] = set()
    for invocation in invocations:
        capability_id = invocation["capability_id"]
        version = invocation["version"]
        if (capability_id, version) in configured or capability_id not in handlers:
            continue
        implementation, handler = handlers[capability_id]
        runtime.configure(capability_id, version, implementation, "1.0.0", handler)
        configured.add((capability_id, version))
    return MissionEngine(store, runtime)


if __name__ == "__main__":
    main()
