import json
import sqlite3
import sys

import pytest

from erasmus.knowledge_runtime import KnowledgeRuntime, KnowledgeRuntimeError
from erasmus.migrations import apply_migrations
from erasmus.cli.main import main


def _seed_migrated_db(tmp_path, name: str = "knowledge.db") -> sqlite3.Connection:
    path = tmp_path / name
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    apply_migrations(db)
    return db


def _policy_payload(policy_id: str = "urn:erasmus:knowledge-policy:test", required_authorities: list[str] | tuple[str, ...] = ()):
    return {
        "contract": "erasmus.knowledge-policy/v1",
        "policy_id": policy_id,
        "version": "1.0.0",
        "policy_digest": {
            "algorithm": "sha256",
            "value": "0" * 64,
            "canonicalization": "canonical-json/v1",
        },
        "scope": {"visibility": "private", "tenant": "unit", "project": None, "labels": []},
        "status": "active",
        "effective_at": "2026-01-01T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "rules": [
            {
                "rule_id": "urn:erasmus:policy-rule:test-allow",
                "operations": ["knowledge:analyze"],
                "subject_kinds": ["candidate"],
                "risk_classes": ["routine"],
                "scope_selector": {},
                "source_requirements": {},
                "epistemic_requirements": {},
                "lifecycle_requirements": {},
                "freshness_requirements": {},
                "required_authorities": list(required_authorities),
                "required_reviews": [],
                "human_approval": "never",
                "tenth_man": {},
                "automation": "permit",
                "budgets": {},
                "retention": {},
                "publication": {},
                "fallback": "degrade",
                "priority": 1,
            }
        ],
        "created_by": "process:unit",
        "event_seq": 1,
        "review_ids": [],
    }


def _insert_policy(db: sqlite3.Connection, payload: dict[str, object]) -> None:
    db.execute(
        """
        INSERT INTO knowledge_policy_sets(
            policy_id, version, policy_digest, policy_json, status, scope_json,
            created_by, event_seq, review_ids_json, effective_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["policy_id"],
            payload["version"],
            json.dumps(payload["policy_digest"]),
            json.dumps(payload),
            payload["status"],
            json.dumps(payload["scope"]),
            payload["created_by"],
            payload["event_seq"],
            json.dumps(payload["review_ids"]),
            payload["effective_at"],
        ),
    )


def _request_payload(policy_id: str = "urn:erasmus:knowledge-policy:test", dry_run: bool = False) -> dict[str, object]:
    return {
        "contract": "erasmus.knowledge-request/v1",
        "request_id": "urn:erasmus:knowledge-request:unit",
        "operation": "knowledge:analyze",
        "actor": "process:unit",
        "authority": [],
        "idempotency_key": "urn:erasmus:idempotency:unit",
        "expected_revisions": {},
        "policy": {"policy_id": policy_id, "version": "1.0.0"},
        "registry_snapshot_id": "urn:erasmus:semantic-registry:default",
        "scope": {"visibility": "private", "tenant": "unit", "labels": []},
        "input": {"subject_kind": "candidate"},
        "evidence_ids": [],
        "review_ids": [],
        "budgets": {
            "timeout_seconds": 30.0,
            "retry_limit": 1,
            "max_model_calls": 1,
            "max_output_bytes": 1024,
        },
        "dry_run": dry_run,
        "requested_at": "2026-01-01T00:00:00Z",
    }


def test_knowledge_runtime_evaluate_policy_request_permits_and_persists(tmp_path):
    db = _seed_migrated_db(tmp_path)
    payload = _policy_payload()
    _insert_policy(db, payload)
    db.commit()

    runtime = KnowledgeRuntime(db)
    response = runtime.evaluate_policy_request(_request_payload(dry_run=False))

    assert response["ok"] is True
    assert response["failure"] is None
    assert response["receipts"][0]["decision"] == "permit"
    count = db.execute(
        "SELECT COUNT(*) FROM knowledge_policy_evaluations"
    ).fetchone()[0]
    assert count == 1


def test_knowledge_runtime_evaluate_policy_request_dry_run_does_not_persist(tmp_path):
    db = _seed_migrated_db(tmp_path)
    payload = _policy_payload()
    _insert_policy(db, payload)
    db.commit()

    runtime = KnowledgeRuntime(db)
    response = runtime.evaluate_policy_request(_request_payload(dry_run=True))

    assert response["ok"] is True
    assert db.execute("SELECT COUNT(*) FROM knowledge_policy_evaluations").fetchone()[0] == 0


def test_knowledge_runtime_evaluate_policy_request_requires_authority(tmp_path):
    db = _seed_migrated_db(tmp_path)
    payload = _policy_payload(required_authorities=("authority:required",))
    _insert_policy(db, payload)
    db.commit()

    runtime = KnowledgeRuntime(db)
    response = runtime.evaluate_policy_request(_request_payload(dry_run=False))

    assert response["ok"] is False
    assert response["failure"]["code"] == "missing_authority"
    assert response["next_actions"] == [{"kind": "obtain_authority", "authorities": ["authority:required"]}]


def test_knowledge_runtime_evaluate_policy_request_invalid_request_returns_failure():
    runtime = KnowledgeRuntime(sqlite3.connect(":memory:"))
    response = runtime.evaluate_policy_request({"bad": "payload"})

    assert response["ok"] is False
    assert response["failure"]["code"] == "invalid_request"


def test_knowledge_runtime_validate_contract_and_inspect_errors(tmp_path):
    policy = _policy_payload()
    assert KnowledgeRuntime.validate_knowledge_policy(policy)["valid"] is True

    db = _seed_migrated_db(tmp_path)
    runtime = KnowledgeRuntime(db)
    with pytest.raises(KnowledgeRuntimeError):
        runtime.inspect_policy("urn:erasmus:knowledge-policy:missing@1.0.0")


def test_knowledge_runtime_cli_validate_inspect_and_evaluate(tmp_path, monkeypatch, capsys):
    db = _seed_migrated_db(tmp_path, "cli.db")
    payload = _policy_payload()
    _insert_policy(db, payload)
    db.commit()
    db.close()

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(payload), encoding="utf-8")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_payload()), encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", str(tmp_path / "cli.db"), "knowledge-policy-validate", str(policy_path)]
    )
    main()
    assert json.loads(capsys.readouterr().out)["valid"] is True

    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", str(tmp_path / "cli.db"), "knowledge-policy-inspect", "urn:erasmus:knowledge-policy:test@1.0.0"]
    )
    main()
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["policy_id"] == payload["policy_id"]
    assert inspected["status"] == "active"

    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", str(tmp_path / "cli.db"), "knowledge-policy-evaluate", str(request_path)]
    )
    main()
    response = json.loads(capsys.readouterr().out)
    assert response["ok"] is True
    assert response["receipts"][0]["decision"] == "permit"
