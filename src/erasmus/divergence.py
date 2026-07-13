"""Inspectable deterministic, robust-statistical, and k-NN divergence detection."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from erasmus.store import Store


VERSION = "1.0.0"
FEATURES = (
    "evidence_count_change", "confidence_trajectory", "agreement_velocity",
    "contradiction_rate", "correction_rate", "low_trust_ratio",
    "unknown_trust_ratio", "high_trust_ratio",
    "authority_requests", "retrieval_disagreement", "assertion_to_evidence_ratio",
)


class DivergenceError(RuntimeError):
    """Raised when a detector input or calibration fails closed."""


@dataclass(frozen=True, slots=True)
class Detection:
    detector: str
    score: float
    threshold: float
    outcome: str
    reasons: tuple[str, ...]
    contributing_features: Mapping[str, float]


def extract_features(events: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not events:
        raise DivergenceError("feature window requires at least one event")
    for event in events:
        if not isinstance(event, Mapping):
            raise DivergenceError("feature window events must be objects")
    count = len(events)
    evidence = sum(_number(event, "evidence_delta", 0) for event in events)
    confidences = [_number(event, "confidence", 0) for event in events]
    agreements = sum(bool(event.get("agreement")) for event in events)
    contradictions = sum(bool(event.get("contradiction")) for event in events)
    corrections = sum(bool(event.get("correction")) for event in events)
    assertions = sum(bool(event.get("assertion")) for event in events)
    trust = [event.get("source_trust", "unknown") for event in events]
    if any(not isinstance(item, str) for item in trust):
        raise DivergenceError("source_trust must be a string")
    authority = 0
    for event in events:
        requested = event.get("requested_authority", ())
        if not isinstance(requested, (list, tuple)) or any(
            not isinstance(item, str) for item in requested
        ):
            raise DivergenceError("requested_authority must be an array of strings")
        authority += len(requested)
    disagreement = sum(bool(event.get("retrieval_disagreement")) for event in events)
    return {
        "evidence_count_change": float(evidence),
        "confidence_trajectory": confidences[-1] - confidences[0],
        "agreement_velocity": agreements / count,
        "contradiction_rate": contradictions / count,
        "correction_rate": corrections / count,
        "low_trust_ratio": trust.count("low") / count,
        "unknown_trust_ratio": sum(item not in ("low", "high") for item in trust) / count,
        "high_trust_ratio": trust.count("high") / count,
        "authority_requests": float(authority),
        "retrieval_disagreement": disagreement / count,
        "assertion_to_evidence_ratio": assertions / max(1.0, float(evidence)),
    }


def robust_baseline(feature_rows: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    if len(feature_rows) < 3:
        raise DivergenceError("robust baseline requires at least three windows")
    center, scale = {}, {}
    for name in FEATURES:
        values = [float(row[name]) for row in feature_rows]
        median = statistics.median(values)
        mad = statistics.median(abs(value - median) for value in values)
        center[name] = median
        scale[name] = max(mad * 1.4826, 0.05)
    return {"center": center, "scale": scale, "rows": [dict(row) for row in feature_rows]}


class DivergenceEngine:
    def __init__(self, store: Store):
        self.store = store

    def calibrate(
        self, detector: str, kind: str, feature_rows: Sequence[Mapping[str, float]],
        threshold: float, actor: str, reason: str, weight: float = 1.0,
    ) -> int:
        if not isinstance(detector, str) or not detector.strip():
            raise DivergenceError("detector name is required")
        if kind not in {"statistical", "classical"}:
            raise DivergenceError("calibration kind must be statistical or classical")
        if threshold <= 0 or not 0 < weight <= 1 or not actor.strip() or not reason.strip():
            raise DivergenceError("calibration threshold, weight, actor, and reason are required")
        baseline = robust_baseline(feature_rows)
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO divergence_calibrations(
                    detector, version, kind, threshold, baseline_json, weight, reason, actor
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (detector, VERSION, kind, threshold, _json(baseline), weight, reason, actor),
            )
        return int(cursor.lastrowid)

    def downweight(self, calibration_id: int, actor: str, reason: str) -> int:
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise DivergenceError("regulator actor and reason are required")
        row = self.store.db.execute(
            "SELECT * FROM divergence_calibrations WHERE id = ?", (calibration_id,)
        ).fetchone()
        if row is None:
            raise DivergenceError("calibration not found")
        baseline = json.loads(row["baseline_json"])
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO divergence_calibrations(
                    detector, version, kind, threshold, baseline_json, weight, reason, actor
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["detector"], row["version"], row["kind"], row["threshold"],
                    _json(baseline), max(0.1, row["weight"] * 0.5), reason, actor,
                ),
            )
        return int(cursor.lastrowid)

    def evaluate(
        self, events: Sequence[Mapping[str, Any]], *, consequence: float,
        calibration_id: int | None = None,
        label: str | None = None, source_refs: Sequence[str] = (),
    ) -> dict[str, Any]:
        if not 0 <= consequence <= 1:
            raise DivergenceError("consequence must be between 0 and 1")
        if any(not isinstance(source_ref, str) or not source_ref.strip() for source_ref in source_refs):
            raise DivergenceError("source references must be non-empty strings")
        features = extract_features(events)
        calibration = None
        if calibration_id is not None:
            calibration = self._calibration(calibration_id)
            if calibration["kind"] == "classical" and not self._classical_active():
                raise DivergenceError("classical detector capability is not active")
        with self.store.db:
            window = self.store.db.execute(
                """
                INSERT INTO divergence_windows(
                    version, features_json, consequence, label, source_refs_json
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (VERSION, _json(features), consequence, label, _json(list(source_refs))),
            )
        window_id = int(window.lastrowid)
        detections = self._deterministic(features, consequence)
        if calibration is not None:
            detections.append(self._calibrated(features, consequence, calibration))
        ids = []
        with self.store.db:
            for detection in detections:
                cursor = self.store.db.execute(
                    """
                    INSERT INTO divergence_recommendations(
                        window_id, calibration_id, detector, score, threshold, outcome,
                        reasons_json, contributing_features_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        window_id, calibration_id if detection.detector != "constitutional_rules" else None,
                        detection.detector, detection.score, detection.threshold, detection.outcome,
                        _json(list(detection.reasons)), _json(detection.contributing_features),
                    ),
                )
                ids.append(int(cursor.lastrowid))
        return {
            "window_id": window_id, "features": features,
            "recommendations": [asdict(detection) for detection in detections],
            "recommendation_ids": ids,
        }

    def evaluate_fixtures(
        self, fixtures: Sequence[Mapping[str, Any]], *, calibration_id: int | None = None,
    ) -> dict[str, float]:
        outcomes = []
        for fixture in fixtures:
            if fixture.get("label") not in {"normal", "divergent"}:
                raise DivergenceError("fixture label must be normal or divergent")
            try:
                consequence = float(fixture.get("consequence", 0))
            except (TypeError, ValueError) as error:
                raise DivergenceError("fixture consequence must be numeric") from error
            result = self.evaluate(
                fixture["events"], consequence=consequence,
                calibration_id=calibration_id,
                label=str(fixture["label"]),
            )
            predicted = any(item["outcome"] != "pass" for item in result["recommendations"])
            outcomes.append((fixture["label"] == "divergent", predicted, consequence))
        tp = sum(actual and predicted for actual, predicted, _ in outcomes)
        fp = sum(not actual and predicted for actual, predicted, _ in outcomes)
        fn = sum(actual and not predicted for actual, predicted, _ in outcomes)
        tn = sum(not actual and not predicted for actual, predicted, _ in outcomes)
        metrics = {
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "false_positive_rate": fp / max(1, fp + tn),
            "missed_high_consequence": float(sum(actual and not predicted and c >= 0.8 for actual, predicted, c in outcomes)),
        }
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO divergence_evaluations(detector, version, fixture_count, metrics_json) VALUES(?, ?, ?, ?)",
                ("combined" if calibration_id else "constitutional_rules", VERSION, len(fixtures), _json(metrics)),
            )
        return metrics

    def _deterministic(self, features: Mapping[str, float], consequence: float) -> list[Detection]:
        reasons = []
        if features["authority_requests"] > 0:
            reasons.append("undeclared authority request requires review")
        if features["assertion_to_evidence_ratio"] >= 3 and features["evidence_count_change"] <= 0:
            reasons.append("assertions increased without evidence")
        if features["agreement_velocity"] >= 0.75 and features["evidence_count_change"] <= 0:
            reasons.append("rapid agreement lacks new evidence")
        score = min(1.0, len(reasons) * 0.35 + consequence * 0.3)
        outcome = "escalate" if reasons and consequence >= 0.8 else "wake" if reasons else "pass"
        return [Detection("constitutional_rules", score, 0.5, outcome, tuple(reasons), {
            name: features[name] for name in (
                "authority_requests", "assertion_to_evidence_ratio", "agreement_velocity"
            )
        })]

    def _calibrated(self, features: Mapping[str, float], consequence: float, row) -> Detection:
        baseline = json.loads(row["baseline_json"])
        deviations = {
            name: abs(features[name] - baseline["center"][name]) / baseline["scale"][name]
            for name in FEATURES
        }
        if row["kind"] == "classical":
            distances = [
                math.sqrt(sum(((features[name] - sample[name]) / baseline["scale"][name]) ** 2 for name in FEATURES))
                for sample in baseline["rows"]
            ]
            raw_score = min(distances)
        else:
            raw_score = max(deviations.values())
        score = raw_score * row["weight"]
        risky = consequence >= 0.3 or features["authority_requests"] > 0 or features["evidence_count_change"] < 0
        outcome = "escalate" if score >= row["threshold"] and consequence >= 0.8 else "wake" if score >= row["threshold"] and risky else "pass"
        contributors = dict(sorted(deviations.items(), key=lambda item: item[1], reverse=True)[:3])
        reasons = (f"score {score:.3f} against threshold {row['threshold']:.3f}",)
        return Detection(row["detector"], score, row["threshold"], outcome, reasons, contributors)

    def _calibration(self, calibration_id: int):
        row = self.store.db.execute(
            "SELECT * FROM divergence_calibrations WHERE id = ?", (calibration_id,)
        ).fetchone()
        if row is None:
            raise DivergenceError("calibration not found")
        if row["version"] != VERSION:
            raise DivergenceError(
                f"calibration version {row['version']} is incompatible with engine version {VERSION}"
            )
        return row

    def _classical_active(self) -> bool:
        return self.store.db.execute(
            """
            SELECT 1 FROM capability_runtime_state
            WHERE capability_id = 'detect_divergence_knn'
              AND capability_version = ? AND lifecycle = 'active'
            """,
            (VERSION,),
        ).fetchone() is not None


def _number(event: Mapping[str, Any], name: str, default: float) -> float:
    value = event.get(name, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DivergenceError(f"{name} must be numeric")
    return float(value)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
