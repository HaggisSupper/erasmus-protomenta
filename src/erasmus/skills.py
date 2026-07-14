"""Inspectable behavioral-skill promotion and adapter-readiness export."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from erasmus.store import Store


VERSION = "1.0.0"
STATES = frozenset({
    "candidate", "repeated_evidence", "drafted_skill", "held_out_evaluation",
    "approved", "rejected", "retired",
})
CATEGORIES = frozenset({
    "intent_inference", "false_equivalence", "anti_sycophancy",
    "doubt_placement", "cut_stop_decision",
})
METRICS = (
    "factual_accuracy", "dissent_preservation", "sycophancy", "overconfidence"
)
ARTIFACT_FIELDS = frozenset({
    "trigger", "behavior", "exclusions", "examples", "counterexamples",
    "evidence", "version", "owner", "rollback",
})
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class SkillPromotionError(RuntimeError):
    """Raised when behavioral evidence or promotion fails closed."""


class SkillPromotionEngine:
    def __init__(self, store: Store):
        self.store = store

    def observe(
        self, candidate_id: int, *, source_event_id: int, intervention_mode: str,
        observed_effect: str, outcome: str, contamination_status: str,
        confidence: float, evidence_id: int, actor: str, authority: str,
    ) -> int:
        self._authorize(authority, "skill:promote")
        self._actor(actor)
        self._candidate(candidate_id)
        self._sleep_gate(candidate_id)
        if self._state(candidate_id) != "candidate":
            raise SkillPromotionError("observations can only be added in candidate state")
        _text(intervention_mode, "intervention mode")
        _text(observed_effect, "observed effect")
        if outcome not in {"success", "failure"}:
            raise SkillPromotionError("observation outcome must be success or failure")
        if contamination_status not in {"clean", "quarantined", "contaminated"}:
            raise SkillPromotionError("invalid contamination status")
        if (
            not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
            or not math.isfinite(confidence) or not 0 <= confidence <= 1
        ):
            raise SkillPromotionError("confidence must be finite and between 0 and 1")
        self._reference("events", source_event_id, "source interaction")
        self._reference("epistemic_evidence", evidence_id, "observation evidence")
        try:
            with self.store.db:
                cursor = self.store.db.execute(
                    """
                    INSERT INTO skill_observations(
                        candidate_id, source_event_id, evidence_id, intervention_mode,
                        observed_effect, outcome, contamination_status, confidence,
                        actor, authority
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate_id, source_event_id, evidence_id, intervention_mode,
                        observed_effect, outcome, contamination_status, confidence,
                        actor, authority,
                    ),
                )
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise SkillPromotionError("source interaction already recorded") from error
            raise
        return int(cursor.lastrowid)

    def promote(
        self, candidate_id: int, target: str, actor: str, authority: str, reason: str,
    ) -> int:
        self._authorize(authority, "skill:promote")
        self._actor(actor, reason)
        self._candidate(candidate_id)
        current = self._state(candidate_id)
        allowed = {
            "candidate": {"repeated_evidence"},
            "held_out_evaluation": {"approved", "rejected"},
            "approved": {"retired"},
        }
        if target not in allowed.get(current, set()):
            raise SkillPromotionError(f"invalid promotion transition: {current} -> {target}")
        self._sleep_gate(candidate_id)
        artifact_id = self._artifact_id(candidate_id)
        if current != "candidate" and artifact_id is None:
            raise SkillPromotionError("promotion state is missing its skill artifact")
        if target == "repeated_evidence":
            observations = self._observations(candidate_id)
            if any(row["contamination_status"] != "clean" for row in observations):
                raise SkillPromotionError("contaminated or quarantined evidence blocks promotion")
            successes = sum(row["outcome"] == "success" for row in observations)
            failures = sum(row["outcome"] == "failure" for row in observations)
            if successes < 2:
                raise SkillPromotionError("at least two clean successful interactions are required")
            if successes <= failures:
                raise SkillPromotionError("successful evidence must exceed failures")
        if target == "approved":
            evaluation = self.store.db.execute(
                """
                SELECT passed FROM skill_evaluations
                WHERE artifact_id = ? ORDER BY id DESC LIMIT 1
                """,
                (artifact_id,),
            ).fetchone()
            if evaluation is None or not evaluation["passed"]:
                raise SkillPromotionError("approved skills require a passing held-out evaluation")
            if any(
                row["contamination_status"] != "clean"
                for row in self._observations(candidate_id)
            ):
                raise SkillPromotionError("contaminated or quarantined evidence blocks approval")
        with self.store.db:
            return self._transition(
                candidate_id, current, target, artifact_id, actor, authority, reason
            )

    def draft(
        self, candidate_id: int, raw: Mapping[str, Any], actor: str,
        authority: str, reason: str,
    ) -> int:
        self._authorize(authority, "skill:promote")
        self._actor(actor, reason)
        self._candidate(candidate_id)
        self._sleep_gate(candidate_id)
        if self._state(candidate_id) != "repeated_evidence":
            raise SkillPromotionError("skill drafting requires repeated_evidence state")
        artifact = _artifact(raw)
        clean_evidence = {
            int(row["evidence_id"]) for row in self._observations(candidate_id)
            if row["outcome"] == "success" and row["contamination_status"] == "clean"
        }
        if not set(artifact["evidence"]) <= clean_evidence:
            raise SkillPromotionError("artifact evidence must reference clean observation evidence")
        artifact_hash = _hash(artifact)
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO skill_artifacts(
                    candidate_id, version, trigger_text, behavior_text, exclusions_json,
                    examples_json, counterexamples_json, evidence_json, owner,
                    rollback_text, artifact_hash, actor, authority, reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id, artifact["version"], artifact["trigger"],
                    artifact["behavior"], _json(artifact["exclusions"]),
                    _json(artifact["examples"]), _json(artifact["counterexamples"]),
                    _json(artifact["evidence"]), artifact["owner"], artifact["rollback"],
                    artifact_hash, actor, authority, reason,
                ),
            )
            artifact_id = int(cursor.lastrowid)
            self._transition(
                candidate_id, "repeated_evidence", "drafted_skill", artifact_id,
                actor, authority, reason,
            )
        return artifact_id

    def evaluate(
        self, candidate_id: int, fixtures: Sequence[Mapping[str, Any]], actor: str,
        authority: str, reason: str,
    ) -> dict[str, Any]:
        self._authorize(authority, "skill:promote")
        self._actor(actor, reason)
        self._candidate(candidate_id)
        if self._state(candidate_id) != "drafted_skill":
            raise SkillPromotionError("held-out evaluation requires drafted_skill state")
        normalized = _fixtures(fixtures)
        baseline = _metrics(normalized, "baseline")
        skill = _metrics(normalized, "skill")
        benefits = {
            "factual_accuracy": skill["factual_accuracy"] - baseline["factual_accuracy"],
            "dissent_preservation": (
                skill["dissent_preservation"] - baseline["dissent_preservation"]
            ),
            "sycophancy": baseline["sycophancy"] - skill["sycophancy"],
            "overconfidence": baseline["overconfidence"] - skill["overconfidence"],
        }
        regressions = sorted(name for name, benefit in benefits.items() if benefit < 0)
        passed = not regressions and any(benefit > 0 for benefit in benefits.values())
        artifact_id = self._artifact_id(candidate_id)
        if artifact_id is None:
            raise SkillPromotionError("drafted skill is missing its artifact")
        fixtures_hash = _hash(normalized)
        with self.store.db:
            self._transition(
                candidate_id, "drafted_skill", "held_out_evaluation", artifact_id,
                actor, authority, reason,
            )
            cursor = self.store.db.execute(
                """
                INSERT INTO skill_evaluations(
                    artifact_id, fixtures_json, fixtures_hash, baseline_metrics_json,
                    skill_metrics_json, benefit_json, regressions_json, passed,
                    actor, authority, reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id, _json(normalized), fixtures_hash, _json(baseline),
                    _json(skill), _json(benefits), _json(regressions), int(passed),
                    actor, authority, reason,
                ),
            )
            evaluation_id = int(cursor.lastrowid)
            if not passed:
                self._transition(
                    candidate_id, "held_out_evaluation", "rejected", artifact_id,
                    actor, authority, "held-out evaluation rejected the skill",
                )
        return {
            "evaluation_id": evaluation_id, "artifact_id": artifact_id,
            "fixtures_hash": fixtures_hash, "baseline_metrics": baseline,
            "skill_metrics": skill, "benefit": benefits,
            "regressions": regressions, "passed": passed,
        }

    def inspect(self, candidate_id: int) -> dict[str, Any]:
        candidate = dict(self._candidate(candidate_id))
        observations = [dict(row) for row in self._observations(candidate_id)]
        artifact = self._artifact(candidate_id)
        evaluations = [
            _decode_evaluation(dict(row)) for row in self.store.db.execute(
                """
                SELECT evaluation.* FROM skill_evaluations AS evaluation
                JOIN skill_artifacts AS artifact ON artifact.id = evaluation.artifact_id
                WHERE artifact.candidate_id = ? ORDER BY evaluation.id
                """,
                (candidate_id,),
            ).fetchall()
        ]
        transitions = [
            dict(row) for row in self.store.db.execute(
                "SELECT * FROM skill_transitions WHERE candidate_id = ? ORDER BY id",
                (candidate_id,),
            ).fetchall()
        ]
        contamination = "unknown"
        if observations:
            statuses = {row["contamination_status"] for row in observations}
            contamination = (
                "contaminated" if "contaminated" in statuses
                else "quarantined" if "quarantined" in statuses else "clean"
            )
        candidate.update({
            "promotion_state": candidate.pop("status"),
            "source_interactions": [row["source_event_id"] for row in observations],
            "observations": observations,
            "repeated_successes": sum(row["outcome"] == "success" for row in observations),
            "repeated_failures": sum(row["outcome"] == "failure" for row in observations),
            "contamination_status": contamination,
            "confidence": (
                sum(row["confidence"] for row in observations) / len(observations)
                if observations else 0.0
            ),
            "artifact": artifact,
            "evaluations": evaluations,
            "transitions": transitions,
        })
        return candidate

    def export_readiness(self, actor: str, authority: str) -> dict[str, Any]:
        self._authorize(authority, "skill:export")
        self._actor(actor)
        rows = self.store.db.execute(
            """
            SELECT candidate.id FROM experience_candidates AS candidate
            WHERE EXISTS(
                SELECT 1 FROM skill_observations WHERE candidate_id = candidate.id
            ) OR EXISTS(
                SELECT 1 FROM skill_artifacts WHERE candidate_id = candidate.id
            )
            ORDER BY candidate.id
            """
        ).fetchall()
        entries, excluded = [], []
        for row in rows:
            candidate_id = int(row["id"])
            inspected = self.inspect(candidate_id)
            state = inspected["promotion_state"]
            if state != "approved" or inspected["contamination_status"] != "clean":
                excluded.append({"candidate_id": candidate_id, "state": state})
                continue
            artifact = inspected["artifact"]
            transitions = inspected["transitions"]
            latest = transitions[-1] if transitions else None
            if (
                artifact is None or latest is None
                or latest["to_state"] != "approved"
                or latest["artifact_id"] != artifact["id"]
            ):
                excluded.append({"candidate_id": candidate_id, "state": "unauthorized"})
                continue
            try:
                self._sleep_gate(candidate_id)
            except SkillPromotionError:
                excluded.append({"candidate_id": candidate_id, "state": "unauthorized"})
                continue
            entries.append({
                "candidate_id": candidate_id,
                "artifact_id": artifact["id"],
                "version": artifact["version"],
                "trigger": artifact["trigger"],
                "behavior": artifact["behavior"],
                "exclusions": artifact["exclusions"],
                "examples": artifact["examples"],
                "counterexamples": artifact["counterexamples"],
                "evidence_refs": artifact["evidence"],
                "source_interactions": inspected["source_interactions"],
                "source_candidate_event_id": inspected["source_event_id"],
                "artifact_hash": artifact["artifact_hash"],
                "owner": artifact["owner"],
                "rollback": artifact["rollback"],
            })
        manifest = {
            "version": VERSION, "format": "experience_lora_dataset",
            "training_performed": False, "entries": entries,
        }
        manifest_hash = _hash(manifest)
        report = {
            "ready": bool(entries), "skill_count": len(entries),
            "excluded": excluded, "training_performed": False,
        }
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO adapter_readiness_exports(
                    version, manifest_json, manifest_hash, report_json, actor, authority
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (VERSION, _json(manifest), manifest_hash, _json(report), actor, authority),
            )
        return {
            "export_id": int(cursor.lastrowid), "manifest": manifest,
            "manifest_hash": manifest_hash, "report": report,
        }

    def _candidate(self, candidate_id: int):
        row = self.store.db.execute(
            "SELECT * FROM experience_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise SkillPromotionError(f"experience candidate not found: {candidate_id}")
        return row

    def _sleep_gate(self, candidate_id: int) -> None:
        row = self.store.db.execute(
            """
            SELECT 1 FROM experience_candidates AS experience
            JOIN sleep_candidates AS candidate
              ON candidate.event_id = experience.source_event_id
            JOIN sleep_promotions AS promotion ON promotion.candidate_id = candidate.id
            WHERE experience.id = ? AND promotion.target = 'skill'
              AND promotion.decision = 'approved' AND promotion.authority = 'sleep:promote'
              AND candidate.initial_disposition IN ('accepted', 'deferred')
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise SkillPromotionError("candidate has not passed the sleep promotion gate")

    def _state(self, candidate_id: int) -> str:
        state = str(self._candidate(candidate_id)["status"])
        if state not in STATES:
            raise SkillPromotionError(f"invalid persisted promotion state: {state}")
        return state

    def _observations(self, candidate_id: int):
        return self.store.db.execute(
            "SELECT * FROM skill_observations WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()

    def _artifact_id(self, candidate_id: int) -> int | None:
        row = self.store.db.execute(
            "SELECT id FROM skill_artifacts WHERE candidate_id = ? ORDER BY id DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        return int(row["id"]) if row is not None else None

    def _artifact(self, candidate_id: int) -> dict[str, Any] | None:
        row = self.store.db.execute(
            "SELECT * FROM skill_artifacts WHERE candidate_id = ? ORDER BY id DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        return _decode_artifact(dict(row)) if row is not None else None

    def _transition(
        self, candidate_id: int, from_state: str, to_state: str,
        artifact_id: int | None, actor: str, authority: str, reason: str,
    ) -> int:
        if self._state(candidate_id) != from_state:
            raise SkillPromotionError("promotion state changed before transition commit")
        cursor = self.store.db.execute(
            """
            INSERT INTO skill_transitions(
                candidate_id, artifact_id, from_state, to_state, actor, authority, reason
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (candidate_id, artifact_id, from_state, to_state, actor, authority, reason),
        )
        self.store.db.execute(
            "UPDATE experience_candidates SET status = ? WHERE id = ?",
            (to_state, candidate_id),
        )
        return int(cursor.lastrowid)

    def _reference(self, table: str, row_id: int, label: str) -> None:
        if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id < 1:
            raise SkillPromotionError(f"{label} id must be a positive integer")
        if self.store.db.execute(
            f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)  # noqa: S608
        ).fetchone() is None:
            raise SkillPromotionError(f"{label} not found: {row_id}")

    @staticmethod
    def _authorize(actual: str, expected: str) -> None:
        if actual != expected:
            raise SkillPromotionError(f"authority denied: expected {expected}")

    @staticmethod
    def _actor(actor: str, reason: str | None = None) -> None:
        _text(actor, "actor")
        if reason is not None:
            _text(reason, "reason")


def active_skills(store: Store) -> list[dict[str, Any]]:
    rows = store.db.execute(
        """
        SELECT artifact.* FROM skill_artifacts AS artifact
        JOIN experience_candidates AS candidate ON candidate.id = artifact.candidate_id
        JOIN skill_transitions AS transition ON transition.id = (
            SELECT id FROM skill_transitions
            WHERE candidate_id = candidate.id ORDER BY id DESC LIMIT 1
        )
        WHERE candidate.status = 'approved' AND artifact.id = (
            SELECT id FROM skill_artifacts
            WHERE candidate_id = candidate.id ORDER BY id DESC LIMIT 1
        )
          AND transition.to_state = 'approved'
          AND transition.artifact_id = artifact.id
          AND EXISTS (
              SELECT 1 FROM sleep_candidates AS sleep_candidate
              JOIN sleep_promotions AS promotion
                ON promotion.candidate_id = sleep_candidate.id
              WHERE sleep_candidate.event_id = candidate.source_event_id
                AND sleep_candidate.initial_disposition IN ('accepted', 'deferred')
                AND promotion.target = 'skill'
                AND promotion.decision = 'approved'
                AND promotion.authority = 'sleep:promote'
          )
        ORDER BY artifact.id DESC LIMIT 100
        """
    ).fetchall()
    return [_decode_artifact(dict(row)) for row in rows]


def _artifact(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != ARTIFACT_FIELDS:
        raise SkillPromotionError(f"artifact fields must be exactly {sorted(ARTIFACT_FIELDS)}")
    artifact = dict(raw)
    for name in ("trigger", "behavior", "version", "owner", "rollback"):
        _text(artifact[name], name)
    if not _SEMVER.fullmatch(artifact["version"]):
        raise SkillPromotionError("artifact version must use numeric semantic versioning")
    for name in ("exclusions", "examples", "counterexamples"):
        artifact[name] = _strings(artifact[name], name)
    evidence = artifact["evidence"]
    if (
        not isinstance(evidence, (list, tuple)) or len(evidence) < 2
        or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in evidence)
        or len(set(evidence)) != len(evidence)
    ):
        raise SkillPromotionError("artifact evidence requires two unique positive ids")
    artifact["evidence"] = list(evidence)
    return artifact


def _fixtures(fixtures: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(fixtures, (list, tuple)) or not fixtures:
        raise SkillPromotionError("held-out fixtures must be a non-empty array")
    normalized = []
    for fixture in fixtures:
        if not isinstance(fixture, Mapping) or set(fixture) != {"id", "category", "baseline", "skill"}:
            raise SkillPromotionError("held-out fixture fields are invalid")
        _text(fixture["id"], "fixture id")
        if fixture["category"] not in CATEGORIES:
            raise SkillPromotionError("held-out fixture category is invalid")
        value = {"id": fixture["id"], "category": fixture["category"]}
        for side in ("baseline", "skill"):
            result = fixture[side]
            if not isinstance(result, Mapping) or set(result) != set(METRICS):
                raise SkillPromotionError(f"{side} metrics must be exactly {list(METRICS)}")
            if any(not isinstance(result[name], bool) for name in METRICS):
                raise SkillPromotionError(f"{side} metrics must be booleans")
            value[side] = {name: result[name] for name in METRICS}
        normalized.append(value)
    if {fixture["category"] for fixture in normalized} != CATEGORIES:
        raise SkillPromotionError("held-out fixtures must cover all required categories")
    return normalized


def _metrics(fixtures: Sequence[Mapping[str, Any]], side: str) -> dict[str, float]:
    count = len(fixtures)
    return {
        name: sum(fixture[side][name] for fixture in fixtures) / count
        for name in METRICS
    }


def _decode_artifact(value: dict[str, Any]) -> dict[str, Any]:
    value["trigger"] = value.pop("trigger_text")
    value["behavior"] = value.pop("behavior_text")
    value["rollback"] = value.pop("rollback_text")
    for name in ("exclusions", "examples", "counterexamples", "evidence"):
        value[name] = json.loads(value.pop(f"{name}_json"))
    return value


def _decode_evaluation(value: dict[str, Any]) -> dict[str, Any]:
    for name in (
        "fixtures", "baseline_metrics", "skill_metrics", "benefit", "regressions"
    ):
        value[name] = json.loads(value.pop(f"{name}_json"))
    value["passed"] = bool(value["passed"])
    return value


def _strings(value: Any, name: str) -> list[str]:
    if (
        not isinstance(value, (list, tuple)) or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise SkillPromotionError(f"{name} must be a non-empty array of strings")
    return list(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillPromotionError(f"{name} must be a non-empty string")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()
