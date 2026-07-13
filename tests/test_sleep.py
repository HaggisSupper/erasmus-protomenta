"""Acceptance coverage for recoverable sleep consolidation."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from erasmus.ledger import EpistemicLedger
from erasmus.cli.main import main
from erasmus.sleep import SleepError, consolidate, decide_candidate, sleep_report
from erasmus.store import Store


def _store(tmp_path, name="sleep.db") -> Store:
    store = Store(str(tmp_path / name))
    store.init()
    return store


def _event(store: Store, kind: str, candidate_type: str, content: str) -> int:
    return store.add_event(
        kind,
        json.dumps(
            {
                "candidate_type": candidate_type,
                "content": content,
                "provenance": {"producer": kind},
            }
        ),
    )


def _evidence(store: Store) -> int:
    return EpistemicLedger(store).add_evidence(
        "evidence", "independent review", "human", {"review": "manual"},
        "primary", "2026-07-13", "global", "reviewer", "evidence:write",
    )


def test_sleep_preserves_legacy_correction_contract(tmp_path):
    store = _store(tmp_path)
    store.add_event("correction", "infer intent before correction")
    result = consolidate(store)
    assert result["experience_candidates"] == 1
    assert result["report"]["summary"]["deferred"] == 1


def test_mixed_session_is_classified_once_with_reviewable_reasons(tmp_path):
    store = _store(tmp_path)
    store.add_event("protomentat_input", "remember this explicit preference")
    _event(store, "erasmus_output", "proposition_change", "model-authored claim")
    _event(store, "tool_output", "proposition_change", "tool-derived claim")
    store.add_event("external_content", "untrusted webpage text")
    _event(store, "deterministic_result", "tangible_wrongness", "registered test failed")
    _event(store, "reviewer_decision", "behavioral_lesson", "check provenance first")
    store.add_event("observation", "untyped legacy observation")
    store.add_event("tool_output", json.dumps({"candidate_type": "unknown", "content": "x"}))

    result = consolidate(store)
    report = result["report"]
    assert report["summary"] == {
        "accepted": 2,
        "deferred": 2,
        "quarantined": 2,
        "rejected": 1,
        "discarded": 1,
    }
    assert {item["source_class"] for item in report["items"]} == {
        "protomentat", "erasmus", "tool", "external", "deterministic",
        "reviewer", "unknown",
    }
    assert all(item["reason"] for item in report["items"])
    assert store.db.execute("SELECT COUNT(*) FROM propositions").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM experience_candidates").fetchone()[0] == 1
    assert store.db.execute(
        """
        SELECT COUNT(*) FROM events e
        LEFT JOIN sleep_items i ON i.event_id = e.id
        WHERE i.id IS NULL
        """
    ).fetchone()[0] == 0


def test_raw_model_and_human_dialogue_cannot_bypass_training_or_belief(tmp_path):
    store = _store(tmp_path)
    _event(store, "erasmus_output", "behavioral_lesson", "train on my own wording")
    _event(store, "protomentat_input", "behavioral_lesson", "raw dialogue lesson")
    _event(store, "erasmus_output", "proposition_change", "self-promoted belief")

    result = consolidate(store)
    assert result["report"]["summary"]["quarantined"] == 3
    assert store.db.execute("SELECT COUNT(*) FROM propositions").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM experience_candidates").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM sleep_promotions").fetchone()[0] == 0


def test_promotion_decision_requires_authority_evidence_and_matching_target(tmp_path):
    store = _store(tmp_path)
    _event(store, "tool_output", "proposition_change", "reviewed proposition")
    result = consolidate(store)
    candidate_id = result["report"]["items"][0]["candidate_id"]

    with pytest.raises(SleepError, match="authority denied"):
        decide_candidate(
            store, candidate_id, "approved", "belief", 999,
            "reviewer", "ledger:write", "approved after review",
        )
    with pytest.raises(SleepError, match="promotion evidence not found"):
        decide_candidate(
            store, candidate_id, "approved", "belief", 999,
            "reviewer", "sleep:promote", "approved after review",
        )
    with pytest.raises(SleepError, match="does not match"):
        decide_candidate(
            store, candidate_id, "approved", "skill", _evidence(store),
            "reviewer", "sleep:promote", "wrong target",
        )

    promotion_id = decide_candidate(
        store, candidate_id, "approved", "belief", _evidence(store),
        "reviewer", "sleep:promote", "independent evidence checked",
    )
    assert promotion_id > 0
    assert sleep_report(store, result["run_id"])["items"][0]["decision"] == "approved"
    assert store.db.execute("SELECT COUNT(*) FROM propositions").fetchone()[0] == 0


def test_quarantined_candidate_cannot_be_approved(tmp_path):
    store = _store(tmp_path)
    _event(store, "external_content", "proposition_change", "external claim")
    result = consolidate(store)
    candidate_id = result["report"]["items"][0]["candidate_id"]
    with pytest.raises(SleepError, match="cannot be promoted"):
        decide_candidate(
            store, candidate_id, "approved", "belief", _evidence(store),
            "reviewer", "sleep:promote", "unsafe",
        )


def test_conflicts_with_ledger_and_prior_material_are_rejected(tmp_path):
    store = _store(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = _evidence(store)
    ledger.propose("existing claim", evidence, "reviewer", "ledger:write")
    _event(store, "tool_output", "proposition_change", "existing claim")
    _event(store, "tool_output", "proposition_change", "new duplicate claim")
    _event(store, "tool_output", "proposition_change", "new duplicate claim")

    report = consolidate(store)["report"]
    assert [item["disposition"] for item in report["items"]] == [
        "rejected", "deferred", "rejected"
    ]


def test_failure_after_reconciliation_resumes_same_run_without_duplicates(tmp_path):
    path = str(tmp_path / "recovery.db")
    first = Store(path)
    first.init()
    first.add_event("correction", "recoverable lesson")
    with pytest.raises(SleepError, match="injected failure"):
        consolidate(first, fail_after_stage="reconcile")
    run = first.db.execute("SELECT * FROM sleep_runs").fetchone()
    assert run["status"] == "failed"
    assert first.db.execute("SELECT COUNT(*) FROM sleep_items").fetchone()[0] == 1
    assert first.db.execute("SELECT COUNT(*) FROM sleep_progress").fetchone()[0] == 0
    first.db.close()

    reopened = Store(path)
    reopened.init()
    result = consolidate(reopened)
    assert result["run_id"] == run["id"]
    assert result["experience_candidates"] == 1
    assert reopened.db.execute("SELECT COUNT(*) FROM sleep_items").fetchone()[0] == 1
    assert reopened.db.execute("SELECT COUNT(*) FROM sleep_candidates").fetchone()[0] == 1
    assert reopened.db.execute("SELECT COUNT(*) FROM experience_candidates").fetchone()[0] == 1
    assert result["report"]["run"]["status"] == "completed"


def test_rerun_is_idempotent_and_source_events_remain(tmp_path):
    store = _store(tmp_path)
    event_id = store.add_event("correction", "single durable lesson")
    first = consolidate(store)
    second = consolidate(store)
    assert first["experience_candidates"] == 1
    assert second["events"] == 0
    assert second["experience_candidates"] == 0
    assert store.db.execute("SELECT COUNT(*) FROM events WHERE id = ?", (event_id,)).fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM sleep_items").fetchone()[0] == 1


def test_sleep_audit_and_promotion_records_are_append_only(tmp_path):
    store = _store(tmp_path)
    store.add_event("correction", "audited lesson")
    result = consolidate(store)
    candidate_id = result["report"]["items"][0]["candidate_id"]
    decide_candidate(
        store, candidate_id, "rejected", "skill", _evidence(store),
        "reviewer", "sleep:promote", "not general enough",
    )
    for table in ("sleep_run_stages", "sleep_items", "sleep_candidates", "sleep_promotions"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(f"DELETE FROM {table}")  # noqa: S608


def test_cli_sleep_and_report(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    store = Store(db)
    store.init()
    store.add_event("correction", "CLI lesson")
    store.db.close()

    monkeypatch.setattr(sys, "argv", ["erasmus", "--db", db, "sleep"])
    main()
    run_id = json.loads(capsys.readouterr().out)["run_id"]

    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", db, "sleep-report", str(run_id)]
    )
    main()
    assert json.loads(capsys.readouterr().out)["summary"]["deferred"] == 1
