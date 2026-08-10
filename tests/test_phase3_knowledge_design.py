from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote

import pytest
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


def _definition_validator(schema: dict, definition: str) -> Draft202012Validator:
    return Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        }
    )


def _sql_table_body(document: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE {re.escape(table)}\s*\((.*?)\n\);",
        document,
        flags=re.DOTALL,
    )
    assert match is not None, table
    return match.group(1)


def _sql_table_statement(document: str, table: str) -> str:
    return f"CREATE TABLE {table} (\n{_sql_table_body(document, table)}\n);"


def _markdown_section(document: str, heading: str) -> str:
    start = document.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    body_start = document.index("\n", start) + 1
    next_heading = re.search(rf"^#{{1,{level}}} ", document[body_start:], re.MULTILINE)
    if next_heading is None:
        return document[body_start:]
    return document[body_start : body_start + next_heading.start()]


def _roadmap_edges(roadmap: str) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for line in roadmap.splitlines():
        if "-->" not in line:
            continue
        nodes = re.findall(r"\bP\d+[A-Z]?\b", line)
        edges.update(zip(nodes, nodes[1:]))
    return edges


def _has_path(edges: set[tuple[str, str]], start: str, target: str) -> bool:
    frontier = [start]
    visited: set[str] = set()
    while frontier:
        node = frontier.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        frontier.extend(right for left, right in edges if left == node)
    return False


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


def test_operator_failure_response_requires_typed_failure_fixture() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "operator-api.schema.json").read_text(encoding="utf-8")
    )
    validator = _definition_validator(schema, "knowledgeResponse")
    base = {
        "contract": "erasmus.knowledge-response/v1",
        "request_id": "urn:erasmus:knowledge-request:test",
        "operation": "snapshot:publish",
        "receipts": [],
        "evidence_refs": [],
        "warnings": [],
        "next_actions": [],
        "started_at": "2026-08-09T12:00:00Z",
        "completed_at": "2026-08-09T12:00:01Z",
        "duration_ms": 1000,
    }
    typed_failure = {
        "code": "authority_denied",
        "message": "knowledge:publish authority is required",
        "details": {},
        "retryable": False,
        "action": "obtain exact authority",
        "related_ids": [],
    }

    assert validator.is_valid(base | {"ok": True, "failure": None})
    assert not validator.is_valid(base | {"ok": True, "failure": typed_failure})
    assert not validator.is_valid(base | {"ok": True})
    assert validator.is_valid(base | {"ok": False, "failure": typed_failure})
    assert not validator.is_valid(base | {"ok": False})
    assert not validator.is_valid(base | {"ok": False, "failure": None})
    assert not validator.is_valid(
        base | {"ok": False, "failure": {"code": "authority_denied"}}
    )


