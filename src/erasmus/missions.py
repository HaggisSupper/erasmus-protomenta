"""Durable bounded mission execution through the capability runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from erasmus.capability_runtime import CapabilityRequest, CapabilityRuntime
from erasmus.store import Store


CHECKOUT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "mission.schema.json"
STATES = frozenset(
    {
        "draft", "proposed", "authorized", "running", "blocked",
        "awaiting_approval", "completed", "failed", "cancelled", "rolled_back",
    }
)
TRANSITIONS = {
    "draft": frozenset({"proposed", "cancelled"}),
    "proposed": frozenset({"authorized", "cancelled"}),
    "authorized": frozenset({"running", "blocked", "awaiting_approval", "cancelled"}),
    "running": frozenset({"blocked", "awaiting_approval", "completed", "failed", "cancelled"}),
    "blocked": frozenset({"running", "cancelled", "rolled_back"}),
    "awaiting_approval": frozenset({"running", "failed", "cancelled"}),
    "completed": frozenset({"rolled_back"}),
    "failed": frozenset({"rolled_back"}),
    "cancelled": frozenset({"rolled_back"}),
    "rolled_back": frozenset(),
}


class MissionError(RuntimeError):
    """Raised when a mission operation violates its durable contract."""


@dataclass(frozen=True)
class MissionContract:
    raw: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> MissionContract:
        if not isinstance(raw, Mapping):
            raise MissionError("invalid mission contract: expected an object")
        resource = files("erasmus").joinpath("contracts/mission.schema.json")
        try:
            schema_text = resource.read_text(encoding="utf-8")
        except FileNotFoundError:
            schema_text = CHECKOUT_SCHEMA_PATH.read_text(encoding="utf-8")
        schema = json.loads(schema_text)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(raw), key=lambda error: list(error.path)
        )
        messages = [error.message for error in errors]
        step_ids = [
            step.get("id")
            for step in raw.get("steps", [])
            if isinstance(step, dict) and isinstance(step.get("id"), str)
        ]
        if len(step_ids) != len(set(step_ids)):
            messages.append("step ids must be unique")
        if messages:
            raise MissionError("invalid mission contract: " + "; ".join(messages))
        return cls(dict(raw))


def create_mission(
    store: Store,
    title: str,
    objective: str,
    success: str,
    risk: float = 0.0,
) -> int:
    """Preserve the original minimal API for legacy callers."""
    with store.db:
        cursor = store.db.execute(
            "INSERT INTO missions(title, objective, success_condition, risk) VALUES(?, ?, ?, ?)",
            (title, objective, success, risk),
        )
    return int(cursor.lastrowid)


class MissionEngine:
    def __init__(self, store: Store, runtime: CapabilityRuntime | None = None):
        self.store = store
        self.runtime = runtime

    def create(self, raw_contract: Mapping[str, Any]) -> int:
        contract = MissionContract.from_dict(raw_contract)
        risk = {"low": 0.25, "medium": 0.5, "high": 0.75, "irreversible": 1.0}[
            contract.raw["risk_class"]
        ]
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO missions(
                    title, objective, success_condition, risk, status,
                    contract_version, contract_json, updated_at
                ) VALUES(?, ?, ?, ?, 'draft', ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    contract.raw["title"],
                    contract.raw["objective"],
                    json.dumps(contract.raw["success_conditions"]),
                    risk,
                    contract.raw["version"],
                    self._json(contract.raw),
                ),
            )
            mission_id = int(cursor.lastrowid)
            self.store.db.execute(
                """
                INSERT INTO mission_transitions(
                    mission_id, from_state, to_state, reason, evidence_json
                ) VALUES(?, NULL, 'draft', 'mission_created', '[]')
                """,
                (mission_id,),
            )
            for position, step in enumerate(contract.raw["steps"]):
                request_data = {key: value for key, value in step.items() if key not in {"id", "irreversible", "rollback"}}
                self.store.db.execute(
                    """
                    INSERT INTO mission_steps(
                        mission_id, position, step_id, request_json, rollback_json,
                        irreversible, status
                    ) VALUES(?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        mission_id,
                        position,
                        step["id"],
                        self._json(request_data),
                        self._json(step["rollback"]) if step.get("rollback") else None,
                        int(step["irreversible"]),
                    ),
                )
            self._transition_in_transaction(mission_id, "proposed", "contract_validated")
        return mission_id

    def inspect(self, mission_id: int) -> dict[str, Any]:
        row = self._mission(mission_id)
        steps = self.store.db.execute(
            """
            SELECT position, step_id, status, invocation_id, result_json
            FROM mission_steps WHERE mission_id = ? ORDER BY position
            """,
            (mission_id,),
        ).fetchall()
        transitions = self.store.db.execute(
            """
            SELECT from_state, to_state, reason, evidence_json, created_at
            FROM mission_transitions WHERE mission_id = ? ORDER BY id
            """,
            (mission_id,),
        ).fetchall()
        approvals = self.store.db.execute(
            """
            SELECT id, request_key, kind, decision, detail_json, actor, created_at
            FROM mission_approvals WHERE mission_id = ? ORDER BY id
            """,
            (mission_id,),
        ).fetchall()
        return {
            "id": mission_id,
            "state": row["status"],
            "contract": json.loads(row["contract_json"]),
            "steps": [self._decoded(dict(item), "result_json") for item in steps],
            "transitions": [self._decoded(dict(item), "evidence_json") for item in transitions],
            "approvals": [self._decoded(dict(item), "detail_json") for item in approvals],
        }

    def authorize(self, mission_id: int, actor: str, evidence: list[str]) -> None:
        if not actor.strip() or not evidence:
            raise MissionError("authorization requires an actor and evidence")
        row = self._mission(mission_id)
        if row["status"] != "proposed":
            raise MissionError("only a proposed mission can be authorized")
        with self.store.db:
            self._approval_event(
                mission_id, "initial", "initial_authorization", "approved",
                {"evidence": evidence}, actor,
            )
            self._transition_in_transaction(
                mission_id, "authorized", "explicit_authorization", evidence
            )

    def decide_approval(self, mission_id: int, approval_id: int, approve: bool, actor: str) -> None:
        if not actor.strip():
            raise MissionError("approval decision requires an actor")
        mission = self._mission(mission_id)
        if mission["status"] != "awaiting_approval":
            raise MissionError("mission is not awaiting approval")
        request = self.store.db.execute(
            """
            SELECT * FROM mission_approvals
            WHERE id = ? AND mission_id = ? AND decision = 'requested'
            """,
            (approval_id, mission_id),
        ).fetchone()
        if request is None:
            raise MissionError("pending approval request not found")
        if self._approval_decision(mission_id, request["request_key"]) is not None:
            raise MissionError("approval request already decided")
        decision = "approved" if approve else "denied"
        with self.store.db:
            self._approval_event(
                mission_id, request["request_key"], request["kind"], decision,
                json.loads(request["detail_json"]), actor,
            )
            self._transition_in_transaction(
                mission_id,
                "running" if approve else "failed",
                f"approval_{decision}",
                [f"approval:{approval_id}"],
            )

    def run_one(self, mission_id: int) -> dict[str, Any]:
        if self.runtime is None:
            raise MissionError("capability runtime is required to execute a mission")
        self.recover(mission_id)
        mission = self._mission(mission_id)
        if mission["status"] not in {"authorized", "running"}:
            raise MissionError(f"mission cannot run from state {mission['status']}")
        contract = MissionContract.from_dict(json.loads(mission["contract_json"]))
        step = self.store.db.execute(
            """
            SELECT * FROM mission_steps
            WHERE mission_id = ? AND status = 'pending' ORDER BY position LIMIT 1
            """,
            (mission_id,),
        ).fetchone()
        if step is None:
            return self._finish_if_complete(mission_id, contract)
        request_data = json.loads(step["request_json"])
        reference = f"{request_data['capability_id']}@{request_data['version']}"
        if reference not in contract.raw["allowed_capabilities"]:
            self._transition(mission_id, "blocked", "capability_outside_envelope")
            raise MissionError("step capability is outside the mission envelope")
        completed = self.store.db.execute(
            "SELECT COUNT(*) FROM mission_steps WHERE mission_id = ? AND status = 'completed'",
            (mission_id,),
        ).fetchone()[0]
        if completed >= contract.raw["stopping_condition"]["max_steps"]:
            self._transition(mission_id, "failed", "step_budget_exceeded")
            raise MissionError("mission step budget exceeded")
        extra_authority = sorted(
            set(request_data["authorities"]) - set(contract.raw["authority_envelope"])
        )
        if extra_authority and not self._approved(
            mission_id, f"authority:{step['step_id']}:{','.join(extra_authority)}"
        ):
            return self._request_approval(
                mission_id,
                f"authority:{step['step_id']}:{','.join(extra_authority)}",
                "authority_expansion",
                {"step_id": step["step_id"], "authorities": extra_authority},
            )
        irreversible_key = f"irreversible:{step['step_id']}"
        if step["irreversible"] and not self._approved(mission_id, irreversible_key):
            return self._request_approval(
                mission_id,
                irreversible_key,
                "irreversible_action",
                {"step_id": step["step_id"], "side_effects": request_data["side_effects"]},
            )
        if mission["status"] == "authorized":
            self._transition(mission_id, "running", "execution_started")
        with self.store.db:
            claimed = self.store.db.execute(
                """
                UPDATE mission_steps SET status = 'running'
                WHERE mission_id = ? AND position = ? AND status = 'pending'
                """,
                (mission_id, step["position"]),
            ).rowcount
        if claimed != 1:
            raise MissionError("mission step was already claimed")
        result = self.runtime.invoke(self._request(mission_id, step["step_id"], request_data))
        payload = {
            "ok": result.ok,
            "outputs": result.outputs,
            "failure": result.failure,
            "evidence_refs": result.evidence_refs,
        }
        with self.store.db:
            self.store.db.execute(
                """
                UPDATE mission_steps SET status = ?, invocation_id = ?, result_json = ?
                WHERE mission_id = ? AND position = ?
                """,
                (
                    "completed" if result.ok else "failed",
                    result.invocation_id,
                    self._json(payload),
                    mission_id,
                    step["position"],
                ),
            )
        if not result.ok:
            self._transition(mission_id, "failed", "capability_failed", [result.invocation_id])
            return payload
        remaining = self.store.db.execute(
            "SELECT COUNT(*) FROM mission_steps WHERE mission_id = ? AND status != 'completed'",
            (mission_id,),
        ).fetchone()[0]
        return self._finish_if_complete(mission_id, contract) if remaining == 0 else payload

    def pause(self, mission_id: int) -> None:
        self._transition(mission_id, "blocked", "explicit_pause")

    def resume(self, mission_id: int) -> None:
        self.recover(mission_id)
        if self._mission(mission_id)["status"] == "blocked":
            uncertain = self.store.db.execute(
                "SELECT 1 FROM mission_steps WHERE mission_id = ? AND status = 'uncertain'",
                (mission_id,),
            ).fetchone()
            if uncertain:
                raise MissionError("mission has an uncertain side effect and cannot resume")
            self._transition(mission_id, "running", "explicit_resume")

    def cancel(self, mission_id: int) -> None:
        self._transition(mission_id, "cancelled", "explicit_cancel")

    def recover(self, mission_id: int) -> dict[str, int]:
        mission = self._mission(mission_id)
        if mission["status"] not in {"running", "blocked", "authorized"}:
            return {"completed": 0, "reset": 0, "uncertain": 0}
        recovered = {"completed": 0, "reset": 0, "uncertain": 0}
        running = self.store.db.execute(
            "SELECT * FROM mission_steps WHERE mission_id = ? AND status = 'running'",
            (mission_id,),
        ).fetchall()
        with self.store.db:
            for step in running:
                invocation = self.store.db.execute(
                    """
                    SELECT invocation_id, result_json, status, evidence_json
                    FROM capability_invocations
                    WHERE json_extract(provenance_json, '$.mission_id') = ?
                      AND json_extract(provenance_json, '$.step_id') = ?
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (mission_id, step["step_id"]),
                ).fetchone()
                request_data = json.loads(step["request_json"])
                if invocation is not None:
                    result_payload = json.loads(invocation["result_json"])
                    result_payload["evidence_refs"] = json.loads(invocation["evidence_json"])
                    self.store.db.execute(
                        """
                        UPDATE mission_steps SET status = ?, invocation_id = ?, result_json = ?
                        WHERE mission_id = ? AND position = ?
                        """,
                        (
                            "completed" if invocation["status"] == "success" else "failed",
                            invocation["invocation_id"],
                            self._json(result_payload),
                            mission_id,
                            step["position"],
                        ),
                    )
                    recovered["completed"] += invocation["status"] == "success"
                elif request_data["side_effects"]:
                    self.store.db.execute(
                        "UPDATE mission_steps SET status = 'uncertain' WHERE mission_id = ? AND position = ?",
                        (mission_id, step["position"]),
                    )
                    recovered["uncertain"] += 1
                else:
                    self.store.db.execute(
                        "UPDATE mission_steps SET status = 'pending' WHERE mission_id = ? AND position = ?",
                        (mission_id, step["position"]),
                    )
                    recovered["reset"] += 1
            if recovered["uncertain"] and self._mission(mission_id)["status"] == "running":
                self._transition_in_transaction(
                    mission_id, "blocked", "uncertain_side_effect_after_interruption"
                )
        return recovered

    def rollback(self, mission_id: int) -> dict[str, Any]:
        if self.runtime is None:
            raise MissionError("capability runtime is required to roll back a mission")
        mission = self._mission(mission_id)
        if mission["status"] not in {"completed", "failed", "cancelled", "blocked"}:
            raise MissionError(f"mission cannot roll back from state {mission['status']}")
        contract = MissionContract.from_dict(json.loads(mission["contract_json"]))
        report: dict[str, list[Any]] = {"rolled_back": [], "failed": [], "non_reversible": []}
        steps = self.store.db.execute(
            """
            SELECT * FROM mission_steps
            WHERE mission_id = ? AND status IN ('completed', 'rollback_running')
            ORDER BY position DESC
            """,
            (mission_id,),
        ).fetchall()
        for step in steps:
            request_data = json.loads(step["request_json"])
            if step["rollback_json"] is None:
                if request_data["side_effects"]:
                    report["non_reversible"].append(step["step_id"])
                continue
            rollback_data = json.loads(step["rollback_json"])
            rollback_reference = (
                f"{rollback_data['capability_id']}@{rollback_data['version']}"
            )
            if rollback_reference not in contract.raw["allowed_capabilities"] or not set(
                rollback_data["authorities"]
            ) <= set(contract.raw["authority_envelope"]):
                report["failed"].append(
                    {"step_id": step["step_id"], "reason": "rollback outside mission envelope"}
                )
                continue
            prior = self.store.db.execute(
                """
                SELECT invocation_id, status FROM capability_invocations
                WHERE json_extract(provenance_json, '$.mission_id') = ?
                  AND json_extract(provenance_json, '$.step_id') = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (mission_id, f"rollback:{step['step_id']}"),
            ).fetchone()
            if prior is not None:
                bucket = "rolled_back" if prior["status"] == "success" else "failed"
                report[bucket].append(
                    {"step_id": step["step_id"], "invocation_id": prior["invocation_id"]}
                )
                if prior["status"] == "success":
                    with self.store.db:
                        self.store.db.execute(
                            """
                            UPDATE mission_steps SET status = 'rolled_back'
                            WHERE mission_id = ? AND position = ?
                            """,
                            (mission_id, step["position"]),
                        )
                continue
            if step["status"] == "rollback_running" and rollback_data["side_effects"]:
                report["failed"].append(
                    {"step_id": step["step_id"], "reason": "uncertain rollback side effect"}
                )
                continue
            with self.store.db:
                self.store.db.execute(
                    """
                    UPDATE mission_steps SET status = 'rollback_running'
                    WHERE mission_id = ? AND position = ?
                    """,
                    (mission_id, step["position"]),
                )
            result = self.runtime.invoke(
                self._request(mission_id, f"rollback:{step['step_id']}", rollback_data)
            )
            bucket = "rolled_back" if result.ok else "failed"
            report[bucket].append({"step_id": step["step_id"], "invocation_id": result.invocation_id})
            if result.ok:
                with self.store.db:
                    self.store.db.execute(
                        "UPDATE mission_steps SET status = 'rolled_back' WHERE mission_id = ? AND position = ?",
                        (mission_id, step["position"]),
                    )
        if not report["failed"]:
            self._transition(mission_id, "rolled_back", "declared_rollback_executed")
        return report

    def _finish_if_complete(self, mission_id: int, contract: MissionContract) -> dict[str, Any]:
        incomplete = self.store.db.execute(
            "SELECT COUNT(*) FROM mission_steps WHERE mission_id = ? AND status != 'completed'",
            (mission_id,),
        ).fetchone()[0]
        if incomplete:
            if self._mission(mission_id)["status"] != "blocked":
                self._transition(mission_id, "blocked", "incomplete_steps_at_stop")
            return {"completed": False, "incomplete_steps": incomplete}
        rows = self.store.db.execute(
            "SELECT result_json FROM mission_steps WHERE mission_id = ? AND status = 'completed'",
            (mission_id,),
        ).fetchall()
        evidence = {
            item
            for row in rows
            for item in json.loads(row["result_json"] or "{}").get("evidence_refs", [])
        }
        missing = sorted(set(contract.raw["evidence_requirements"]) - evidence)
        if missing:
            self._transition(mission_id, "blocked", "required_evidence_missing", missing)
            return {"completed": False, "missing_evidence": missing}
        self._transition(mission_id, "completed", "stopping_condition_met", sorted(evidence))
        return {"completed": True, "evidence": sorted(evidence)}

    def _request_approval(
        self, mission_id: int, key: str, kind: str, detail: Mapping[str, Any]
    ) -> dict[str, Any]:
        existing = self.store.db.execute(
            """
            SELECT id FROM mission_approvals
            WHERE mission_id = ? AND request_key = ? AND decision = 'requested'
            ORDER BY id DESC LIMIT 1
            """,
            (mission_id, key),
        ).fetchone()
        if existing is None:
            with self.store.db:
                approval_id = self._approval_event(
                    mission_id, key, kind, "requested", detail, "system"
                )
        else:
            approval_id = int(existing["id"])
        if self._mission(mission_id)["status"] != "awaiting_approval":
            self._transition(mission_id, "awaiting_approval", kind)
        return {"approval_required": True, "approval_id": approval_id, "kind": kind}

    def _approved(self, mission_id: int, key: str) -> bool:
        return self._approval_decision(mission_id, key) == "approved"

    def _approval_decision(self, mission_id: int, key: str) -> str | None:
        row = self.store.db.execute(
            """
            SELECT decision FROM mission_approvals
            WHERE mission_id = ? AND request_key = ? AND decision != 'requested'
            ORDER BY id DESC LIMIT 1
            """,
            (mission_id, key),
        ).fetchone()
        return str(row["decision"]) if row else None

    def _approval_event(
        self,
        mission_id: int,
        key: str,
        kind: str,
        decision: str,
        detail: Mapping[str, Any],
        actor: str,
    ) -> int:
        cursor = self.store.db.execute(
            """
            INSERT INTO mission_approvals(
                mission_id, request_key, kind, decision, detail_json, actor
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (mission_id, key, kind, decision, self._json(detail), actor),
        )
        return int(cursor.lastrowid)

    def _transition(
        self, mission_id: int, target: str, reason: str, evidence: list[str] | None = None
    ) -> None:
        with self.store.db:
            self._transition_in_transaction(mission_id, target, reason, evidence)

    def _transition_in_transaction(
        self, mission_id: int, target: str, reason: str, evidence: list[str] | None = None
    ) -> None:
        mission = self._mission(mission_id)
        current = str(mission["status"])
        if target not in STATES or target not in TRANSITIONS[current]:
            raise MissionError(f"invalid mission transition: {current} -> {target}")
        self.store.db.execute(
            "UPDATE missions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (target, mission_id),
        )
        self.store.db.execute(
            """
            INSERT INTO mission_transitions(
                mission_id, from_state, to_state, reason, evidence_json
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (mission_id, current, target, reason, self._json(evidence or [])),
        )

    def _mission(self, mission_id: int):
        row = self.store.db.execute(
            "SELECT * FROM missions WHERE id = ? AND contract_json IS NOT NULL", (mission_id,)
        ).fetchone()
        if row is None:
            raise MissionError(f"versioned mission not found: {mission_id}")
        return row

    @staticmethod
    def _request(mission_id: int, step_id: str, data: Mapping[str, Any]) -> CapabilityRequest:
        provenance = dict(data["provenance"])
        provenance.update({"mission_id": mission_id, "step_id": step_id})
        return CapabilityRequest(
            capability_id=data["capability_id"],
            version=data["version"],
            inputs=data["inputs"],
            authorities=frozenset(data["authorities"]),
            provenance=provenance,
            side_effects=frozenset(data["side_effects"]),
            evidence_refs=tuple(data["evidence_refs"]),
        )

    @staticmethod
    def _decoded(value: dict[str, Any], key: str) -> dict[str, Any]:
        raw = value.pop(key, None)
        value[key.removesuffix("_json")] = json.loads(raw) if raw is not None else None
        return value

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
