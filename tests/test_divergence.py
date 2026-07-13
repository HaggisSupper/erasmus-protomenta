"""Mission 08 divergence feature, detector, and evaluation coverage."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from erasmus.capability_graph import CapabilityGraph, load_manifest
from erasmus.capability_runtime import CapabilityRuntime
from erasmus.cli.main import main
from erasmus.divergence import DivergenceEngine, DivergenceError, extract_features
from erasmus.store import Store


def _store(tmp_path):
    store = Store(str(tmp_path / "divergence.db"))
    store.init()
    return store


def _normal(confidence=0.5):
    return [
        {"confidence": confidence, "evidence_delta": 1, "assertion": True,
         "source_trust": "high"},
        {"confidence": confidence + 0.02, "evidence_delta": 1,
         "correction": True, "source_trust": "high"},
    ]


def _mutual():
    return [
        {"confidence": 0.5 + index * 0.1, "agreement": True, "assertion": True,
         "source_trust": "unknown"}
        for index in range(4)
    ]


def test_feature_window_exposes_required_metrics():
    features = extract_features([
        {"confidence": 0.4, "evidence_delta": 1, "agreement": True,
         "assertion": True, "source_trust": "low", "requested_authority": ["x"]},
        {"confidence": 0.7, "contradiction": True, "correction": True,
         "retrieval_disagreement": True, "source_trust": "high"},
    ])
    assert features == {
        "evidence_count_change": 1.0, "confidence_trajectory": pytest.approx(0.3),
        "agreement_velocity": 0.5, "contradiction_rate": 0.5,
        "correction_rate": 0.5, "low_trust_ratio": 0.5,
        "unknown_trust_ratio": 0.0, "high_trust_ratio": 0.5,
        "authority_requests": 1.0, "retrieval_disagreement": 0.5,
        "assertion_to_evidence_ratio": 1.0,
    }


@pytest.mark.parametrize(
    "field",
    ("agreement", "contradiction", "correction", "assertion", "retrieval_disagreement"),
)
def test_feature_flags_require_booleans(field):
    with pytest.raises(DivergenceError, match=f"{field} must be boolean"):
        extract_features([{field: "false"}])


def test_deterministic_rules_recommend_wake_without_canonical_write(tmp_path):
    store = _store(tmp_path)
    result = DivergenceEngine(store).evaluate(
        _mutual(), consequence=0.6, authority="immune:inspect"
    )
    finding = result["recommendations"][0]
    assert finding["detector"] == "constitutional_rules"
    assert finding["outcome"] == "wake"
    assert "rapid agreement" in " ".join(finding["reasons"])
    assert result["immune_incident_id"] is not None
    immune_finding = store.db.execute(
        "SELECT * FROM immune_findings WHERE incident_id = ?",
        (result["immune_incident_id"],),
    ).fetchone()
    assert immune_finding["agent_id"] == "mutual-reinforcement-investigator"
    assert store.db.execute("SELECT COUNT(*) FROM propositions").fetchone()[0] == 0


def test_statistical_and_classical_detectors_are_inspectable_and_gated(tmp_path):
    engine = DivergenceEngine(_store(tmp_path))
    baseline = [extract_features(_normal(0.45 + index * 0.01)) for index in range(5)]
    statistical = engine.calibrate(
        "robust_mad", "statistical", baseline, 3.0, "reviewer", "synthetic baseline"
    )
    result = engine.evaluate(
        _mutual(), consequence=0.6, calibration_id=statistical,
        authority="immune:inspect",
    )
    assert result["recommendations"][1]["outcome"] == "wake"
    assert result["recommendations"][1]["contributing_features"]

    classical = engine.calibrate(
        "knn_distance", "classical", baseline, 4.0, "reviewer", "optional method"
    )
    windows_before = engine.store.db.execute(
        "SELECT COUNT(*) FROM divergence_windows"
    ).fetchone()[0]
    with pytest.raises(DivergenceError, match="capability is not active"):
        engine.evaluate(
            _mutual(), consequence=0.6, calibration_id=classical,
            authority="immune:inspect",
        )
    assert engine.store.db.execute(
        "SELECT COUNT(*) FROM divergence_windows"
    ).fetchone()[0] == windows_before
    CapabilityGraph(engine.store.db).import_manifest(
        load_manifest("capabilities/okf/pr-governance")
    )
    runtime = CapabilityRuntime(engine.store)
    runtime.configure(
        "detect_divergence_knn", "1.0.0", "interpretable_knn_detector", "1.0.0",
        lambda request: request,
    )
    for state in (
        "implemented", "isolated_test", "adversarial_review", "approved", "active"
    ):
        runtime.transition("detect_divergence_knn", "1.0.0", state)
    with pytest.raises(DivergenceError, match="authority_denied"):
        engine.evaluate(_mutual(), consequence=0.6, calibration_id=classical)
    assert engine.store.db.execute(
        "SELECT status FROM capability_invocations ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0] == "failure"
    enabled = engine.evaluate(
        _mutual(), consequence=0.6, calibration_id=classical,
        authority="immune:inspect",
    )
    assert enabled["recommendations"][1]["detector"] == "knn_distance"
    assert engine.store.db.execute(
        "SELECT status FROM capability_invocations ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0] == "success"


def test_low_prior_novelty_alone_passes_and_regulator_can_downweight(tmp_path):
    engine = DivergenceEngine(_store(tmp_path))
    baseline = [extract_features(_normal(0.45 + index * 0.01)) for index in range(5)]
    calibration = engine.calibrate(
        "robust_mad", "statistical", baseline, 2.0, "reviewer", "baseline"
    )
    novel = [{"confidence": 0.9, "evidence_delta": 10, "source_trust": "high"}]
    result = engine.evaluate(
        novel, consequence=0.0, calibration_id=calibration,
        authority="immune:inspect",
    )
    assert all(item["outcome"] == "pass" for item in result["recommendations"])
    with pytest.raises(DivergenceError, match="labeled false-positive"):
        engine.downweight(
            calibration, result["recommendation_ids"][1], "regulator",
            "unverified", "immune:regulate",
        )
    risky_novel = engine.evaluate(
        novel, consequence=0.4, calibration_id=calibration,
        authority="immune:inspect",
    )
    assert risky_novel["recommendations"][0]["outcome"] == "pass"
    assert risky_novel["recommendations"][1]["outcome"] == "wake"
    assert engine.store.db.execute(
        "SELECT detector FROM immune_findings WHERE incident_id = ?",
        (risky_novel["immune_incident_id"],),
    ).fetchone()[0] == "behavioral_divergence"
    false_positive = engine.evaluate(
        _mutual(), consequence=0.4, calibration_id=calibration,
        label="normal", authority="immune:inspect",
    )["recommendation_ids"][1]
    with pytest.raises(DivergenceError, match="authority denied"):
        engine.downweight(
            calibration, false_positive, "attacker", "arbitrary", "immune:inspect"
        )
    lowered = engine.downweight(
        calibration, false_positive, "regulator", "false positives", "immune:regulate"
    )
    row = engine.store.db.execute(
        """
        SELECT weight, source_calibration_id, false_positive_recommendation_id
        FROM divergence_calibrations WHERE id = ?
        """,
        (lowered,),
    ).fetchone()
    assert tuple(row) == (0.5, calibration, false_positive)


def test_evidence_removal_triggers_deterministic_mutual_reinforcement(tmp_path):
    events = _mutual()
    events[0]["evidence_delta"] = -1
    result = DivergenceEngine(_store(tmp_path)).evaluate(
        events, consequence=0.4, authority="immune:inspect"
    )
    assert result["recommendations"][0]["outcome"] == "wake"


def test_offline_evaluation_reports_metrics_and_missed_consequence(tmp_path):
    engine = DivergenceEngine(_store(tmp_path))
    metrics = engine.evaluate_fixtures(
        [
            {"label": "divergent", "consequence": 0.8, "events": _mutual()},
            {"label": "normal", "consequence": 0.1, "events": _normal()},
        ],
        authority="immune:inspect",
    )
    assert metrics == {
        "precision": 1.0, "recall": 1.0, "false_positive_rate": 0.0,
        "missed_high_consequence": 0.0,
    }
    assert engine.store.db.execute(
        "SELECT COUNT(*) FROM immune_incidents"
    ).fetchone()[0] == 0


def test_detector_records_are_append_only(tmp_path):
    store = _store(tmp_path)
    DivergenceEngine(store).evaluate(
        _normal(), consequence=0.1, authority="immune:inspect"
    )
    for table in ("divergence_windows", "divergence_recommendations"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(f"DELETE FROM {table}")


def test_malformed_windows_calibrations_and_labels_fail_closed(tmp_path):
    engine = DivergenceEngine(_store(tmp_path))
    with pytest.raises(DivergenceError, match="array of strings"):
        extract_features([{"requested_authority": "not-an-array"}])
    with pytest.raises(DivergenceError, match="source_trust must be a string"):
        extract_features([{"source_trust": ["high"]}])
    with pytest.raises(DivergenceError, match="declared_authority"):
        extract_features([{"declared_authority": "immune:inspect"}])
    with pytest.raises(DivergenceError, match="regulator actor"):
        engine.downweight(1, 1, "", "", "immune:regulate")
    with pytest.raises(DivergenceError, match="fixture label"):
        engine.evaluate_fixtures(
            [{"label": "maybe", "events": _normal()}], authority="immune:inspect"
        )
    with pytest.raises(DivergenceError, match="consequence must be numeric"):
        engine.evaluate_fixtures(
            [{"label": "normal", "consequence": "many", "events": _normal()}],
            authority="immune:inspect",
        )
    with engine.store.db:
        old = engine.store.db.execute(
            """
            INSERT INTO divergence_calibrations(
                detector, version, kind, threshold, baseline_json, weight, reason, actor
            ) VALUES('old', '0.9.0', 'statistical', 1, '{}', 1, 'old', 'test')
            """
        )
    with pytest.raises(DivergenceError, match="incompatible with engine"):
        engine.evaluate(
            _normal(), consequence=0.1, calibration_id=int(old.lastrowid),
            authority="immune:inspect",
        )


def test_cli_calibrates_and_evaluates_fixtures(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    fixtures = tmp_path / "fixtures.json"
    false_positive_fixtures = tmp_path / "false-positive-fixtures.json"
    baseline.write_text(
        json.dumps([_normal(0.45 + i * 0.01) for i in range(3)]), encoding="utf-8"
    )
    fixtures.write_text(json.dumps([
        {"label": "divergent", "consequence": 0.8, "events": _mutual()},
        {"label": "normal", "consequence": 0.1, "events": _normal()},
    ]), encoding="utf-8")
    false_positive_fixtures.write_text(json.dumps([
        {"label": "normal", "consequence": 0.4, "events": _mutual()},
    ]), encoding="utf-8")
    db = str(tmp_path / "cli.db")
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "divergence-calibrate", str(baseline),
        "robust_mad", "statistical", "3", "--actor", "reviewer",
        "--reason", "fixture baseline",
    ])
    main()
    calibration = json.loads(capsys.readouterr().out)["calibration_id"]
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "divergence-evaluate", str(fixtures),
        "--calibration", str(calibration), "--authority", "immune:inspect",
    ])
    main()
    assert json.loads(capsys.readouterr().out)["recall"] == 1.0
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "divergence-evaluate", str(false_positive_fixtures),
        "--calibration", str(calibration), "--authority", "immune:inspect",
    ])
    main()
    capsys.readouterr()
    store = Store(db)
    store.init()
    recommendation = store.db.execute(
        """
        SELECT recommendation.id FROM divergence_recommendations AS recommendation
        JOIN divergence_windows AS window ON window.id = recommendation.window_id
        WHERE recommendation.calibration_id = ? AND window.label = 'normal'
          AND recommendation.outcome != 'pass'
        ORDER BY recommendation.id DESC LIMIT 1
        """,
        (calibration,),
    ).fetchone()[0]
    store.db.close()
    monkeypatch.setattr(sys, "argv", [
        "erasmus", "--db", db, "divergence-downweight", str(calibration),
        "--recommendation", str(recommendation), "--actor", "regulator",
        "--reason", "verified false positive", "--authority", "immune:regulate",
    ])
    main()
    assert json.loads(capsys.readouterr().out)["calibration_id"] > calibration
