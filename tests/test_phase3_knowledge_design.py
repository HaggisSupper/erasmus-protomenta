from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "docs" / "architecture" / "knowledge-system"

REQUIRED_DOCUMENTS = {
    "README.md",
    "ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md",
    "CONTRACT_CATALOGUE.md",
    "STATE_MODEL.md",
    "KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md",
    "OPEN_QUESTIONS_AND_SYNTHESIS.md",
    "POLICY_IDENTITY_AND_REGISTRIES.md",
    "STORAGE_PROJECTION_AND_RETRIEVAL.md",
    "UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md",
    "TEMPORAL_CONSISTENCY_AND_HISTORY.md",
    "OPERATOR_API_AND_RUNBOOK.md",
    "SECURITY_PRIVACY_AND_GOVERNANCE.md",
    "TEST_AND_ACCEPTANCE_PLAN.md",
    "GLOSSARY.md",
    "DESIGN_TRACEABILITY_MATRIX.md",
}
REQUIRED_SCHEMAS = {
    "knowledge-system.schema.json",
    "question-synthesis.schema.json",
    "governance-registry.schema.json",
    "impact-serving.schema.json",
    "temporal-consistency.schema.json",
    "operator-api.schema.json",
}
LINKED_OUTSIDE_PACKAGE = {
    ROOT / "docs" / "architecture" / "okf-knowledge-foundry.md",
    ROOT / "docs" / "DEVELOPMENT_TRACK.md",
    ROOT / "docs" / "roadmap" / "ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md",
    ROOT / "docs" / "adr" / "ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md",
    ROOT / "docs" / "superpowers" / "specs" / "2026-08-09-phase-3-knowledge-system-design.md",
}

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PLACEHOLDER = re.compile(r"\b(?:TBD|TODO|FIXME|XXX)\b", re.IGNORECASE)
_INLINE_CODE = re.compile(r"`[^`]*`")


def _markdown_files() -> list[Path]:
    return sorted(PACKAGE.glob("*.md")) + sorted(LINKED_OUTSIDE_PACKAGE)


def _internal_targets(path: Path) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    for raw in _LINK.findall(path.read_text(encoding="utf-8")):
        target = raw.strip().strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = unquote(target.split("#", 1)[0])
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        targets.append((raw, resolved))
    return targets


def _schema_paths() -> list[Path]:
    return sorted((PACKAGE / "schemas").glob("*.json"))


def _top_level_contracts(schema: dict) -> list[str]:
    contracts: list[str] = []
    for branch in schema.get("oneOf", []):
        reference = branch.get("$ref", "")
        prefix = "#/$defs/"
        assert reference.startswith(prefix), reference
        definition = schema["$defs"][reference.removeprefix(prefix)]
        contract = definition.get("properties", {}).get("contract", {}).get("const")
        assert isinstance(contract, str) and contract, reference
        contracts.append(contract)
    return contracts


def test_phase3_design_package_is_complete_and_indexed() -> None:
    actual_documents = {path.name for path in PACKAGE.glob("*.md")}
    actual_schemas = {path.name for path in (PACKAGE / "schemas").glob("*.json")}

    assert REQUIRED_DOCUMENTS <= actual_documents
    assert REQUIRED_SCHEMAS == actual_schemas

    index = (PACKAGE / "README.md").read_text(encoding="utf-8")
    for name in sorted(REQUIRED_DOCUMENTS - {"README.md"}):
        assert f"]({name})" in index
    for name in sorted(REQUIRED_SCHEMAS):
        assert f"](schemas/{name})" in index

    assert "**Draft schema registration:** Registered" in index
    assert "**Database migration:** None" in index
    assert "**Runtime activation:** None" in index
    assert (
        "No migration has been added. No policy, registry, candidate import, "
        "identity resolution, serving directive, canonical publication, or "
        "retrieval projection has been activated."
    ) in index


def test_phase3_markdown_internal_links_resolve_and_stay_inside_repository() -> None:
    broken: list[str] = []
    escaped: list[str] = []
    repository_root = ROOT.resolve()

    for path in _markdown_files():
        assert path.is_file(), path
        for raw, target in _internal_targets(path):
            if not target.is_relative_to(repository_root):
                escaped.append(f"{path.relative_to(ROOT)} -> {raw}")
            elif not target.exists():
                broken.append(f"{path.relative_to(ROOT)} -> {raw}")

    assert escaped == []
    assert broken == []


def test_phase3_design_has_no_placeholder_requirements() -> None:
    failures: list[str] = []
    for path in _markdown_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            prose = _INLINE_CODE.sub("", line)
            if _PLACEHOLDER.search(prose):
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    assert failures == []


def test_phase3_schema_seeds_are_valid_unique_registered_and_non_runtime() -> None:
    schema_ids: set[str] = set()
    contract_ids: set[str] = set()

    assert {path.name for path in _schema_paths()} == REQUIRED_SCHEMAS

    for path in _schema_paths():
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

        schema_id = schema["$id"]
        assert schema_id not in schema_ids
        schema_ids.add(schema_id)

        assert "Experimental design fixture only" in schema["description"]
        assert "Not registered with the live Erasmus runtime" in schema["description"]

        contracts = _top_level_contracts(schema)
        assert contracts
        assert len(contracts) == len(set(contracts))
        assert contract_ids.isdisjoint(contracts)
        contract_ids.update(contracts)


