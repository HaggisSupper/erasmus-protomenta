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
from erasmus.checkpoint import load_latest_checkpoint
from erasmus.missions import create_mission
from erasmus.review import tenth_man_prompt
from erasmus.sleep import consolidate
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
            "missions",
            "experience_candidates",
            "immune_state",
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


if __name__ == "__main__":
    main()
