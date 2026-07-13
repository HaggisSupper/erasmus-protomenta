"""Acceptance coverage for the deterministic cognitive immune cascade."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from erasmus.cli.main import main
from erasmus.immune import ImmuneCascade, ImmuneError, deterministic_screen
from erasmus.ledger import EpistemicLedger
from erasmus.store import Store


def _store(tmp_path, name="immune.db") -> Store:
    store = Store(str(tmp_path / name))
    store.init()
    return store


def _mutual_event(**overrides):
    event = {
        "event_type": "reasoning",
        "repeated_agreement": 4,
        "independent_sources": 0,
        "consequence": 0.4,
        "canonical_ref": "proposition:1",
        "context": {"topic": "causal claim"},
    }
    event.update(overrides)
    return event


def test_tier0_detects_all_known_boundary_violations():
    alerts = deterministic_screen(
        confidence_delta=0.4,
        new_evidence=0,
        authority_delta=1,
        consequence=0.8,
        provenance_present=False,
        forbidden_transition=True,
        direct_memory_to_belief=True,
    )
    assert {alert.detector for alert in alerts} == {
        "missing_provenance", "forbidden_transition", "confidence_without_evidence",
        "undeclared_authority", "direct_memory_to_belief",
    }


@pytest.mark.parametrize(
    ("event", "expected_agent", "expected_outcome"),
    [
        (
            _mutual_event(),
            "mutual-reinforcement-investigator",
            "request_counterevidence",
        ),
        (
            {
                "event_type": "comparison",
                "false_equivalence": True,
                "material_differences_omitted": True,
                "consequence": 0.4,
            },
            "false-equivalence-investigator",
            "flag",
        ),
        (
            {
                "event_type": "retrieval",
                "source_kind": "rag",
                "attempted_belief_promotion": True,
                "consequence": 0.4,
            },
            "provenance-contamination-investigator",
            "quarantine",
        ),
    ],
)
def test_only_matching_specialist_wakes_and_returns_to_sleep(
    tmp_path, event, expected_agent, expected_outcome
):
    cascade = ImmuneCascade(_store(tmp_path))
    result = cascade.process(event, "immune:inspect")

    assert {row["agent_id"] for row in result["findings"] if row["agent_id"]} == {
        expected_agent
    }
    assert result["findings"][0]["outcome"] == expected_outcome
    assert [row["to_state"] for row in result["agent_transitions"]] == [
        "awakened", "investigating", "mitigating", "monitoring", "sleeping"
    ]
    states = {row["agent_id"]: row["status"] for row in cascade.list_agents()}
    assert states[expected_agent] == "sleeping"


def test_investigators_never_mutate_canonical_ledger(tmp_path):
    store = _store(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence(
        "evidence", "observed", "observation", {"source": "sensor"},
        "primary", "2026-07-13", "lab", "tester", "evidence:write",
    )
    proposition = ledger.propose(
        "bounded claim", evidence, "tester", "ledger:write", "lab"
    )
    before = ledger.inspect(proposition)

    result = ImmuneCascade(store).process(
        {
            "event_type": "retrieval", "source_kind": "rag",
            "attempted_belief_promotion": True, "canonical_ref": f"proposition:{proposition}",
            "consequence": 0.7,
        },
        "immune:inspect",
    )

    after = ledger.inspect(proposition)
    assert after == before
    assert result["findings"][0]["mitigation"]["canonical_write"] is False
    assert result["findings"][0]["outcome"] == "quarantine"


def test_authority_and_event_provenance_fail_closed(tmp_path):
    store = _store(tmp_path)
    cascade = ImmuneCascade(store)
    with pytest.raises(ImmuneError, match="authority denied"):
        cascade.process(_mutual_event(), "ledger:write")
    with pytest.raises(ImmuneError, match="source event not found"):
        cascade.process(
            {"event_type": "observation", "source_event_id": 999}, "immune:inspect"
        )
    with pytest.raises(ImmuneError, match="unknown immune event fields"):
        cascade.process({"event_type": "x", "hidden_write": True}, "immune:inspect")


def test_incident_survives_restart_and_recurrence_wakes_again(tmp_path):
    path = str(tmp_path / "restart.db")
    first_store = Store(path)
    first_store.init()
    first = ImmuneCascade(first_store).process(_mutual_event(), "immune:inspect")
    first_store.db.close()

    reopened = Store(path)
    reopened.init()
    cascade = ImmuneCascade(reopened)
    assert cascade.inspect(first["id"])["fingerprint"] == first["fingerprint"]
    second = cascade.process(_mutual_event(), "immune:inspect")
    assert second["recurrence"] == 1
    assert second["agent_transitions"][0]["to_state"] == "awakened"


def test_regulator_suppresses_repeated_false_positive_activation(tmp_path):
    cascade = ImmuneCascade(_store(tmp_path))
    agent = "mutual-reinforcement-investigator"
    for index in range(2):
        result = cascade.process(
            _mutual_event(context={"topic": f"benign-{index}"}), "immune:inspect"
        )
        cascade.record_false_positive(
            result["id"], "mutual_reinforcement", "verified benign context",
            "protomentat", "immune:regulate", agent,
        )

    suppressed = cascade.process(_mutual_event(), "immune:inspect")
    assert suppressed["findings"][0]["outcome"] == "pass"
    assert "regulator suppressed" in suppressed["findings"][0]["rationale"]
    assert suppressed["agent_transitions"] == []


def test_non_pathological_low_prior_leap_is_tolerated(tmp_path):
    cascade = ImmuneCascade(_store(tmp_path))
    result = cascade.process(
        _mutual_event(event_type="leap", pathological=False), "immune:inspect"
    )
    assert result["findings"][0]["outcome"] == "pass"
    assert result["agent_transitions"] == []


def test_retired_agent_stays_dormant_and_tier0_still_flags(tmp_path):
    cascade = ImmuneCascade(_store(tmp_path))
    agent = "false-equivalence-investigator"
    cascade.retire_agent(
        agent, "operator disabled this specialist", "protomentat", "immune:regulate"
    )
    result = cascade.process(
        {
            "event_type": "comparison", "false_equivalence": True,
            "material_differences_omitted": True,
        },
        "immune:inspect",
    )
    assert result["findings"][0]["outcome"] == "flag"
    assert result["findings"][0]["agent_id"] is None
    assert result["agent_transitions"] == []
    states = {row["agent_id"]: row["status"] for row in cascade.list_agents()}
    assert states[agent] == "retired"


def test_consequential_unresolved_incident_escalates_to_protomentat(tmp_path):
    result = ImmuneCascade(_store(tmp_path)).process(
        _mutual_event(consequence=0.9), "immune:inspect"
    )
    finding = result["findings"][0]
    assert finding["outcome"] == "escalate"
    assert finding["mitigation"]["recipient"] == "protomentat"
    assert "escalated" in [row["to_state"] for row in result["agent_transitions"]]


def test_immune_audit_records_are_append_only(tmp_path):
    store = _store(tmp_path)
    result = ImmuneCascade(store).process(_mutual_event(), "immune:inspect")
    for sql in (
        "DELETE FROM immune_incidents WHERE id = ?",
        "UPDATE immune_findings SET rationale = 'hidden' WHERE incident_id = ?",
        "DELETE FROM immune_agent_transitions WHERE incident_id = ?",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(sql, (result["id"],))


def test_cli_processes_and_inspects_incident(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_mutual_event()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "immune-process", str(event_path),
        "--authority", "immune:inspect",
    ])
    main()
    incident_id = json.loads(capsys.readouterr().out)["id"]

    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "immune-inspect", str(incident_id),
    ])
    main()
    assert json.loads(capsys.readouterr().out)["findings"][0]["agent_id"] == (
        "mutual-reinforcement-investigator"
    )
