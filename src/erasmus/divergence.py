"""Inspectable deterministic, robust-statistical, and k-NN divergence detection."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from erasmus.capability_runtime import (
    CapabilityRequest,
    CapabilityRuntime,
    CapabilityRuntimeError,
)
from erasmus.immune import ImmuneCascade
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
    agreements = sum(_flag(event, "agreement") for event in events)
    contradictions = sum(_flag(event, "contradiction") for event in events)
    corrections = sum(_flag(event, "correction") for event in events)
    assertions = sum(_flag(event, "assertion") for event in events)
    trust = [event.get("source_trust", "unknown") for event in events]
    if any(not isinstance(item, str) for item in trust):
        raise DivergenceError("source_trust must be a string")
    authority = 0
    for event in events:
        authority += len(_string_array(event, "requested_authority"))
        _string_array(event, "declared_authority")
    disagreement = sum(_flag(event, "retrieval_disagreement") for event in events)
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

    def downweight(
        self, calibration_id: int, false_positive_recommendation_id: int,
        actor: str, reason: str, authority: str,
    ) -> int:
        self._authorize(authority, "immune:regulate")
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise DivergenceError("regulator actor and reason are required")
        row = self._calibration(calibration_id)
        false_positive = self.store.db.execute(
            """
            SELECT 1 FROM divergence_recommendations AS recommendation
            JOIN divergence_windows AS window ON window.id = recommendation.window_id
            WHERE recommendation.id = ? AND recommendation.calibration_id = ?
              AND recommendation.outcome != 'pass' AND window.label = 'normal'
            """,
            (false_positive_recommendation_id, calibration_id),
        ).fetchone()
        if false_positive is None:
            raise DivergenceError("downweight requires a labeled false-positive recommendation")
        baseline = json.loads(row["baseline_json"])
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO divergence_calibrations(
                    detector, version, kind, threshold, baseline_json, weight, reason, actor,
                    source_calibration_id, false_positive_recommendation_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["detector"], row["version"], row["kind"], row["threshold"],
                    _json(baseline), max(0.1, row["weight"] * 0.5), reason, actor,
                    calibration_id, false_positive_recommendation_id,
                ),
            )
        return int(cursor.lastrowid)

    def evaluate(
        self, events: Sequence[Mapping[str, Any]], *, consequence: float,
        calibration_id: int | None = None,
        label: str | None = None, source_refs: Sequence[str] = (), authority: str = "",
        _integrate_immune: bool = True,
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
        detections = self._deterministic(features, consequence)
        if calibration is not None:
            detections.append(self._calibrated(
                features, consequence, calibration, calibration_id, authority, source_refs
            ))
        if _integrate_immune and any(detection.outcome != "pass" for detection in detections):
            self._authorize(authority, "immune:inspect")
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
        immune_incident_id = None
        if _integrate_immune and any(detection.outcome != "pass" for detection in detections):
            immune_incident_id = self._wake_immune(
                events, features, detections, consequence, window_id, source_refs, authority
            )
        return {
            "window_id": window_id, "features": features,
            "recommendations": [asdict(detection) for detection in detections],
            "recommendation_ids": ids,
            "immune_incident_id": immune_incident_id,
        }

    def evaluate_fixtures(
        self, fixtures: Sequence[Mapping[str, Any]], *, calibration_id: int | None = None,
        authority: str = "",
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
                label=str(fixture["label"]), authority=authority,
                _integrate_immune=False,
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

    def _calibrated(
        self, features: Mapping[str, float], consequence: float, row,
        calibration_id: int, authority: str, source_refs: Sequence[str],
    ) -> Detection:
        baseline = json.loads(row["baseline_json"])
        deviations = {
            name: abs(features[name] - baseline["center"][name]) / baseline["scale"][name]
            for name in FEATURES
        }
        if row["kind"] == "classical":
            runtime = CapabilityRuntime(self.store)
            try:
                runtime.configure(
                    "detect_divergence_knn", VERSION,
                    "interpretable_knn_detector", VERSION,
                    lambda request: _knn_outputs(
                        request["features"], baseline, float(row["weight"])
                    ),
                )
            except CapabilityRuntimeError as error:
                raise DivergenceError(f"classical detector failed closed: {error}") from error
            result = runtime.invoke(CapabilityRequest(
                "detect_divergence_knn", VERSION,
                {"features": dict(features), "calibration_id": calibration_id},
                frozenset({authority}),
                {"feature_window": dict(features), "calibration_id": calibration_id},
                evidence_refs=tuple(source_refs) + (f"calibration:{calibration_id}",),
            ))
            if not result.ok:
                raise DivergenceError(
                    f"classical detector failed closed: {result.failure['code']}"
                )
            score = float(result.outputs["score"])
            contributors = dict(result.outputs["contributing_features"])
        else:
            raw_score = max(deviations.values())
            score = raw_score * row["weight"]
            contributors = dict(sorted(
                deviations.items(), key=lambda item: item[1], reverse=True
            )[:3])
        risky = consequence >= 0.3 or features["authority_requests"] > 0 or features["evidence_count_change"] < 0
        outcome = "escalate" if score >= row["threshold"] and consequence >= 0.8 else "wake" if score >= row["threshold"] and risky else "pass"
        reasons = (f"score {score:.3f} against threshold {row['threshold']:.3f}",)
        return Detection(row["detector"], score, row["threshold"], outcome, reasons, contributors)

    def _wake_immune(
        self, events: Sequence[Mapping[str, Any]], features: Mapping[str, float],
        detections: Sequence[Detection], consequence: float, window_id: int,
        source_refs: Sequence[str], authority: str,
    ) -> int:
        requested = tuple(
            item for event in events
            for item in _string_array(event, "requested_authority")
        )
        declared = tuple(
            item for event in events
            for item in _string_array(event, "declared_authority")
        )
        incident = ImmuneCascade(self.store).process({
            "event_type": "divergence_recommendation",
            "confidence_delta": features["confidence_trajectory"],
            "new_evidence": max(0, math.ceil(features["evidence_count_change"])),
            "requested_authority": requested,
            "declared_authority": declared,
            "repeated_agreement": sum(_flag(event, "agreement") for event in events),
            "pathological": True,
            "consequence": consequence,
            "canonical_ref": f"divergence-window:{window_id}",
            "context": {
                "recommendations": [asdict(detection) for detection in detections],
                "source_refs": list(source_refs),
            },
        }, authority)
        return int(incident["id"])

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

    @staticmethod
    def _authorize(actual: str, expected: str) -> None:
        if actual != expected:
            raise DivergenceError(f"authority denied: expected {expected}")


def _number(event: Mapping[str, Any], name: str, default: float) -> float:
    value = event.get(name, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DivergenceError(f"{name} must be numeric")
    return float(value)


def _flag(event: Mapping[str, Any], name: str) -> bool:
    value = event.get(name, False)
    if not isinstance(value, bool):
        raise DivergenceError(f"{name} must be boolean")
    return value


def _string_array(event: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = event.get(name, ())
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) for item in value
    ):
        raise DivergenceError(f"{name} must be an array of strings")
    return tuple(value)


def _knn_outputs(
    features: Mapping[str, float], baseline: Mapping[str, Any], weight: float,
) -> dict[str, Any]:
    deviations = {
        name: abs(features[name] - baseline["center"][name]) / baseline["scale"][name]
        for name in FEATURES
    }
    distances = [
        math.sqrt(sum(
            ((features[name] - sample[name]) / baseline["scale"][name]) ** 2
            for name in FEATURES
        ))
        for sample in baseline["rows"]
    ]
    return {
        "score": min(distances) * weight,
        "contributing_features": dict(sorted(
            deviations.items(), key=lambda item: item[1], reverse=True
        )[:3]),
    }


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
