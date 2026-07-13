from copy import deepcopy
from pathlib import Path

import pytest

from erasmus.capability_graph import (
    CapabilityGraph,
    GraphValidationError,
    load_manifest,
    validate_manifest,
)
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
    assert len(capability_graph.list_capabilities()) == 8
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


def test_graph_survives_restart(tmp_path):
    path = tmp_path / "restart.db"
    first = Store(str(path))
    first.init()
    CapabilityGraph(first.db).import_manifest(starter())
    first.db.close()
    second = Store(str(path))
    second.init()
    assert CapabilityGraph(second.db).inspect("query_sqlite")["version"] == "1.0.0"
