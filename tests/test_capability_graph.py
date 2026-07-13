import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from erasmus.capability_graph import (
    CapabilityGraph,
    GraphValidationError,
    load_manifest,
    validate_manifest,
)
from erasmus.migrations import apply_migrations
from erasmus.store import Store


MANIFEST = Path("capabilities/okf/pr-governance")


def starter():
    return load_manifest(MANIFEST)


def capability(data, capability_id):
    return next(item for item in data["capabilities"] if item["id"] == capability_id)


def graph(tmp_path):
    store = Store(str(tmp_path / "graph.db"))
    store.init()
    result = CapabilityGraph(store.db)
    result.import_bundle(MANIFEST)
    return result


def test_starter_schema_and_round_trip(tmp_path):
    manifest = starter()
    assert validate_manifest(manifest) == []
    capability_graph = graph(tmp_path)
    assert capability_graph.export_manifest() == manifest
    assert len(capability_graph.list_capabilities()) == 11
    assert capability_graph.inspect("merge_pull_request")["classification"] == "deterministic"
    exported = tmp_path / "exported-okf"
    capability_graph.export_bundle(exported)
    assert {
        file.relative_to(MANIFEST): file.read_text(encoding="utf-8")
        for file in MANIFEST.rglob("*.md")
    } == {
        file.relative_to(exported): file.read_text(encoding="utf-8")
        for file in exported.rglob("*.md")
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.pop("profile"), "schema:/: 'profile' is a required property"),
        (
            lambda data: data["edges"].append(
                {"from": "missing@1.0.0", "type": "requires", "to": "run_tests@1.0.0"}
            ),
            "edge source does not exist",
        ),
        (
            lambda data: data["edges"].append(
                {"from": "run_tests@1.0.0", "type": "unknown", "to": "compile_build@1.0.0"}
            ),
            "is not one of",
        ),
        (
            lambda data: data["capabilities"][0].update(authority_required=[]),
            "missing authority declaration",
        ),
        (
            lambda data: data["capabilities"][0].update(authority_required=["inherit"]),
            "silent authority inheritance",
        ),
        (
            lambda data: capability(data, "compile_build").update(rollback_behavior=None),
            "missing rollback",
        ),
        (
            lambda data: data["implementations"][0].update(id="ambient_path_git"),
            "undeclared implementation",
        ),
    ],
)
def test_invalid_manifests_fail_closed(mutate, message):
    manifest = starter()
    mutate(manifest)
    assert any(message in error for error in validate_manifest(manifest))


def test_incompatible_ports_and_execution_cycles_are_rejected():
    manifest = starter()
    capability(manifest, "inspect_git_repository")["outputs"][0]["schema"] = {"type": "string"}
    manifest["edges"].append(
        {"from": "inspect_git_repository@1.0.0", "type": "may_follow", "to": "inspect_pull_request@1.0.0"}
    )
    errors = validate_manifest(manifest)
    assert any("incompatible required port" in error for error in errors)
    assert any("forbidden execution cycle" in error for error in errors)


def test_conflicting_prerequisite_port_schemas_fail_closed():
    manifest = starter()
    source = capability(manifest, "merge_pull_request")
    source["inputs"] = [{"name": "shared", "schema": {"type": "string"}}]
    dependencies = [
        capability(manifest, "request_human_approval"),
        capability(manifest, "run_tests"),
    ]
    dependencies[0]["outputs"] = [{"name": "shared", "schema": {"type": "string"}}]
    dependencies[1]["outputs"] = [{"name": "shared", "schema": {"type": "integer"}}]
    errors = validate_manifest(manifest)
    assert "ambiguous required port: merge_pull_request@1.0.0.shared" in errors

    dependencies[1]["outputs"] = [{"name": "shared", "schema": {"type": "string"}}]
    source["inputs"][0]["schema"] = {"type": "boolean"}
    errors = validate_manifest(manifest)
    assert "incompatible required port: merge_pull_request@1.0.0.shared" in errors


