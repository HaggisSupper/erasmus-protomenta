from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from erasmus.knowledge_runtime import KnowledgeRuntime
from erasmus.store import Store


def _runtime(tmp_path: Path) -> tuple[Store, KnowledgeRuntime]:
    store = Store(str(tmp_path / "adversarial.db"))
    store.init()
    store.init_phase3()
    return store, KnowledgeRuntime(store, tmp_path / "knowledge")


def _scope(tenant: str = "local") -> dict:
    return {
        "visibility": "private",
        "tenant": tenant,
        "project": "phase3",
        "domain": None,
        "labels": [],
    }


def test_same_source_bytes_cannot_be_silently_rebound_to_another_scope(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    rt.register_source_bytes(
        b"same bytes", "a.txt", "text/plain", _scope("alpha"),
        "human:scott", "knowledge:source-register",
    )
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        rt.register_source_bytes(
            b"same bytes", "b.txt", "text/plain", _scope("beta"),
            "human:scott", "knowledge:source-register",
        )


def test_source_span_must_preserve_parent_source_scope(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    source = rt.register_source_bytes(
        b"evidence", "a.txt", "text/plain", _scope("alpha"),
        "human:scott", "knowledge:source-register",
    )
    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        rt.register_source_span(
            source["source_id"],
            {"kind": "text-lines", "data": {"start": 1, "end": 1}},
            "evidence",
            _scope("beta"),
            "human:scott",
            "knowledge:source-register",
        )


def test_source_registration_persists_authority_and_idempotency_provenance(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    source = rt.register_source_bytes(
        b"audited", "audit.txt", "text/plain", _scope(),
        "human:scott", "knowledge:source-register",
    )
    row = store.db.execute(
        "SELECT authority, idempotency_key FROM knowledge_sources WHERE source_id=?",
        (source["source_id"],),
    ).fetchone()
    assert row is not None
    assert row["authority"] == "knowledge:source-register"
    assert row["idempotency_key"] == source["source_id"]


def test_phase3_governance_history_rejects_update_and_delete(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    source = rt.register_source_bytes(
        b"identity", "id.txt", "text/plain", _scope(),
        "human:scott", "knowledge:source-register",
    )
    span = rt.register_source_span(
        source["source_id"],
        {"kind": "text-lines", "data": {"start": 1, "end": 1}},
        "identity", _scope(), "human:scott", "knowledge:source-register",
    )
    candidate = rt.import_candidate(
        "foundry/v1", "Identity", "identity", [source["source_id"]],
        [span["span_id"]], _scope(), "human:scott", "knowledge:candidate-import",
    )
    claim = rt.add_candidate_claim(
        candidate["candidate_id"], "identity", [span["span_id"]], {}, _scope(),
        "routine", "human:scott", "knowledge:claim-decompose",
    )
    left = rt.create_entity("component", "left", _scope(), "human:scott", "knowledge:identity-write")
    right = rt.create_entity("component", "right", _scope(), "human:scott", "knowledge:identity-write")
    identity = rt.record_identity_decision(
        left["entity_id"], right["entity_id"], "distinct_entity",
        "human:scott", "knowledge:identity-decide", "reviewed",
    )
    reconciliation = rt.reconcile_claim(
        claim["candidate_claim_id"], "reject", "human:scott", "knowledge:reconcile",
        mission_id=1, idempotency_key="reject-identity",
    )

    immutable_rows = [
        ("knowledge_identity_decisions", "decision_id", identity["decision_id"]),
        ("knowledge_reconciliation_decisions", "decision_id", reconciliation["decision_id"]),
    ]
    for table, key, value in immutable_rows:
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute(f"UPDATE {table} SET actor='human:tamper' WHERE {key}=?", (value,))
        with pytest.raises(sqlite3.IntegrityError):
            store.db.execute(f"DELETE FROM {table} WHERE {key}=?", (value,))
        store.db.rollback()