def test_phase3_state_planes_are_explicit_and_not_conflated() -> None:
    state_model = (PACKAGE / "STATE_MODEL.md").read_text(encoding="utf-8")
    lifecycle = (PACKAGE / "KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md").read_text(
        encoding="utf-8"
    )
    schema_doc = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )

    required_state_names = {
        "candidate_disposition",
        "reconciliation_action",
        "epistemic_status",
        "concept_lifecycle",
        "synthesis_lifecycle",
        "question_state",
        "freshness_state",
        "snapshot_state",
        "projection_state",
        "policy_state",
        "registry_state",
        "channel_state",
        "job_state",
    }
    for name in required_state_names:
        assert f"`{name}`" in state_model

    assert "status: draft" in state_model
    assert "external foundry" in state_model.lower()
    assert "[*] --> provisional" in lifecycle
    assert "provisional --> reviewed" in lifecycle
    assert "`provisional -> reviewed`" in lifecycle
    assert "[*] --> draft" not in lifecycle
    assert "`draft -> reviewed`" not in lifecycle

    concept_lifecycle = schema_doc["$defs"]["evidencePacketItem"]["properties"][
        "concept_lifecycle"
    ]["enum"]
    assert concept_lifecycle == [
        "provisional",
        "reviewed",
        "validated",
        "contested",
        "canonical",
        "superseded",
        "rejected",
        "deprecated",
    ]
    assert "draft" not in concept_lifecycle

    snapshot = schema_doc["$defs"]["canonicalSnapshot"]
    assert "snapshot_state" in snapshot["required"]
    assert "status" not in snapshot["required"]
    assert "snapshot_state" in snapshot["properties"]
    assert "status" not in snapshot["properties"]

    projection = schema_doc["$defs"]["projectionManifest"]
    assert "projection_state" in projection["required"]
    assert "status" not in projection["required"]
    assert "projection_state" in projection["properties"]
    assert "status" not in projection["properties"]


def test_phase3_authority_and_source_of_truth_boundaries_are_concrete() -> None:
    spec = (PACKAGE / "ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md").read_text(
        encoding="utf-8"
    )
    policy = (PACKAGE / "POLICY_IDENTITY_AND_REGISTRIES.md").read_text(
        encoding="utf-8"
    )
    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    operator = (PACKAGE / "OPERATOR_API_AND_RUNBOOK.md").read_text(encoding="utf-8")
    adr = (
        ROOT
        / "docs"
        / "adr"
        / "ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md"
    ).read_text(encoding="utf-8")

    assert "existing epistemic ledger" in spec
    assert "No model writes database rows or files directly" in spec
    assert "Missing policy is deny-by-default" in policy
    assert "A lower layer may narrow authority but cannot broaden" in policy
    assert "There is one current pointer per channel" in policy
    assert "channel_id TEXT NOT NULL" in storage
    assert "UNIQUE(channel_id, sequence)" in storage
    assert "### 6.1 Publication channel isolation" in storage
    assert "deleting every projection leaves authoritative knowledge intact" in adr.lower()
    assert "Tauri" in operator and "must not" in operator
    assert "dry_run" in operator
    assert "KnowledgeJob" in operator


def test_phase3_roadmap_contains_every_prerequisite_and_remains_non_authorizing() -> None:
    roadmap = (
        ROOT / "docs" / "roadmap" / "ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md"
    ).read_text(encoding="utf-8")
    design_index = (PACKAGE / "README.md").read_text(encoding="utf-8")
    foundry = (ROOT / "docs" / "architecture" / "okf-knowledge-foundry.md").read_text(
        encoding="utf-8"
    )
    development_track = (ROOT / "docs" / "DEVELOPMENT_TRACK.md").read_text(
        encoding="utf-8"
    )

    for phase in (
        "P3.0A",
        "P3.1",
        "P3.2",
        "P3.3A",
        "P3.4",
        "P3.8A",
        "P3.9",
        "P3.10",
        "P3.12",
        "P3.14",
    ):
        assert phase in roadmap

    assert "Each increment" in roadmap and "separate bounded mission" in roadmap
    assert "design authority only" in design_index
    assert "does not expand the authority" in foundry
    assert "The target is non-authorizing" in development_track


def test_phase3_traceability_declares_no_undefined_gap() -> None:
    traceability = (PACKAGE / "DESIGN_TRACEABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    )
    rows = [line for line in traceability.splitlines() if line.startswith("|")]
    data_rows = [line for line in rows if "---" not in line and "Design concern" not in line]

    assert len(data_rows) >= 40
    assert all("**Defined**" in line for line in data_rows)
    assert "Residual uncertainties deliberately deferred" in traceability
    assert "not unresolved design gaps" in traceability


def test_one_time_design_workflows_are_not_left_in_repository() -> None:
    workflow_root = ROOT / ".github" / "workflows"
    forbidden = {
        "normalize-phase3-design.yml",
        "normalize-phase3-design-pr.yml",
        "finalize-phase3-design.yml",
        "integrate-phase3-impact-design.yml",
        "integrate-phase3-temporal-design.yml",
    }
    assert not any((workflow_root / name).exists() for name in forbidden)