def test_planner_orders_shared_diamond_dependency_once(tmp_path):
    manifest = starter()
    merge_ref = "merge_pull_request@1.0.0"
    inspect_ref = "inspect_git_repository@1.0.0"
    parents = ("request_human_approval", "run_tests")
    shared = capability(manifest, "inspect_git_repository")
    shared["outputs"].extend(
        port
        for parent in parents
        for port in capability(manifest, parent)["inputs"]
        if port["name"] not in {output["name"] for output in shared["outputs"]}
    )
    for parent in parents:
        manifest["edges"].append(
            {"from": f"{parent}@1.0.0", "type": "requires", "to": inspect_ref}
        )
    capability_graph = graph(tmp_path)
    capability(manifest, "merge_pull_request")["goals"] = ["diamond"]
    capability_graph.import_manifest(manifest)
    plans = capability_graph.plan(
        "diamond",
        {"repository:read", "process:execute", "review:request", "approval:request", "repository:merge"},
    )
    assert len(plans) == 1
    ids = [step.capability_id for step in plans[0].steps]
    assert ids.count("inspect_git_repository") == 1
    assert ids[-1] == merge_ref.rsplit("@", 1)[0]


def test_import_is_atomic_and_rebuildable(tmp_path):
    capability_graph = graph(tmp_path)
    invalid = starter()
    invalid["capabilities"][0]["authority_required"] = []
    with pytest.raises(GraphValidationError):
        capability_graph.import_manifest(invalid)
    assert capability_graph.export_manifest() == starter()
    capability_graph.import_manifest(starter())
    assert capability_graph.export_manifest() == starter()


def test_planner_prefers_deterministic_before_semantic(tmp_path):
    manifest = starter()
    semantic = deepcopy(capability(manifest, "inspect_git_repository"))
    semantic.update(
        id="semantic_repository_inspection",
        classification="semantic",
        allowed_implementations=["semantic_repository_agent"],
    )
    manifest["capabilities"].append(semantic)
    manifest["implementations"].append(
        {
            "id": "semantic_repository_agent",
            "version": "1.0.0",
            "capability_id": "semantic_repository_inspection",
            "capability_version": "1.0.0",
        }
    )
    capability_graph = graph(tmp_path)
    capability_graph.import_manifest(manifest)
    plans = capability_graph.plan("inspect_repository", {"repository:read"})
    assert [plan.steps[-1].capability_id for plan in plans] == ["inspect_git_repository"]

    ambiguous = deepcopy(capability(manifest, "inspect_git_repository"))
    ambiguous.update(id="second_git_inspection", allowed_implementations=["second_git_inspector"])
    manifest["capabilities"].append(ambiguous)
    manifest["implementations"].append(
        {
            "id": "second_git_inspector", "version": "1.0.0",
            "capability_id": "second_git_inspection", "capability_version": "1.0.0",
        }
    )
    capability_graph.import_manifest(manifest)
    assert capability_graph.plan("inspect_repository", {"repository:read"}) == []


def test_planner_rejects_missing_authority_conflicts_and_stale_evidence(tmp_path):
    capability_graph = graph(tmp_path)
    head = "a" * 40
    authorities = {
        "repository:read", "process:execute", "review:request",
        "approval:request", "repository:merge",
    }
    assert capability_graph.plan("merge_guarded_pull_request", authorities - {"repository:merge"}, head) == []

    manifest = starter()
    implementations = {
        f"{item['capability_id']}@{item['capability_version']}": item
        for item in manifest["implementations"]
    }
    prerequisites = [
        "inspect_git_repository@1.0.0", "inspect_pull_request@1.0.0",
        "run_tests@1.0.0", "invoke_tenth_man_review@1.0.0",
        "request_human_approval@1.0.0",
    ]
    for ref in prerequisites:
        capability_id, version = ref.rsplit("@", 1)
        implementation = implementations[ref]
        capability_graph.record_evidence(
            capability_id, version, implementation["id"], implementation["version"],
            {}, {}, "success", "b" * 40,
        )
    assert capability_graph.plan("merge_guarded_pull_request", authorities, head) == []

    for ref in prerequisites:
        capability_id, version = ref.rsplit("@", 1)
        implementation = implementations[ref]
        capability_graph.record_evidence(
            capability_id, version, implementation["id"], implementation["version"],
            {}, {}, "success", head,
        )
    assert capability_graph.plan("merge_guarded_pull_request", authorities, head)

    conflicted = starter()
    conflicted["edges"].append(
        {"from": "inspect_pull_request@1.0.0", "type": "conflicts_with", "to": "run_tests@1.0.0"}
    )
    capability_graph.import_manifest(conflicted)
    assert capability_graph.plan("merge_guarded_pull_request", authorities, head) == []


