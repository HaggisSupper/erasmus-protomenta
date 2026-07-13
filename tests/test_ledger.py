"""Acceptance coverage for the append-only epistemic ledger (Mission 04)."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from erasmus.checkpoint import Checkpoint, load_latest_checkpoint, save_checkpoint
from erasmus.cli.main import main
from erasmus.ledger import EpistemicLedger, LedgerError
from erasmus.store import Store


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "ledger.db"))
    store.init()
    return store


def _evidence(
    ledger: EpistemicLedger,
    content: str = "measured observation",
    *,
    record_type: str = "evidence",
    source_kind: str = "observation",
    trust: str = "primary",
    scope: str = "lab",
    provenance: dict | None = None,
    supersedes_id: int | None = None,
) -> int:
    return ledger.add_evidence(
        record_type=record_type,
        content=content,
        source_kind=source_kind,
        provenance=provenance or {"source": "instrument-7", "sample": "A"},
        trust_class=trust,
        effective_date="2026-07-13",
        scope=scope,
        actor="tester",
        authority="evidence:write",
        supersedes_id=supersedes_id,
    )


def _proposition(
    ledger: EpistemicLedger,
    statement: str = "Treatment A changes outcome B",
    *,
    status: str = "speculative",
    scope: str = "lab",
) -> tuple[int, int]:
    origin = _evidence(ledger, f"origin for {statement}", scope=scope)
    proposition_id = ledger.propose(
        statement, origin, "tester", "ledger:write", scope, status
    )
    return proposition_id, origin


@pytest.mark.parametrize("initial", ["speculative", "analogy", "leap", "unresolved"])
def test_initial_states_promote_only_through_explicit_support(tmp_path, initial):
    ledger = EpistemicLedger(_store(tmp_path))
    proposition_id, _ = _proposition(ledger, f"claim from {initial}", status=initial)

    support = _evidence(ledger, "independent replication")
    assert ledger.transition(
        proposition_id, "support", support, "tester", "ledger:write",
        "independent evidence", "plausible",
    ) == "plausible"


def test_full_support_and_contradiction_lifecycle_is_auditable(tmp_path):
    ledger = EpistemicLedger(_store(tmp_path))
    proposition_id, _ = _proposition(ledger)

    for target in ("plausible", "supported", "established"):
        support = _evidence(
            ledger, f"support for {target}", trust="deterministic" if target == "established" else "primary"
        )
        assert ledger.transition(
            proposition_id, "support", support, "tester", "ledger:write",
            f"advance to {target}", target,
        ) == target

    contradiction = _evidence(
        ledger, "controlled counterexample", record_type="contradiction",
        trust="deterministic",
    )
    assert ledger.transition(
        proposition_id, "contradict", contradiction, "tester", "ledger:write",
        "counterexample reproduced",
    ) == "contradicted"

    renewed = _evidence(ledger, "revised controlled result", trust="deterministic")
    assert ledger.transition(
        proposition_id, "support", renewed, "tester", "ledger:write",
        "contradiction resolved", "supported",
    ) == "supported"

    inspected = ledger.inspect(proposition_id)
    assert inspected["status"] == "supported"
    assert [row["operation"] for row in inspected["transitions"]] == [
        "propose", "support", "support", "support", "contradict", "support"
    ]
    queried = ledger.query(proposition_id)
    assert queried["strongest_support"]["id"] == renewed
    assert queried["strongest_contradiction"]["id"] == contradiction


def test_falsification_requires_test_and_wrongness_then_can_reopen(tmp_path):
    ledger = EpistemicLedger(_store(tmp_path))
    proposition_id, origin = _proposition(ledger)
    test_id = _evidence(
        ledger, "If A is true, sensor C must rise", record_type="falsification_test",
        source_kind="test",
    )
    wrongness = _evidence(
        ledger, "Sensor C fell in the registered test",
        record_type="tangible_wrongness", source_kind="test", trust="deterministic",
    )

    with pytest.raises(LedgerError, match="tangible wrongness and a test"):
        ledger.transition(
            proposition_id, "falsify", origin, "tester", "ledger:write", "failed", test_id=test_id
        )
    with pytest.raises(LedgerError, match="tangible wrongness and a test"):
        ledger.transition(
            proposition_id, "falsify", wrongness, "tester", "ledger:write", "failed"
        )

    assert ledger.transition(
        proposition_id, "falsify", wrongness, "tester", "ledger:write",
        "registered prediction failed", test_id=test_id,
    ) == "falsified"
    assert ledger.query(proposition_id)["unresolved_tests"] == []

    with pytest.raises(LedgerError, match="new evidence"):
        ledger.transition(
            proposition_id, "reopen", origin, "tester", "ledger:write", "old evidence"
        )
    new_evidence = _evidence(ledger, "new calibration changes the interpretation")
    assert ledger.transition(
        proposition_id, "reopen", new_evidence, "tester", "ledger:write",
        "new post-falsification evidence",
    ) == "unresolved"
    assert ledger.query(proposition_id)["unresolved_tests"][0]["id"] == test_id


def test_rag_and_confidence_cannot_promote_a_proposition(tmp_path):
    ledger = EpistemicLedger(_store(tmp_path))
    proposition_id, _ = _proposition(ledger)
    rag = _evidence(
        ledger, "retrieved passage", source_kind="rag", trust="contextual",
        provenance={"document": "memo-4", "chunk": 9},
    )

    assert ledger.inspect(proposition_id)["status"] == "speculative"
    assert all(item["id"] != rag for item in ledger.inspect(proposition_id)["evidence"])

    ledger.record_confidence(
        proposition_id, 0.99, rag, "tester", "ledger:write", "retrieval score"
    )
    inspected = ledger.inspect(proposition_id)
    assert inspected["confidence"] == 0.99
    assert inspected["status"] == "speculative"
    assert len(inspected["transitions"]) == 1
    assert inspected["confidence_history"][-1]["evidence_id"] == rag


@pytest.mark.parametrize("basis", ["agreement", "repetition"])
def test_agreement_and_repetition_are_not_promotion_evidence(tmp_path, basis):
    ledger = EpistemicLedger(_store(tmp_path))
    proposition_id, _ = _proposition(ledger)
    weak = _evidence(
        ledger, "the model said it again", source_kind="model",
        provenance={"basis": basis, "model": "local"},
    )
    with pytest.raises(LedgerError, match="not promotion evidence"):
        ledger.transition(
            proposition_id, "support", weak, "tester", "ledger:write",
            "repeat", "plausible",
        )


def test_evidence_validation_and_authority_fail_closed(tmp_path):
    store = _store(tmp_path)
    ledger = EpistemicLedger(store)
    kwargs = dict(
        record_type="evidence", content="x", source_kind="human",
        provenance={"source": "reviewer"}, trust_class="primary",
        effective_date="2026-07-13", scope="lab", actor="tester",
        authority="evidence:write",
    )
    with pytest.raises(LedgerError, match="provenance"):
        ledger.add_evidence(**{**kwargs, "provenance": {}})
    with pytest.raises(LedgerError, match="authority denied"):
        ledger.add_evidence(**{**kwargs, "authority": "read"})
    with pytest.raises(LedgerError, match="record type"):
        ledger.add_evidence(**{**kwargs, "record_type": "opinion"})
    with pytest.raises(LedgerError, match="source kind"):
        ledger.add_evidence(**{**kwargs, "source_kind": "unknown"})
    with pytest.raises(LedgerError, match="source event not found"):
        ledger.add_evidence(**{**kwargs, "source_event_id": 999})


def test_append_only_records_and_supersession_preserve_audit_history(tmp_path):
    store = _store(tmp_path)
    ledger = EpistemicLedger(store)
    proposition_id, origin = _proposition(ledger)
    successor = _evidence(ledger, "corrected measurement", supersedes_id=origin)

    inspected = ledger.inspect(proposition_id)
    assert inspected["evidence"][0]["id"] == origin
    assert inspected["evidence"][0]["superseded_by"] == successor
    assert ledger.query(proposition_id)["strongest_support"] is None

    for sql, parameters in (
        ("UPDATE propositions SET statement = 'changed' WHERE id = ?", (proposition_id,)),
        ("DELETE FROM epistemic_evidence WHERE id = ?", (origin,)),
        ("DELETE FROM proposition_transitions WHERE proposition_id = ?", (proposition_id,)),
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(sql, parameters)


def test_proposition_supersession_closes_path_without_deletion(tmp_path):
    ledger = EpistemicLedger(_store(tmp_path))
    original, _ = _proposition(ledger, "old bounded claim")
    replacement, replacement_origin = _proposition(ledger, "revised bounded claim")
    ledger.supersede(
        original, replacement, replacement_origin, "tester", "ledger:write",
        "scope-preserving correction",
    )

    assert ledger.inspect(original)["superseded_by"] == replacement
    closed = ledger.query(replacement)["relevant_closed_paths"]
    assert any(row["id"] == original and row["replacement_id"] == replacement for row in closed)
    with pytest.raises(LedgerError, match="already superseded"):
        ledger.supersede(
            original, replacement, replacement_origin, "tester", "ledger:write", "again"
        )


def test_checkpoint_references_proposition_without_copying_ledger(tmp_path):
    store = _store(tmp_path)
    ledger = EpistemicLedger(store)
    proposition_id, _ = _proposition(ledger)
    event_id = store.add_event("observation", "{}")
    checkpoint = Checkpoint(
        frontier="active boundary", proposition="display summary only",
        strongest_support="support summary", strongest_contradiction="counter summary",
        unresolved_tension="open test", active_mode="analysis", next_move="run test",
        source_event_ids=[event_id], proposition_id=proposition_id,
    )
    save_checkpoint(store, checkpoint)
    assert load_latest_checkpoint(store) == checkpoint
    assert store.db.execute(
        "SELECT COUNT(*) FROM proposition_transitions WHERE proposition_id = ?",
        (proposition_id,),
    ).fetchone()[0] == 1

    checkpoint.proposition_id = 999
    with pytest.raises(ValueError, match="proposition_id does not exist"):
        save_checkpoint(store, checkpoint)


def test_cli_can_add_propose_and_inspect(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "ledger-evidence-add", "observed result",
        "--type", "evidence", "--source-kind", "observation",
        "--provenance", '{"source":"sensor"}', "--trust", "primary",
        "--effective-date", "2026-07-13", "--scope", "lab",
        "--actor", "operator", "--authority", "evidence:write",
    ])
    main()
    evidence_id = json.loads(capsys.readouterr().out)["evidence_id"]

    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "ledger-propose", "CLI claim", str(evidence_id),
        "--scope", "lab", "--actor", "operator", "--authority", "ledger:write",
    ])
    main()
    proposition_id = json.loads(capsys.readouterr().out)["proposition_id"]

    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "ledger-inspect", str(proposition_id),
    ])
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "speculative"