def test_publication_contract_is_append_only_receipt_first_and_recoverable() -> None:
    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    test_plan = (PACKAGE / "TEST_AND_ACCEPTANCE_PLAN.md").read_text(encoding="utf-8")

    intent = _sql_table_body(storage, "knowledge_publication_intents")
    snapshot = _sql_table_body(storage, "knowledge_snapshots")
    event = _sql_table_body(storage, "knowledge_snapshot_events")
    receipt = _sql_table_body(storage, "knowledge_publication_receipts")
    selection = _sql_table_body(storage, "knowledge_channel_selection_events")
    evidence_packet = _sql_table_body(storage, "knowledge_evidence_packets")
    assert "expected_prior_pointer_payload_json TEXT" in intent
    assert "expected_prior_pointer_json" not in intent
    assert "$.pointer_generation" in intent
    assert "intent_kind TEXT NOT NULL" in intent
    assert "selection_kind TEXT NOT NULL" in intent
    assert "attempt_sequence INTEGER NOT NULL" in intent
    assert "snapshot_sequence INTEGER NOT NULL" in intent
    assert "expected_prior_pointer_generation INTEGER NOT NULL" in intent
    assert "target_materialization_receipt_id TEXT" in intent
    assert not re.search(r"^    sequence INTEGER", intent, re.MULTILINE)
    assert "status TEXT" not in snapshot
    assert "published_at TEXT" not in snapshot
    assert "withdrawn_at TEXT" not in snapshot
    assert "creating_intent_id TEXT NOT NULL UNIQUE" in snapshot
    assert "snapshot_sequence INTEGER NOT NULL" in snapshot
    assert not re.search(r"^    sequence INTEGER", snapshot, re.MULTILINE)
    assert "prior_state TEXT" in event and "new_state TEXT NOT NULL" in event
    assert "receipt_status TEXT NOT NULL" in receipt
    assert "target_snapshot_id TEXT" in receipt
    assert "target_snapshot_id TEXT NOT NULL" not in receipt
    assert "pointer_payload_digest_json TEXT" in receipt
    assert "evidence_json TEXT NOT NULL" in receipt
    assert "attempt_sequence INTEGER NOT NULL" in receipt
    assert "snapshot_sequence INTEGER" in receipt
    assert "expected_prior_pointer_generation INTEGER NOT NULL" in receipt
    assert "next_pointer_generation INTEGER" in receipt
    assert "next_pointer_generation = expected_prior_pointer_generation + 1" in receipt
    assert "json_type(failure_json, '$.code') = 'text'" in receipt
    assert "FOREIGN KEY(target_snapshot_id, snapshot_sequence)" in receipt
    assert not re.search(r"^    sequence INTEGER", receipt, re.MULTILINE)
    assert "attempt_sequence INTEGER NOT NULL" in selection
    assert "snapshot_sequence INTEGER NOT NULL" in selection
    assert "prior_pointer_generation INTEGER NOT NULL" in selection
    assert "pointer_generation INTEGER NOT NULL" in selection
    assert "publication_receipt_id TEXT NOT NULL" in selection
    assert "publication_receipt_status TEXT NOT NULL" in selection
    assert "CHECK(publication_receipt_status = 'success')" in selection
    assert "FOREIGN KEY(publication_receipt_id, publication_receipt_status)" in selection
    assert "CHECK(pointer_generation = prior_pointer_generation + 1)" in selection
    assert not re.search(r"^    sequence INTEGER", selection, re.MULTILINE)
    assert "event_seq INTEGER NOT NULL UNIQUE" in evidence_packet
    assert "CHECK(as_known_event_seq <= event_seq)" in evidence_packet
    assert "REFERENCES knowledge_publication_receipts(receipt_id)" in evidence_packet

    protocol = _markdown_section(storage, "### 5.3 Append-only publication protocol")
    ordered_steps = [
        "**Prepare intent (SQLite transaction)**",
        "**Render and validate (filesystem work root)**",
        "**Approve snapshot (SQLite transaction)**",
        "**Install snapshot directory (filesystem)**",
        "**Commit terminal success receipt (SQLite transaction)**",
        "**Activate current pointer (filesystem)**",
        "**Confirm activation (SQLite transaction)**",
    ]
    positions = [protocol.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    assert "No filesystem operation and SQLite transaction are claimed to be atomic together" in protocol
    assert "must never name a snapshot without its committed success receipt" in protocol
    assert "`expected_prior_pointer_payload = null`" in protocol
    assert "`expected_prior_pointer_generation = 0`" in protocol
    assert "compare-and-swap the absent pointer at generation 0" in protocol
    assert "must not insert `knowledge_snapshots` or `knowledge_snapshot_members`" in protocol
    assert "attempt_sequence" in protocol
    assert "snapshot_sequence" in protocol
    assert "pointer_generation" in protocol

    failpoints = _markdown_section(test_plan, "### 9.4 Append-only publication failpoints")
    assert "after directory move before receipt commit" in failpoints
    assert "after receipt commit before pointer write" in failpoints
    assert "after pointer replace before channel-selection event" in failpoints
    assert "after pointer swap before receipt commit" not in failpoints
    for boundary in (
        "after prepare commit",
        "during either deterministic render",
        "during validation",
        "after approval commit before final directory move",
        "after pointer temporary-file fsync",
        "after channel-selection event before cleanup",
    ):
        assert boundary in failpoints

    for recovery_state in (
        "Intent exists; final directory absent",
        "Final directory exists; success receipt absent",
        "Success receipt exists; pointer remains prior generation",
        "Pointer names target receipt; selection event absent",
        "Pointer is missing, malformed, unreceipted, or content-mismatched",
    ):
        assert recovery_state in protocol

    for document_name in (
        "CONTRACT_CATALOGUE.md",
        "OPERATOR_API_AND_RUNBOOK.md",
        "STATE_MODEL.md",
    ):
        document = (PACKAGE / document_name).read_text(encoding="utf-8")
        assert "attempt_sequence" in document, document_name
        assert "snapshot_sequence" in document, document_name
        assert "pointer_generation" in document, document_name


def test_publication_schema_handles_bootstrap_creation_and_existing_snapshot_selection() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    top_level_definitions = {
        branch["$ref"].removeprefix("#/$defs/") for branch in schema["oneOf"]
    }
    assert "channelSelectionEvent" in schema["$defs"]
    assert "channelSelectionEvent" in top_level_definitions
    intent_validator = _definition_validator(schema, "publicationIntent")
    receipt_validator = _definition_validator(schema, "publicationReceipt")
    selection_validator = _definition_validator(schema, "channelSelectionEvent")
    digest = {
        "algorithm": "sha256",
        "value": "a" * 64,
        "canonicalization": "canonical-json/v1",
    }
    bootstrap_intent = {
        "contract": "erasmus.publication-intent/v1",
        "intent_id": "urn:erasmus:publication-intent:first",
        "intent_kind": "new_snapshot",
        "selection_kind": "publish",
        "channel_id": "urn:erasmus:publication-channel:private-default",
        "target_snapshot_id": "urn:erasmus:snapshot:first",
        "snapshot_sequence": 1,
        "attempt_sequence": 1,
        "expected_prior_pointer_payload": None,
        "expected_prior_pointer_generation": 0,
        "target_materialization_receipt_id": None,
        "exact_plan": {"plan_id": "urn:erasmus:publication-plan:first"},
        "event_seq": 101,
        "created_at": "2026-08-10T12:00:00Z",
    }
    assert intent_validator.is_valid(bootstrap_intent)
    assert not intent_validator.is_valid(
        {
            key: value
            for key, value in bootstrap_intent.items()
            if key != "expected_prior_pointer_generation"
        }
    )
    assert not intent_validator.is_valid(
        bootstrap_intent | {"expected_prior_pointer_generation": 1}
    )
    assert not intent_validator.is_valid(
        bootstrap_intent | {"expected_prior_pointer_generation": "0"}
    )
    assert not intent_validator.is_valid(
        bootstrap_intent
        | {
            "target_materialization_receipt_id":
                "urn:erasmus:publication-receipt:old"
        }
    )

    current_pointer = {
        "channel_id": bootstrap_intent["channel_id"],
        "snapshot_id": "urn:erasmus:snapshot:newer",
        "snapshot_sequence": 2,
        "receipt_id": "urn:erasmus:publication-receipt:newer",
        "intent_id": "urn:erasmus:publication-intent:newer",
        "attempt_sequence": 2,
        "manifest_digest": digest,
        "policy_id": "urn:erasmus:policy:default",
        "policy_version": "1.0.0",
        "registry_snapshot_id": "urn:erasmus:registry-snapshot:current",
    }
    rollback_intent = bootstrap_intent | {
        "intent_id": "urn:erasmus:publication-intent:rollback",
        "intent_kind": "reselect_existing",
        "selection_kind": "rollback",
        "attempt_sequence": 3,
        "expected_prior_pointer_payload": current_pointer,
        "expected_prior_pointer_generation": 2,
        "target_materialization_receipt_id": "urn:erasmus:publication-receipt:first",
        "exact_plan": None,
        "event_seq": 102,
    }
    assert intent_validator.is_valid(rollback_intent)
    for field in ("policy_id", "policy_version", "registry_snapshot_id"):
        incomplete_pointer = {
            key: value for key, value in current_pointer.items() if key != field
        }
        assert not intent_validator.is_valid(
            rollback_intent | {"expected_prior_pointer_payload": incomplete_pointer}
        )
    assert intent_validator.is_valid(
        rollback_intent
        | {
            "intent_id": "urn:erasmus:publication-intent:reselect",
            "selection_kind": "reselect",
        }
    )
    assert not intent_validator.is_valid(
        rollback_intent | {"target_materialization_receipt_id": None}
    )
    assert not intent_validator.is_valid(
        rollback_intent | {"expected_prior_pointer_generation": 0}
    )
    assert not intent_validator.is_valid(
        rollback_intent | {"exact_plan": {"must_not": "render"}}
    )

    bootstrap_receipt = {
        "contract": "erasmus.publication-receipt/v1",
        "receipt_id": "urn:erasmus:publication-receipt:first",
        "intent_id": bootstrap_intent["intent_id"],
        "receipt_kind": "materialization",
        "channel_id": bootstrap_intent["channel_id"],
        "target_snapshot_id": bootstrap_intent["target_snapshot_id"],
        "snapshot_sequence": 1,
        "attempt_sequence": 1,
        "expected_prior_pointer_generation": 0,
        "next_pointer_generation": 1,
        "publisher": {
            "id": "erasmus.knowledge.publisher",
            "version": "1.0.0",
            "digest": digest,
        },
        "validator": {
            "id": "erasmus.knowledge.validator",
            "version": "1.0.0",
            "digest": digest,
        },
        "manifest_digest": digest,
        "pointer_payload_digest": digest,
        "receipt_status": "success",
        "results": {},
        "evidence": {
            "input_digest": digest,
            "policy_evaluation_id": "urn:erasmus:policy-evaluation:first",
            "review_ids": [],
        },
        "failure": None,
        "event_seq": 102,
        "completed_at": "2026-08-10T12:00:01Z",
    }
    assert receipt_validator.is_valid(bootstrap_receipt)
    assert not receipt_validator.is_valid(
        {
            key: value
            for key, value in bootstrap_receipt.items()
            if key != "next_pointer_generation"
        }
    )
    assert receipt_validator.is_valid(
        bootstrap_receipt
        | {
            "receipt_id": "urn:erasmus:publication-receipt:rollback",
            "intent_id": rollback_intent["intent_id"],
            "receipt_kind": "reselection",
            "attempt_sequence": 3,
            "expected_prior_pointer_generation": 2,
            "next_pointer_generation": 3,
            "event_seq": 103,
        }
    )

    bootstrap_selection = {
        "contract": "erasmus.channel-selection-event/v1",
        "selection_event_id": "urn:erasmus:channel-selection:first",
        "intent_id": bootstrap_intent["intent_id"],
        "channel_id": bootstrap_intent["channel_id"],
        "snapshot_id": bootstrap_intent["target_snapshot_id"],
        "snapshot_sequence": 1,
        "publication_receipt_id": "urn:erasmus:publication-receipt:first",
        "publication_receipt_status": "success",
        "attempt_sequence": 1,
        "selection_kind": "publish",
        "prior_snapshot_id": None,
        "prior_pointer_generation": 0,
        "pointer_generation": 1,
        "pointer_digest": digest,
        "event_seq": 104,
        "created_at": "2026-08-10T12:00:01Z",
    }
    assert selection_validator.is_valid(bootstrap_selection)
    assert not selection_validator.is_valid(
        {
            key: value
            for key, value in bootstrap_selection.items()
            if key != "attempt_sequence"
        }
    )
    assert not selection_validator.is_valid(
        bootstrap_selection | {"prior_pointer_generation": 1}
    )
    assert not selection_validator.is_valid(
        bootstrap_selection | {"pointer_generation": 2}
    )
    assert not selection_validator.is_valid(
        bootstrap_selection | {"selection_kind": "recovery"}
    )
    assert not selection_validator.is_valid(
        bootstrap_selection | {"publication_receipt_status": "failure"}
    )
    assert not selection_validator.is_valid(
        {
            key: value
            for key, value in bootstrap_selection.items()
            if key != "publication_receipt_status"
        }
    )
    assert selection_validator.is_valid(
        bootstrap_selection
        | {
            "selection_event_id": "urn:erasmus:channel-selection:rollback",
            "intent_id": rollback_intent["intent_id"],
            "snapshot_sequence": 1,
            "attempt_sequence": 3,
            "selection_kind": "rollback",
            "prior_snapshot_id": "urn:erasmus:snapshot:newer",
            "prior_pointer_generation": 2,
            "pointer_generation": 3,
            "event_seq": 105,
        }
    )


def test_publication_intent_has_one_authoritative_expected_pointer_generation() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = _definition_validator(schema, "publicationIntent")
    digest = {
        "algorithm": "sha256",
        "value": "c" * 64,
        "canonicalization": "canonical-json/v1",
    }
    prior_payload = {
        "channel_id": "urn:erasmus:publication-channel:private-default",
        "snapshot_id": "urn:erasmus:snapshot:current",
        "snapshot_sequence": 1,
        "receipt_id": "urn:erasmus:publication-receipt:current",
        "intent_id": "urn:erasmus:publication-intent:current",
        "attempt_sequence": 1,
        "manifest_digest": digest,
        "policy_id": "urn:erasmus:policy:default",
        "policy_version": "1.0.0",
        "registry_snapshot_id": "urn:erasmus:registry-snapshot:current",
    }
    later_intent = {
        "contract": "erasmus.publication-intent/v1",
        "intent_id": "urn:erasmus:publication-intent:later",
        "channel_id": prior_payload["channel_id"],
        "attempt_sequence": 2,
        "intent_kind": "new_snapshot",
        "selection_kind": "publish",
        "target_snapshot_id": "urn:erasmus:snapshot:later",
        "snapshot_sequence": 2,
        "expected_prior_pointer_payload": prior_payload,
        "expected_prior_pointer_generation": 1,
        "exact_plan": {"plan_id": "urn:erasmus:publication-plan:later"},
        "target_materialization_receipt_id": None,
        "event_seq": 201,
        "created_at": "2026-08-10T14:00:00Z",
    }
    assert validator.is_valid(later_intent)
    assert not validator.is_valid(
        later_intent
        | {
            "expected_prior_pointer_payload": prior_payload
            | {"pointer_generation": 1}
        }
    )
    assert validator.is_valid(
        later_intent
        | {
            "intent_id": "urn:erasmus:publication-intent:first",
            "attempt_sequence": 1,
            "target_snapshot_id": "urn:erasmus:snapshot:first",
            "snapshot_sequence": 1,
            "expected_prior_pointer_payload": None,
            "expected_prior_pointer_generation": 0,
            "event_seq": 202,
        }
    )
    assert not validator.is_valid(
        later_intent
        | {
            "expected_prior_pointer_payload": None,
            "expected_prior_pointer_generation": 1,
        }
    )


def test_publication_receipt_schema_distinguishes_success_from_early_failure() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = _definition_validator(schema, "publicationReceipt")
    digest = {
        "algorithm": "sha256",
        "value": "d" * 64,
        "canonicalization": "canonical-json/v1",
    }
    implementation = {
        "id": "erasmus.knowledge.publisher",
        "version": "1.0.0",
        "digest": digest,
    }
    deterministic_evidence = {
        "input_digest": digest,
        "policy_evaluation_id": "urn:erasmus:policy-evaluation:publication",
        "review_ids": ["urn:erasmus:review:publication"],
    }
    typed_failure = {
        "code": "render_failed",
        "message": "The deterministic render failed before artifact creation.",
        "details": {"render": 1},
        "retryable": True,
        "action": "start a later publication attempt",
        "related_ids": ["urn:erasmus:publication-intent:first"],
    }
    success = {
        "contract": "erasmus.publication-receipt/v1",
        "receipt_id": "urn:erasmus:publication-receipt:success",
        "intent_id": "urn:erasmus:publication-intent:success",
        "receipt_kind": "materialization",
        "channel_id": "urn:erasmus:publication-channel:private-default",
        "target_snapshot_id": "urn:erasmus:snapshot:success",
        "snapshot_sequence": 1,
        "attempt_sequence": 1,
        "expected_prior_pointer_generation": 0,
        "next_pointer_generation": 1,
        "publisher": implementation,
        "validator": implementation | {"id": "erasmus.knowledge.validator"},
        "results": {"deterministic": True},
        "evidence": deterministic_evidence,
        "manifest_digest": digest,
        "pointer_payload_digest": digest,
        "receipt_status": "success",
        "failure": None,
        "event_seq": 203,
        "completed_at": "2026-08-10T14:00:01Z",
    }
    assert validator.is_valid(success)
    for field in ("publisher", "validator", "results", "evidence"):
        assert not validator.is_valid(
            {key: value for key, value in success.items() if key != field}
        ), field
    for field in (
        "target_snapshot_id",
        "snapshot_sequence",
        "manifest_digest",
        "pointer_payload_digest",
        "next_pointer_generation",
    ):
        assert not validator.is_valid(success | {field: None}), field
        assert not validator.is_valid(
            {key: value for key, value in success.items() if key != field}
        ), field
    assert not validator.is_valid(success | {"failure": typed_failure})
    assert not validator.is_valid(success | {"next_pointer_generation": 2})

    early_failure = success | {
        "receipt_id": "urn:erasmus:publication-receipt:failure",
        "intent_id": "urn:erasmus:publication-intent:first",
        "target_snapshot_id": None,
        "snapshot_sequence": None,
        "next_pointer_generation": None,
        "manifest_digest": None,
        "pointer_payload_digest": None,
        "receipt_status": "failure",
        "failure": typed_failure,
        "event_seq": 204,
    }
    assert validator.is_valid(early_failure)
    assert not validator.is_valid(early_failure | {"failure": None})
    assert not validator.is_valid(
        early_failure | {"failure": {"code": "render_failed"}}
    )
    assert not validator.is_valid(early_failure | {"next_pointer_generation": 1})
    assert not validator.is_valid(early_failure | {"snapshot_sequence": 1})
    assert validator.is_valid(
        early_failure
        | {
            "target_snapshot_id": "urn:erasmus:snapshot:partial",
            "snapshot_sequence": 2,
            "manifest_digest": digest,
        }
    )


def test_publication_ddl_persists_early_failure_before_artifact_and_allows_retry() -> None:
    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for table in (
        "knowledge_events",
        "knowledge_publication_intents",
        "knowledge_snapshots",
        "knowledge_publication_receipts",
        "knowledge_channel_selection_events",
    ):
        connection.execute(_sql_table_statement(storage, table))

    timestamp = "2026-08-10T14:00:00Z"
    for event_seq in range(1, 16):
        connection.execute(
            """
            INSERT INTO knowledge_events (
                event_seq, event_id, event_type, aggregate_type, aggregate_id,
                command_id, transaction_id, payload_digest_json,
                recorded_at, committed_at
            ) VALUES (?, ?, 'fixture', 'fixture', ?, NULL, ?, '{}', ?, ?)
            """,
            (
                event_seq,
                f"early-failure-event-{event_seq}",
                f"aggregate-{event_seq}",
                f"transaction-{event_seq}",
                timestamp,
                timestamp,
            ),
        )

    intent_sql = """
        INSERT INTO knowledge_publication_intents (
            intent_id, channel_id, attempt_sequence, intent_kind,
            selection_kind, target_snapshot_id, snapshot_sequence,
            exact_plan_json, expected_prior_pointer_payload_json,
            expected_prior_pointer_generation,
            target_materialization_receipt_id, event_seq, created_at
        ) VALUES (?, 'private', ?, 'new_snapshot', 'publish', ?, ?, '{}',
                  NULL, 0, NULL, ?, ?)
    """
    connection.execute(
        intent_sql,
        ("intent-failed", 1, "snapshot-never-created", 1, 1, timestamp),
    )
    connection.execute(
        """
        INSERT INTO knowledge_publication_receipts (
            receipt_id, intent_id, receipt_kind, target_snapshot_id,
            channel_id, attempt_sequence, snapshot_sequence,
            expected_prior_pointer_generation, next_pointer_generation,
            publisher_json, validator_json, results_json, evidence_json,
            manifest_digest_json, pointer_payload_digest_json,
            receipt_status, failure_json, event_seq, completed_at
        ) VALUES (
            'receipt-failed', 'intent-failed', 'materialization', NULL,
            'private', 1, NULL, 0, NULL, '{}', '{}', '{}', '{}',
            NULL, NULL, 'failure',
            '{"code":"render_failed","message":"render failed","details":{},"retryable":true,"action":"retry","related_ids":[]}',
            2, ?
        )
        """,
        (timestamp,),
    )
    assert connection.execute("SELECT COUNT(*) FROM knowledge_snapshots").fetchone() == (0,)
    assert connection.execute(
        "SELECT receipt_status, target_snapshot_id, next_pointer_generation "
        "FROM knowledge_publication_receipts WHERE receipt_id = 'receipt-failed'"
    ).fetchone() == ("failure", None, None)

    connection.execute(
        intent_sql,
        ("intent-retry", 2, "snapshot-retry", 2, 3, timestamp),
    )
    connection.execute(
        """
        INSERT INTO knowledge_snapshots (
            snapshot_id, creating_intent_id, channel_id, snapshot_sequence,
            parent_snapshot_id, scope_json, manifest_digest_json, root_path,
            event_seq, created_at
        ) VALUES (
            'snapshot-retry', 'intent-retry', 'private', 2, NULL, '{}', '{}',
            '/snapshot-retry', 4, ?
        )
        """,
        (timestamp,),
    )
    connection.execute(
        """
        INSERT INTO knowledge_publication_receipts (
            receipt_id, intent_id, receipt_kind, target_snapshot_id,
            channel_id, attempt_sequence, snapshot_sequence,
            expected_prior_pointer_generation, next_pointer_generation,
            publisher_json, validator_json, results_json, evidence_json,
            manifest_digest_json, pointer_payload_digest_json,
            receipt_status, failure_json, event_seq, completed_at
        ) VALUES (
            'receipt-retry', 'intent-retry', 'materialization', 'snapshot-retry',
            'private', 2, 2, 0, 1, '{}', '{}', '{}', '{}', '{}', '{}',
            'success', NULL, 5, ?
        )
        """,
        (timestamp,),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO knowledge_channel_selection_events (
                selection_event_id, intent_id, channel_id, snapshot_id,
                publication_receipt_id, publication_receipt_status,
                prior_snapshot_id, attempt_sequence, snapshot_sequence,
                prior_pointer_generation, pointer_generation,
                pointer_digest_json, selection_kind, event_seq, created_at
            ) VALUES (
                'bad-selection', 'intent-failed', 'private', 'snapshot-retry',
                'receipt-failed', 'success', NULL, 1, 2, 0, 1, '{}',
                'publish', 6, ?
            )
            """,
            (timestamp,),
        )

    connection.execute(
        """
        INSERT INTO knowledge_publication_intents (
            intent_id, channel_id, attempt_sequence, intent_kind,
            selection_kind, target_snapshot_id, snapshot_sequence,
            exact_plan_json, expected_prior_pointer_payload_json,
            expected_prior_pointer_generation,
            target_materialization_receipt_id, event_seq, created_at
        ) VALUES (
            'intent-late-failure', 'private', 4, 'reselect_existing',
            'rollback', 'snapshot-retry', 2, NULL, '{}', 1,
            'receipt-retry', 11, ?
        )
        """,
        (timestamp,),
    )
    connection.execute(
        """
        INSERT INTO knowledge_publication_receipts (
            receipt_id, intent_id, receipt_kind, target_snapshot_id,
            channel_id, attempt_sequence, snapshot_sequence,
            expected_prior_pointer_generation, next_pointer_generation,
            publisher_json, validator_json, results_json, evidence_json,
            manifest_digest_json, pointer_payload_digest_json,
            receipt_status, failure_json, event_seq, completed_at
        ) VALUES (
            'receipt-late-failure', 'intent-late-failure', 'reselection',
            'snapshot-retry', 'private', 4, 2, 1, NULL, '{}', '{}', '{}', '{}',
            '{}', NULL, 'failure',
            '{"code":"artifact_corrupt","message":"artifact corrupt","details":{},"retryable":false,"action":"inspect","related_ids":[]}',
            12, ?
        )
        """,
        (timestamp,),
    )
    assert connection.execute(
        "SELECT target_snapshot_id, snapshot_sequence, next_pointer_generation "
        "FROM knowledge_publication_receipts "
        "WHERE receipt_id = 'receipt-late-failure'"
    ).fetchone() == ("snapshot-retry", 2, None)

    connection.execute(
        intent_sql,
        ("intent-ghost-failure", 5, "snapshot-does-not-exist", 5, 14, timestamp),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO knowledge_publication_receipts (
                receipt_id, intent_id, receipt_kind, target_snapshot_id,
                channel_id, attempt_sequence, snapshot_sequence,
                expected_prior_pointer_generation, next_pointer_generation,
                publisher_json, validator_json, results_json, evidence_json,
                manifest_digest_json, pointer_payload_digest_json,
                receipt_status, failure_json, event_seq, completed_at
            ) VALUES (
                'receipt-ghost-failure', 'intent-ghost-failure',
                'materialization', 'snapshot-does-not-exist', 'private', 5, 5,
                0, NULL, '{}', '{}', '{}', '{}', NULL, NULL, 'failure',
                '{"code":"render_failed","message":"render failed","details":{},"retryable":true,"action":"retry","related_ids":[]}',
                15, ?
            )
            """,
            (timestamp,),
        )

    connection.execute(
        """
        INSERT INTO knowledge_channel_selection_events (
            selection_event_id, intent_id, channel_id, snapshot_id,
            publication_receipt_id, publication_receipt_status,
            prior_snapshot_id, attempt_sequence, snapshot_sequence,
            prior_pointer_generation, pointer_generation,
            pointer_digest_json, selection_kind, event_seq, created_at
        ) VALUES (
            'selection-retry', 'intent-retry', 'private', 'snapshot-retry',
            'receipt-retry', 'success', NULL, 2, 2, 0, 1, '{}',
            'publish', 7, ?
        )
        """,
        (timestamp,),
    )
    assert connection.execute(
        "SELECT attempt_sequence FROM knowledge_publication_intents "
        "WHERE attempt_sequence <= 2 ORDER BY attempt_sequence"
    ).fetchall() == [(1,), (2,)]
    assert connection.execute(
        "SELECT publication_receipt_id FROM knowledge_channel_selection_events"
    ).fetchall() == [("receipt-retry",)]

    connection.execute(
        intent_sql,
        ("intent-bad-generation", 3, "snapshot-bad-generation", 3, 8, timestamp),
    )
    connection.execute(
        """
        INSERT INTO knowledge_snapshots (
            snapshot_id, creating_intent_id, channel_id, snapshot_sequence,
            parent_snapshot_id, scope_json, manifest_digest_json, root_path,
            event_seq, created_at
        ) VALUES (
            'snapshot-bad-generation', 'intent-bad-generation', 'private', 3,
            'snapshot-retry', '{}', '{}', '/snapshot-bad-generation', 9, ?
        )
        """,
        (timestamp,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO knowledge_publication_receipts (
                receipt_id, intent_id, receipt_kind, target_snapshot_id,
                channel_id, attempt_sequence, snapshot_sequence,
                expected_prior_pointer_generation, next_pointer_generation,
                publisher_json, validator_json, results_json, evidence_json,
                manifest_digest_json, pointer_payload_digest_json,
                receipt_status, failure_json, event_seq, completed_at
            ) VALUES (
                'receipt-bad-generation', 'intent-bad-generation',
                'materialization', 'snapshot-bad-generation', 'private', 3, 3,
                0, 2, '{}', '{}', '{}', '{}', '{}', '{}', 'success', NULL, 10, ?
            )
            """,
            (timestamp,),
        )


def test_evidence_packet_is_an_event_ordered_immutable_retrieval_receipt() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = _definition_validator(schema, "evidencePacket")
    packet = {
        "contract": "erasmus.evidence-packet/v1",
        "packet_id": "urn:erasmus:evidence-packet:test",
        "request_id": "urn:erasmus:knowledge-request:test",
        "channel_id": "urn:erasmus:publication-channel:private-default",
        "snapshot_id": "urn:erasmus:snapshot:first",
        "snapshot_sequence": 1,
        "publication_receipt_id": "urn:erasmus:publication-receipt:rollback",
        "pointer_generation": 3,
        "directive_set_digest": {
            "algorithm": "sha256",
            "value": "b" * 64,
            "canonicalization": "canonical-json/v1",
        },
        "as_known_event_seq": 104,
        "items": [],
        "omitted": {"count": 0, "reasons": []},
        "budget": {"used": 0, "limit": 100},
        "event_seq": 106,
        "created_at": "2026-08-10T12:00:02Z",
    }
    assert validator.is_valid(packet)
    assert not validator.is_valid(
        {key: value for key, value in packet.items() if key != "event_seq"}
    )
    assert not validator.is_valid(packet | {"event_seq": 0})
    for field in (
        "publication_receipt_id",
        "pointer_generation",
        "directive_set_digest",
        "as_known_event_seq",
    ):
        assert not validator.is_valid(
            {key: value for key, value in packet.items() if key != field}
        )


def test_publication_ddl_reselects_without_duplicating_snapshot_identity() -> None:
    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    intent_body = _sql_table_body(storage, "knowledge_publication_intents")
    assert "attempt_sequence INTEGER NOT NULL" in intent_body
    assert "intent_kind TEXT NOT NULL" in intent_body
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for table in (
        "knowledge_events",
        "knowledge_publication_intents",
        "knowledge_snapshots",
        "knowledge_publication_receipts",
        "knowledge_channel_selection_events",
    ):
        connection.execute(_sql_table_statement(storage, table))

    for event_seq in range(1, 12):
        connection.execute(
            """
            INSERT INTO knowledge_events (
                event_seq, event_id, event_type, aggregate_type, aggregate_id,
                command_id, transaction_id, payload_digest_json,
                recorded_at, committed_at
            ) VALUES (?, ?, 'fixture', 'fixture', ?, NULL, ?, '{}', ?, ?)
            """,
            (
                event_seq,
                f"event-{event_seq}",
                f"aggregate-{event_seq}",
                f"transaction-{event_seq}",
                "2026-08-10T12:00:00Z",
                "2026-08-10T12:00:00Z",
            ),
        )

    intent_sql = """
        INSERT INTO knowledge_publication_intents (
            intent_id, channel_id, attempt_sequence, intent_kind,
            selection_kind, target_snapshot_id, snapshot_sequence,
            exact_plan_json, expected_prior_pointer_payload_json,
            expected_prior_pointer_generation,
            target_materialization_receipt_id, event_seq, created_at
        ) VALUES (?, 'private', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    snapshot_sql = """
        INSERT INTO knowledge_snapshots (
            snapshot_id, creating_intent_id, channel_id, snapshot_sequence,
            parent_snapshot_id, scope_json, manifest_digest_json, root_path,
            event_seq, created_at
        ) VALUES (?, ?, 'private', ?, ?, '{}', ?, ?, ?, ?)
    """
    receipt_sql = """
        INSERT INTO knowledge_publication_receipts (
            receipt_id, intent_id, receipt_kind, target_snapshot_id,
            channel_id, attempt_sequence, snapshot_sequence,
            expected_prior_pointer_generation, next_pointer_generation,
            publisher_json, validator_json, results_json, evidence_json,
            manifest_digest_json, pointer_payload_digest_json,
            receipt_status, failure_json, event_seq, completed_at
        ) VALUES (?, ?, ?, ?, 'private', ?, ?, ?, ?, '{}', '{}', '{}', '{}',
                  ?, ?, 'success', NULL, ?, ?)
    """
    selection_sql = """
        INSERT INTO knowledge_channel_selection_events (
            selection_event_id, intent_id, channel_id, snapshot_id,
            publication_receipt_id, publication_receipt_status,
            prior_snapshot_id, attempt_sequence,
            snapshot_sequence, prior_pointer_generation, pointer_generation,
            pointer_digest_json, selection_kind, event_seq, created_at
        ) VALUES (?, ?, 'private', ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    timestamp = "2026-08-10T12:00:00Z"
    digest_one = '{"digest":"one"}'
    digest_two = '{"digest":"two"}'

    connection.execute(
        intent_sql,
        ("intent-1", 1, "new_snapshot", "publish", "snapshot-1", 1,
         '{"plan":1}', None, 0, None, 1, timestamp),
    )
    connection.execute(
        snapshot_sql,
        ("snapshot-1", "intent-1", 1, None, digest_one, "/s1", 2, timestamp),
    )
    connection.execute(
        receipt_sql,
        ("receipt-1", "intent-1", "materialization", "snapshot-1", 1, 1,
         0, 1, digest_one, digest_one, 3, timestamp),
    )
    connection.execute(
        selection_sql,
        ("selection-1", "intent-1", "snapshot-1", "receipt-1", None, 1, 1,
         0, 1, digest_one, "publish", 4, timestamp),
    )

    connection.execute(
        intent_sql,
        ("intent-2", 2, "new_snapshot", "publish", "snapshot-2", 2,
         '{"plan":2}', '{"snapshot_id":"snapshot-1"}', 1, None, 5, timestamp),
    )
    connection.execute(
        snapshot_sql,
        ("snapshot-2", "intent-2", 2, "snapshot-1", digest_two, "/s2", 6,
         timestamp),
    )
    connection.execute(
        receipt_sql,
        ("receipt-2", "intent-2", "materialization", "snapshot-2", 2, 2,
         1, 2, digest_two, digest_two, 7, timestamp),
    )
    connection.execute(
        selection_sql,
        ("selection-2", "intent-2", "snapshot-2", "receipt-2", "snapshot-1",
         2, 2, 1, 2, digest_two, "publish", 8, timestamp),
    )

    connection.execute(
        intent_sql,
        ("intent-3", 3, "reselect_existing", "rollback", "snapshot-1", 1,
         None, '{"snapshot_id":"snapshot-2"}', 2, "receipt-1", 9, timestamp),
    )
    connection.execute(
        receipt_sql,
        ("receipt-3", "intent-3", "reselection", "snapshot-1", 3, 1,
         2, 3, digest_one, digest_one, 10, timestamp),
    )
    connection.execute(
        selection_sql,
        ("selection-3", "intent-3", "snapshot-1", "receipt-3", "snapshot-2",
         3, 1, 2, 3, digest_one, "rollback", 11, timestamp),
    )
    connection.commit()

    assert connection.execute(
        "SELECT snapshot_sequence FROM knowledge_snapshots ORDER BY snapshot_sequence"
    ).fetchall() == [(1,), (2,)]
    assert connection.execute(
        "SELECT attempt_sequence FROM knowledge_publication_intents ORDER BY attempt_sequence"
    ).fetchall() == [(1,), (2,), (3,)]
    assert connection.execute(
        "SELECT pointer_generation FROM knowledge_channel_selection_events "
        "ORDER BY pointer_generation"
    ).fetchall() == [(1,), (2,), (3,)]
    assert connection.execute("SELECT COUNT(*) FROM knowledge_snapshots").fetchone() == (2,)
    assert connection.execute(
        "SELECT snapshot_sequence, attempt_sequence, pointer_generation "
        "FROM knowledge_channel_selection_events WHERE selection_kind = 'rollback'"
    ).fetchone() == (1, 3, 3)


def test_invalidation_and_directive_lifecycle_precede_publication_and_retrieval() -> None:
    roadmap = (
        ROOT / "docs" / "roadmap" / "ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md"
    ).read_text(encoding="utf-8")
    edges = _roadmap_edges(roadmap)
    assert _has_path(edges, "P8A", "P8B")
    assert _has_path(edges, "P8B", "P9")
    assert _has_path(edges, "P8B", "P10")

    prerequisite = _markdown_section(
        roadmap, "## 10B. P3.8B — Minimum invalidation and serving suspension"
    )
    assert "hard prerequisite" in prerequisite
    assert "full downstream impact analysis" in prerequisite

    schema = json.loads(
        (PACKAGE / "schemas" / "impact-serving.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = _definition_validator(schema, "servingDirective")
    directive = {
        "contract": "erasmus.serving-directive/v1",
        "directive_id": "urn:erasmus:serving-directive:test",
        "subject_ids": ["urn:erasmus:concept:test"],
        "channel_ids": ["urn:erasmus:publication-channel:private-default"],
        "scope_selector": {},
        "effect": "block",
        "qualification": None,
        "reason_code": "source_withdrawn",
        "invalidation_event_id": "urn:erasmus:invalidation-event:test",
        "impact_id": None,
        "evidence_ids": [1],
        "policy_evaluation_id": "urn:erasmus:policy-evaluation:test",
        "actor": "human:operator",
        "authority": "knowledge:withdraw",
        "mission_id": 123,
        "effective_at": "2026-08-09T12:00:00Z",
        "expires_at": None,
        "replacement_snapshot_id": None,
        "supersedes_directive_id": None,
        "event_seq": 41,
        "created_at": "2026-08-09T12:00:00Z",
    }
    assert validator.is_valid(directive)
    assert validator.is_valid(
        directive
        | {
            "directive_id": "urn:erasmus:serving-directive:replacement",
            "supersedes_directive_id": directive["directive_id"],
            "effect": "allow",
        }
    )
    assert not validator.is_valid(
        {key: value for key, value in directive.items() if key != "supersedes_directive_id"}
    )
    assert not validator.is_valid(directive | {"supersedes_directive_id": 41})

    controls = (
        PACKAGE / "UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md"
    ).read_text(encoding="utf-8")
    directive_table = _sql_table_body(controls, "knowledge_serving_directives")
    assert "supersedes_directive_id TEXT" in directive_table
    assert "REFERENCES knowledge_serving_directives(directive_id)" in directive_table


def test_canonical_publication_is_channel_relative_not_a_global_lifecycle() -> None:
    schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    lifecycle = schema["$defs"]["evidencePacketItem"]["properties"][
        "concept_lifecycle"
    ]["enum"]
    assert lifecycle == [
        "provisional",
        "reviewed",
        "validated",
        "contested",
        "superseded",
        "rejected",
        "deprecated",
    ]
    assert "canonical" not in schema["$defs"]["evidencePacketItem"]["properties"][
        "concept_lifecycle"
    ]["enum"]
    assert schema["$defs"]["channelPublicationState"]["enum"] == [
        "unpublished",
        "current",
        "historical",
        "withdrawn",
    ]
    assert "channel_id" in schema["$defs"]["canonicalSnapshot"]["required"]
    assert "channel_id" in schema["$defs"]["evidencePacket"]["required"]
    assert "channel_publication_state" in schema["$defs"]["evidencePacketItem"][
        "required"
    ]

    synthesis_schema = json.loads(
        (PACKAGE / "schemas" / "question-synthesis.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "canonical" not in synthesis_schema["$defs"]["synthesisState"]["enum"]

    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    retrieval = _markdown_section(storage, "### 12.4 Filtering")
    assert "snapshot membership for the selected channel" in retrieval
    assert "concept lifecycle is not a channel authorization filter" in retrieval.lower()

    state_model = (PACKAGE / "STATE_MODEL.md").read_text(encoding="utf-8")
    channel_state = _markdown_section(state_model, "## 5A. Channel publication state")
    assert (
        "same revision can have different channel publication states simultaneously"
        in channel_state.lower()
    )
    assert (
        "a revision may remain `validated` while it is current in a private channel"
        in state_model.lower()
    )
    assert "unpublished in a public channel" in state_model.lower()


def test_authoritative_records_share_one_total_sqlite_event_sequence() -> None:
    knowledge_schema = json.loads(
        (PACKAGE / "schemas" / "knowledge-system.schema.json").read_text(
            encoding="utf-8"
        )
    )
    knowledge_authoritative_definitions = {
        branch["$ref"].removeprefix("#/$defs/")
        for branch in knowledge_schema["oneOf"]
    } - {"knowledgeMutationCommand"}
    authoritative_definitions = {
        "knowledge-system.schema.json": knowledge_authoritative_definitions,
        "question-synthesis.schema.json": {
            "openQuestion",
            "questionTransition",
            "synthesis",
            "synthesisTransition",
        },
        "governance-registry.schema.json": {
            "knowledgePolicySet",
            "policyEvaluationReceipt",
            "entityRecord",
            "entityAlias",
            "identityResolutionDecision",
            "semanticRegistrySnapshot",
            "relationshipTypeDefinition",
            "publicationChannel",
        },
        "impact-serving.schema.json": {
            "uncertaintyRecord",
            "materialityAssessment",
            "knowledgeDependency",
            "knowledgeUseReceipt",
            "invalidationEvent",
            "impactAnalysis",
            "servingDirective",
        },
        "temporal-consistency.schema.json": {"historicalQueryReceipt"},
    }
    for filename, definitions in authoritative_definitions.items():
        schema = json.loads((PACKAGE / "schemas" / filename).read_text(encoding="utf-8"))
        assert schema["$defs"]["eventSequence"] == {
            "type": "integer",
            "minimum": 1,
        }
        for definition in definitions:
            contract = schema["$defs"][definition]
            assert "event_seq" in contract["required"], (filename, definition)
            assert contract["properties"]["event_seq"] == {
                "$ref": "#/$defs/eventSequence"
            }, (filename, definition)

    storage = (PACKAGE / "STORAGE_PROJECTION_AND_RETRIEVAL.md").read_text(
        encoding="utf-8"
    )
    event_table = _sql_table_body(storage, "knowledge_events")
    assert "event_seq INTEGER PRIMARY KEY AUTOINCREMENT" in event_table
    assert "event_id TEXT NOT NULL UNIQUE" in event_table
    assert "committed_at TEXT NOT NULL" in event_table

    authoritative_tables = {
        "STORAGE_PROJECTION_AND_RETRIEVAL.md": {
            "knowledge_sources",
            "knowledge_extraction_receipts",
            "knowledge_source_spans",
            "knowledge_candidates",
            "knowledge_candidate_claims",
            "knowledge_candidate_transitions",
            "knowledge_comparison_targets",
            "knowledge_reconciliation_proposals",
            "knowledge_reconciliation_decisions",
            "knowledge_concepts",
            "knowledge_concept_revisions",
            "knowledge_claim_bindings",
            "knowledge_relationships",
            "knowledge_reviews",
            "knowledge_lifecycle_transitions",
            "knowledge_publication_intents",
            "knowledge_snapshots",
            "knowledge_snapshot_members",
            "knowledge_snapshot_events",
            "knowledge_publication_receipts",
            "knowledge_channel_selection_events",
            "knowledge_projection_manifests",
            "knowledge_evidence_packets",
            "knowledge_freshness_assessments",
            "knowledge_revalidation_requests",
        },
        "OPEN_QUESTIONS_AND_SYNTHESIS.md": {
            "knowledge_open_questions",
            "knowledge_question_transitions",
            "knowledge_syntheses",
            "knowledge_synthesis_transitions",
        },
        "POLICY_IDENTITY_AND_REGISTRIES.md": {
            "knowledge_policy_sets",
            "knowledge_policy_transitions",
            "knowledge_policy_evaluations",
            "knowledge_entities",
            "knowledge_entity_aliases",
            "knowledge_identity_decisions",
            "knowledge_semantic_registry_snapshots",
            "knowledge_registry_transitions",
            "knowledge_publication_channels",
            "knowledge_channel_transitions",
        },
        "UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md": {
            "knowledge_uncertainties",
            "knowledge_materiality_assessments",
            "knowledge_dependencies",
            "knowledge_use_receipts",
            "knowledge_invalidation_events",
            "knowledge_impact_analyses",
            "knowledge_serving_directives",
        },
    }
    for filename, tables in authoritative_tables.items():
        document = (PACKAGE / filename).read_text(encoding="utf-8")
        for table in tables:
            body = _sql_table_body(document, table)
            assert "event_seq INTEGER NOT NULL UNIQUE" in body, (filename, table)
            assert re.search(
                r"(?:event_seq INTEGER NOT NULL UNIQUE\s+REFERENCES|"
                r"FOREIGN KEY\(event_seq\)\s+REFERENCES)\s+"
                r"knowledge_events\(event_seq\)",
                body,
            ), (filename, table)

    temporal = (PACKAGE / "TEMPORAL_CONSISTENCY_AND_HISTORY.md").read_text(
        encoding="utf-8"
    )
    reconstruction = _markdown_section(temporal, "## 6. Current-state projections")
    assert "ORDER BY event_seq" in reconstruction
    assert "timestamps are temporal facts, never ordering keys or tie-breakers" in reconstruction.lower()


def test_design_validation_does_not_claim_runtime_recovery_evidence() -> None:
    index = (PACKAGE / "README.md").read_text(encoding="utf-8")
    traceability = (PACKAGE / "DESIGN_TRACEABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    )
    test_plan = (PACKAGE / "TEST_AND_ACCEPTANCE_PLAN.md").read_text(encoding="utf-8")
    limitation = (
        "Static design validation is not runtime evidence for crash safety, "
        "concurrency, recovery, filesystem durability, or cross-platform behavior."
    )

    assert limitation in index
    assert limitation in traceability
    assert "Complete target design" not in index
    assert "defines every identified architectural and operational responsibility" not in traceability
    assert "Executable runtime fault, concurrency, and recovery tests remain mandatory" in test_plan


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
        "channel_publication_state",
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
        "superseded",
        "rejected",
        "deprecated",
    ]
    assert "draft" not in concept_lifecycle

    snapshot = schema_doc["$defs"]["canonicalSnapshot"]
    assert "snapshot_state" not in snapshot["required"]
    assert "status" not in snapshot["required"]
    assert "snapshot_state" not in snapshot["properties"]
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
    assert "UNIQUE(channel_id, attempt_sequence)" in storage
    assert "UNIQUE(channel_id, snapshot_sequence)" in storage
    assert "UNIQUE(channel_id, pointer_generation)" in storage
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
    assert "without granting those artifacts epistemic authority" in foundry
    assert "The foundry does **not**:" in foundry
    assert "The target is non-authorizing" in development_track


def test_phase3_traceability_maps_declared_concerns_without_runtime_claims() -> None:
    traceability = (PACKAGE / "DESIGN_TRACEABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    )
    rows = [line for line in traceability.splitlines() if line.startswith("|")]
    data_rows = [line for line in rows if "---" not in line and "Design concern" not in line]

    assert len(data_rows) >= 40
    assert all("**Defined**" in line for line in data_rows)
    assert "Residual uncertainties deliberately deferred" in traceability
    assert "Runtime evidence still required" in traceability


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
