"""Mission 09 inspectable skill-promotion and adapter-readiness coverage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys

import pytest

from erasmus.cli.main import main
from erasmus.context import assemble_context
from erasmus.ledger import EpistemicLedger
from erasmus.skills import SkillPromotionEngine, SkillPromotionError
from erasmus.sleep import consolidate, decide_candidate
from erasmus.store import Store


CATEGORIES = (
    "intent_inference",
    "false_equivalence",
    "anti_sycophancy",
    "doubt_placement",
    "cut_stop_decision",
)
METRICS = (
    "factual_accuracy", "dissent_preservation", "sycophancy", "overconfidence"
)


def _store(tmp_path, name="skills.db") -> Store:
    store = Store(str(tmp_path / name))
    store.init()
    return store


def _evidence(store: Store, label: str) -> int:
    return EpistemicLedger(store).add_evidence(
        "evidence", label, "human", {"review": label}, "primary",
        "2026-07-13", "skills", "reviewer", "evidence:write",
    )


def _gated_candidate(store: Store, lesson="infer intent before intervening") -> int:
    source_event_id = store.add_event("reviewer_decision", json.dumps({
        "candidate_type": "behavioral_lesson",
        "content": lesson,
        "provenance": {"review": "manual"},
    }))
    report = consolidate(store)["report"]
    sleep_candidate_id = next(
        item["candidate_id"] for item in report["items"]
        if item["event_id"] == source_event_id
    )
    decide_candidate(
        store, sleep_candidate_id, "approved", "skill", _evidence(store, "sleep gate"),
        "reviewer", "sleep:promote", "eligible for repeated behavioral evidence",
    )
    return store.db.execute(
        "SELECT id FROM experience_candidates WHERE source_event_id = ?",
        (source_event_id,),
    ).fetchone()[0]


def _observe(
    engine: SkillPromotionEngine, candidate_id: int, label: str, *,
    contamination="clean", outcome="success", confidence=0.8,
) -> int:
    source_event_id = engine.store.add_event("observation", label)
    evidence_id = _evidence(engine.store, label)
    engine.observe(
        candidate_id, source_event_id=source_event_id,
        intervention_mode="clarify_then_answer", observed_effect=label,
        outcome=outcome, contamination_status=contamination,
        confidence=confidence, evidence_id=evidence_id,
        actor="reviewer", authority="skill:promote",
    )
    return evidence_id


def _artifact(evidence_ids):
    return {
        "trigger": "intent is ambiguous before a consequential intervention",
        "behavior": "state the inferred intent and ask one bounded clarification",
        "exclusions": ["trivial reversible choices"],
        "examples": ["Confirm whether cut means shorten or remove."],
        "counterexamples": ["Do not ask when the user already specified the target."],
        "evidence": list(evidence_ids),
        "version": "1.0.0",
        "owner": "protomentat",
        "rollback": "retire the artifact and restore constitution-only behavior",
    }


def _fixtures(*, passing=True):
    good = {
        "factual_accuracy": True, "dissent_preservation": True,
        "sycophancy": False, "overconfidence": False,
    }
    bad = {
        "factual_accuracy": False, "dissent_preservation": False,
        "sycophancy": True, "overconfidence": True,
    }
    fixtures = []
    for index, category in enumerate(CATEGORIES):
        baseline, skill = (bad, good) if passing else (good, dict(good))
        if not passing and index == 0:
            skill = dict(good, factual_accuracy=False)
        fixtures.append({
            "id": f"held-out-{index}", "category": category,
            "baseline": dict(baseline), "skill": dict(skill),
        })
    return fixtures


def _drafted(store: Store, lesson="infer intent before intervening"):
    engine = SkillPromotionEngine(store)
    candidate_id = _gated_candidate(store, lesson)
    evidence_ids = [
        _observe(engine, candidate_id, "success one"),
        _observe(engine, candidate_id, "success two"),
    ]
    engine.promote(
        candidate_id, "repeated_evidence", "reviewer", "skill:promote",
        "two independent successes",
    )
    artifact_id = engine.draft(
        candidate_id, _artifact(evidence_ids), "reviewer", "skill:promote",
        "inspectable draft",
    )
    return engine, candidate_id, artifact_id


def _approved(store: Store, lesson="infer intent before intervening"):
    engine, candidate_id, artifact_id = _drafted(store, lesson)
    evaluation = engine.evaluate(
        candidate_id, _fixtures(), "reviewer", "skill:promote",
        "held-out comparison",
    )
    engine.promote(
        candidate_id, "approved", "protomentat", "skill:promote",
        "benefit without regression",
    )
    return engine, candidate_id, artifact_id, evaluation


def _context(store: Store):
    return assemble_context(
        store, constitution="constitution", prompt_artifact="prompt",
        budgets={
            "total": 100, "constitution": 10, "checkpoint": 10,
            "propositions": 10, "adaptations": 50, "evidence": 10,
            "dialogue": 10,
        },
    )


def test_raw_or_single_observation_cannot_cross_sleep_and_repetition_gates(tmp_path):
    store = _store(tmp_path)
    raw_event = store.add_event("observation", "raw dialogue")
    with store.db:
        raw_candidate = store.db.execute(
            """
            INSERT INTO experience_candidates(lesson, status, created_at, source_event_id)
            VALUES('raw lesson', 'candidate', CURRENT_TIMESTAMP, ?)
            """,
            (raw_event,),
        )
    engine = SkillPromotionEngine(store)
    with pytest.raises(SkillPromotionError, match="sleep promotion gate"):
        engine.observe(
            int(raw_candidate.lastrowid), source_event_id=raw_event,
            intervention_mode="none", observed_effect="none", outcome="success",
            contamination_status="clean", confidence=0.8,
            evidence_id=_evidence(store, "raw"), actor="reviewer",
            authority="skill:promote",
        )

    candidate_id = _gated_candidate(store)
    with pytest.raises(SkillPromotionError, match="authority denied"):
        engine.observe(
            candidate_id, source_event_id=store.add_event("observation", "denied"),
            intervention_mode="clarify", observed_effect="better", outcome="success",
            contamination_status="clean", confidence=0.8,
            evidence_id=_evidence(store, "denied"), actor="reviewer",
            authority="skill:export",
        )
    _observe(engine, candidate_id, "only success")
    with pytest.raises(SkillPromotionError, match="two clean successful"):
        engine.promote(
            candidate_id, "repeated_evidence", "reviewer", "skill:promote",
            "too early",
        )


def test_candidate_to_approved_skill_survives_restart_and_activates(tmp_path):
    path = str(tmp_path / "restart.db")
    store = Store(path)
    store.init()
    engine, candidate_id, artifact_id = _drafted(store)
    store.db.close()

    reopened = Store(path)
    reopened.init()
    engine = SkillPromotionEngine(reopened)
    evaluation = engine.evaluate(
        candidate_id, _fixtures(), "reviewer", "skill:promote", "replay passed"
    )
    engine.promote(
        candidate_id, "approved", "protomentat", "skill:promote", "approve"
    )
    inspected = engine.inspect(candidate_id)
    assert inspected["promotion_state"] == "approved"
    assert inspected["repeated_successes"] == 2
    assert inspected["repeated_failures"] == 0
    assert inspected["contamination_status"] == "clean"
    assert inspected["confidence"] == pytest.approx(0.8)
    assert inspected["artifact"]["id"] == artifact_id
    assert evaluation["passed"] is True
    assert set(evaluation["baseline_metrics"]) == set(METRICS)
    adaptation = next(section for section in _context(reopened).sections if section.name == "adaptations")
    assert "ask one bounded clarification" in adaptation.content
    assert adaptation.authority == "approved_skill"


def test_failed_held_out_evaluation_rejects_and_cannot_activate(tmp_path):
    store = _store(tmp_path)
    engine, candidate_id, _ = _drafted(store, "preserve factual dissent")
    evaluation = engine.evaluate(
        candidate_id, _fixtures(passing=False), "reviewer", "skill:promote",
        "factual regression",
    )
    assert evaluation["passed"] is False
    assert "factual_accuracy" in evaluation["regressions"]
    assert engine.inspect(candidate_id)["promotion_state"] == "rejected"
    with pytest.raises(SkillPromotionError, match="invalid promotion transition"):
        engine.promote(
            candidate_id, "approved", "reviewer", "skill:promote", "bypass failure"
        )
    assert "ask one bounded clarification" not in next(
        section for section in _context(store).sections if section.name == "adaptations"
    ).content


def test_contamination_blocks_promotion_and_unauthorized_rows(tmp_path):
    store = _store(tmp_path)
    candidate_id = _gated_candidate(store, "avoid contaminated adaptation")
    engine = SkillPromotionEngine(store)
    _observe(engine, candidate_id, "clean success")
    _observe(engine, candidate_id, "quarantined success", contamination="quarantined")
    with pytest.raises(SkillPromotionError, match="contaminated or quarantined"):
        engine.promote(
            candidate_id, "repeated_evidence", "reviewer", "skill:promote", "unsafe"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute(
            """
            INSERT INTO skill_observations(
                candidate_id, source_event_id, evidence_id, intervention_mode,
                observed_effect, outcome, contamination_status, confidence, actor, authority
            ) VALUES(?, ?, ?, 'x', 'x', 'success', 'clean', 1, 'x', 'unauthorized')
            """,
            (
                candidate_id, store.add_event("observation", "unauthorized"),
                _evidence(store, "unauthorized"),
            ),
        )
    store.db.rollback()
    exported = engine.export_readiness("reviewer", "skill:export")
    assert exported["manifest"]["entries"] == []
    assert exported["report"]["ready"] is False
    assert exported["report"]["excluded"]


def test_artifact_requires_complete_fields_and_observation_evidence(tmp_path):
    store = _store(tmp_path)
    engine = SkillPromotionEngine(store)
    candidate_id = _gated_candidate(store)
    evidence_ids = [
        _observe(engine, candidate_id, "success one"),
        _observe(engine, candidate_id, "success two"),
    ]
    engine.promote(
        candidate_id, "repeated_evidence", "reviewer", "skill:promote", "enough"
    )
    incomplete = _artifact(evidence_ids)
    incomplete.pop("rollback")
    with pytest.raises(SkillPromotionError, match="artifact fields"):
        engine.draft(
            candidate_id, incomplete, "reviewer", "skill:promote", "incomplete"
        )
    unrelated = _artifact([*evidence_ids, _evidence(store, "unrelated")])
    with pytest.raises(SkillPromotionError, match="clean observation evidence"):
        engine.draft(
            candidate_id, unrelated, "reviewer", "skill:promote", "untraceable"
        )


def test_retired_skill_is_auditable_inactive_and_excluded_from_export(tmp_path):
    store = _store(tmp_path)
    engine, candidate_id, _, _ = _approved(store, "retirable behavior")
    engine.promote(
        candidate_id, "retired", "protomentat", "skill:promote", "rollback exercised"
    )
    inspected = engine.inspect(candidate_id)
    assert inspected["promotion_state"] == "retired"
    assert inspected["transitions"][-1]["to_state"] == "retired"
    assert "ask one bounded clarification" not in next(
        section for section in _context(store).sections if section.name == "adaptations"
    ).content
    exported = engine.export_readiness("reviewer", "skill:export")
    assert exported["manifest"]["entries"] == []
    assert exported["report"]["excluded"][0]["state"] == "retired"


def test_readiness_manifest_is_hashed_provenanced_and_never_trains(tmp_path):
    store = _store(tmp_path)
    engine, candidate_id, artifact_id, _ = _approved(store)
    exported = engine.export_readiness("reviewer", "skill:export")
    entry = exported["manifest"]["entries"][0]
    assert entry["candidate_id"] == candidate_id
    assert entry["artifact_id"] == artifact_id
    assert len(entry["source_interactions"]) == 2
    assert len(entry["evidence_refs"]) == 2
    assert exported["report"] == {
        "ready": True, "skill_count": 1, "excluded": [],
        "training_performed": False,
    }
    canonical = json.dumps(exported["manifest"], sort_keys=True, separators=(",", ":"))
    assert exported["manifest_hash"] == hashlib.sha256(canonical.encode()).hexdigest()
    for table in (
        "skill_observations", "skill_artifacts", "skill_evaluations",
        "skill_transitions", "adapter_readiness_exports",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(f"DELETE FROM {table}")  # noqa: S608
        store.db.rollback()


def test_cli_inspects_and_exports_readiness(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "cli.db")
    store = Store(db)
    store.init()
    _, candidate_id, _, _ = _approved(store)
    store.db.close()
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "skill-inspect", str(candidate_id),
    ])
    main()
    assert json.loads(capsys.readouterr().out)["promotion_state"] == "approved"
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "skill-export", "--actor", "reviewer",
        "--authority", "skill:export",
    ])
    main()
    assert json.loads(capsys.readouterr().out)["report"]["ready"] is True