def test_evidence_rejects_undeclared_implementation(tmp_path):
    capability_graph = graph(tmp_path)
    with pytest.raises(ValueError, match="undeclared implementation"):
        capability_graph.record_evidence(
            "run_tests", "1.0.0", "ambient_pytest", "1.0.0", {}, {}, "success"
        )


def test_evidence_rejects_unknown_result(tmp_path):
    capability_graph = graph(tmp_path)
    with pytest.raises(ValueError, match="success.*failure"):
        capability_graph.record_evidence(
            "run_tests", "1.0.0", "pytest", "1.0.0", {}, {}, "maybe"
        )


def test_constraint_migrations_are_retryable_and_preserve_valid_rows():
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE schema_version(version INTEGER PRIMARY KEY);
        INSERT INTO schema_version VALUES(1), (2), (3), (4), (5);
        CREATE TABLE capabilities(
            id TEXT NOT NULL, version TEXT NOT NULL, PRIMARY KEY(id, version)
        );
        INSERT INTO capabilities VALUES('source', '1'), ('target', '1');
        CREATE TABLE capability_edges(
            source_id TEXT NOT NULL, source_version TEXT NOT NULL,
            edge_type TEXT NOT NULL, target_id TEXT NOT NULL, target_version TEXT NOT NULL,
            PRIMARY KEY(source_id, source_version, edge_type, target_id, target_version)
        );
        INSERT INTO capability_edges VALUES('source', '1', 'unknown', 'target', '1');
        CREATE TABLE capability_evidence(
            id INTEGER PRIMARY KEY, capability_id TEXT NOT NULL,
            capability_version TEXT NOT NULL, implementation_id TEXT NOT NULL,
            implementation_version TEXT NOT NULL, inputs_json TEXT NOT NULL,
            outputs_json TEXT NOT NULL, head_sha TEXT, result TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO capability_evidence(
            capability_id, capability_version, implementation_id,
            implementation_version, inputs_json, outputs_json, result
        ) VALUES('source', '1', 'implementation', '1', '{}', '{}', 'success');
        """
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        apply_migrations(db)
    assert db.execute("SELECT MAX(version) FROM schema_version").fetchone() == (5,)
    assert db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='capability_edges_v6'"
    ).fetchone() is None

    db.execute("DELETE FROM capability_edges")
    db.execute(
        "INSERT INTO capability_edges VALUES('source', '1', 'requires', 'target', '1')"
    )
    db.commit()
    assert apply_migrations(db) == [6, 7, 8, 9, 10]
    assert db.execute("SELECT edge_type FROM capability_edges").fetchone() == ("requires",)
    assert db.execute("SELECT result FROM capability_evidence").fetchone() == ("success",)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        db.execute(
            "INSERT INTO capability_edges VALUES('source', '1', 'unknown', 'target', '1')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        db.execute(
            "UPDATE capability_evidence SET result='unknown'"
        )


def test_graph_survives_restart(tmp_path):
    path = tmp_path / "restart.db"
    first = Store(str(path))
    first.init()
    CapabilityGraph(first.db).import_manifest(starter())
    first.db.close()
    second = Store(str(path))
    second.init()
    assert CapabilityGraph(second.db).inspect("query_sqlite")["version"] == "1.0.0"
