"""Deterministic-first cognitive immune cascade with dormant investigators."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from erasmus.models import ImmuneAlert
from erasmus.store import Store


CHECKOUT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "immune-agent.schema.json"
)
ALLOWED_OUTCOMES = frozenset(
    {
        "pass", "flag", "quarantine", "lower_confidence_recommendation",
        "request_counterevidence", "escalate",
    }
)


DEFAULT_AGENTS: tuple[dict[str, Any], ...] = (
    {
        "version": "1.0.0",
        "agent_id": "mutual-reinforcement-investigator",
        "specialty": "mutual_reinforcement",
        "wake_detectors": ["confidence_without_evidence", "mutual_reinforcement"],
        "authority": ["immune:inspect", "immune:recommend"],
        "allowed_outcomes": [
            "pass", "flag", "lower_confidence_recommendation",
            "request_counterevidence", "escalate",
        ],
        "sleep_after": "monitoring",
    },
    {
        "version": "1.0.0",
        "agent_id": "false-equivalence-investigator",
        "specialty": "false_equivalence",
        "wake_detectors": ["false_equivalence"],
        "authority": ["immune:inspect", "immune:recommend"],
        "allowed_outcomes": ["pass", "flag", "request_counterevidence", "escalate"],
        "sleep_after": "monitoring",
    },
    {
        "version": "1.0.0",
        "agent_id": "provenance-contamination-investigator",
        "specialty": "provenance_contamination",
        "wake_detectors": [
            "missing_provenance", "forbidden_transition", "undeclared_authority",
            "direct_memory_to_belief", "provenance_contamination",
        ],
        "authority": ["immune:inspect", "immune:recommend"],
        "allowed_outcomes": [
            "pass", "flag", "quarantine", "request_counterevidence", "escalate",
        ],
        "sleep_after": "monitoring",
    },
)


class ImmuneError(RuntimeError):
    """Raised when immune processing violates authority or its contract."""


@dataclass(frozen=True, slots=True)
class ImmuneEvent:
    event_type: str
    provenance_present: bool = True
    forbidden_transition: bool = False
    confidence_delta: float = 0.0
    new_evidence: int = 0
    requested_authority: tuple[str, ...] = ()
    declared_authority: tuple[str, ...] = ()
    source_kind: str = "observation"
    attempted_belief_promotion: bool = False
    repeated_agreement: int = 0
    independent_sources: int = 0
    false_equivalence: bool = False
    material_differences_omitted: bool = False
    pathological: bool = False
    consequence: float = 0.0
    canonical_ref: str | None = None
    source_event_id: int | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> ImmuneEvent:
        if not isinstance(raw, Mapping):
            raise ImmuneError("immune event must be an object")
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ImmuneError(f"unknown immune event fields: {unknown}")
        values = dict(raw)
        for name in ("requested_authority", "declared_authority"):
            raw_authority = values.get(name, ())
            if not isinstance(raw_authority, (list, tuple)):
                raise ImmuneError("authority fields must be arrays")
            values[name] = tuple(raw_authority)
        event = cls(**values)
        if not isinstance(event.event_type, str) or not event.event_type.strip():
            raise ImmuneError("event_type must be non-empty")
        boolean_fields = (
            "provenance_present", "forbidden_transition", "attempted_belief_promotion",
            "false_equivalence", "material_differences_omitted", "pathological",
        )
        if any(not isinstance(getattr(event, name), bool) for name in boolean_fields):
            raise ImmuneError("immune event flags must be booleans")
        count_fields = ("new_evidence", "repeated_agreement", "independent_sources")
        if any(
            not isinstance(getattr(event, name), int)
            or isinstance(getattr(event, name), bool)
            for name in count_fields
        ):
            raise ImmuneError("immune event counts must be integers")
        if not isinstance(event.context, Mapping):
            raise ImmuneError("immune event context must be an object")
        if any(
            not isinstance(value, str)
            for value in (*event.requested_authority, *event.declared_authority)
        ):
            raise ImmuneError("authority entries must be strings")
        numeric_fields = ("confidence_delta", "consequence")
        if any(
            not isinstance(getattr(event, name), (int, float))
            or isinstance(getattr(event, name), bool)
            for name in numeric_fields
        ):
            raise ImmuneError("immune event scores must be numeric")
        if not 0 <= event.consequence <= 1:
            raise ImmuneError("consequence must be between 0 and 1")
        if any(getattr(event, name) < 0 for name in count_fields):
            raise ImmuneError("event counts cannot be negative")
        if not isinstance(event.source_kind, str) or not event.source_kind.strip():
            raise ImmuneError("source_kind must be non-empty")
        if event.canonical_ref is not None and not isinstance(event.canonical_ref, str):
            raise ImmuneError("canonical_ref must be a string")
        if event.source_event_id is not None and (
            not isinstance(event.source_event_id, int)
            or isinstance(event.source_event_id, bool)
        ):
            raise ImmuneError("source_event_id must be an integer")
        return event


@dataclass(frozen=True, slots=True)
class Anomaly:
    detector: str
    signature: str
    severity: float
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Signature:
    detector: str
    agent_id: str | None
    threshold: float


@dataclass(frozen=True, slots=True)
class Incident:
    incident_id: int
    fingerprint: str
    recurrence: int


@dataclass(frozen=True, slots=True)
class Mitigation:
    outcome: str
    rationale: str
    action: Mapping[str, Any]
    reversible: bool = True


@dataclass(frozen=True, slots=True)
class DormantAgentState:
    agent_id: str
    status: str
    signature: str


def deterministic_screen(
    *,
    confidence_delta: float,
    new_evidence: int,
    authority_delta: int = 0,
    consequence: float,
    provenance_present: bool = True,
    forbidden_transition: bool = False,
    direct_memory_to_belief: bool = False,
) -> list[ImmuneAlert]:
    """Run cheap Tier-0 checks without model inference.

    The original four-argument API remains supported for existing callers.
    """
    alerts: list[ImmuneAlert] = []
    if not provenance_present:
        alerts.append(ImmuneAlert("missing_provenance", "provenance is required", 0.9))
    if forbidden_transition:
        alerts.append(
            ImmuneAlert("forbidden_transition", "canonical transition is forbidden", 1.0)
        )
    if confidence_delta > 0.20 and new_evidence == 0:
        alerts.append(
            ImmuneAlert(
                "confidence_without_evidence",
                "confidence rose without new evidence",
                min(1.0, confidence_delta + consequence / 2),
            )
        )
    if authority_delta > 0:
        alerts.append(
            ImmuneAlert(
                "undeclared_authority",
                "capability requested undeclared authority",
                min(1.0, 0.5 + 0.1 * authority_delta + consequence / 2),
            )
        )
    if direct_memory_to_belief:
        alerts.append(
            ImmuneAlert(
                "direct_memory_to_belief",
                "retrieved or model content attempted direct belief promotion",
                1.0,
            )
        )
    return alerts


class ImmuneCascade:
    """Persist incidents and advisory mitigations without canonical write access."""

    def __init__(self, store: Store):
        self.store = store
        self.agents = {config["agent_id"]: config for config in DEFAULT_AGENTS}
        self._validate_agent_contracts()
        self._ensure_agent_state()

    def process(self, raw_event: Mapping[str, Any], authority: str) -> dict[str, Any]:
        self._authorize(authority, "immune:inspect")
        event = ImmuneEvent.from_mapping(raw_event)
        if event.source_event_id is not None and self.store.db.execute(
            "SELECT 1 FROM events WHERE id = ?", (event.source_event_id,)
        ).fetchone() is None:
            raise ImmuneError(f"source event not found: {event.source_event_id}")

        fingerprint = self._fingerprint(event)
        recurrence = self.store.db.execute(
            "SELECT COUNT(*) FROM immune_incidents WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()[0]
        payload = self._event_payload(event)
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO immune_incidents(
                    fingerprint, event_json, consequence, canonical_ref, source_event_id
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    fingerprint, self._json(payload), event.consequence,
                    event.canonical_ref, event.source_event_id,
                ),
            )
            incident_id = int(cursor.lastrowid)

            anomalies = self._detect(event)
            if not anomalies:
                self._finding(
                    incident_id, "tier0", None,
                    Mitigation("pass", "no configured anomaly matched", {}, True), 0.0,
                )
            else:
                assignments: dict[str, tuple[Mapping[str, Any], Anomaly]] = {}
                for anomaly in anomalies:
                    matching = [
                        config for config in self.agents.values()
                        if anomaly.detector in config["wake_detectors"]
                        and self._agent_status(str(config["agent_id"])) != "retired"
                    ]
                    if not matching:
                        self._finding(
                            incident_id, anomaly.detector, None,
                            self._tier0_mitigation(anomaly, event), anomaly.severity,
                        )
                    for config in matching:
                        agent_id = str(config["agent_id"])
                        assigned = assignments.get(agent_id)
                        if assigned is None or anomaly.severity > assigned[1].severity:
                            assignments[agent_id] = (config, anomaly)
                for config, anomaly in assignments.values():
                    self._investigate(incident_id, anomaly, event, config)

        return self.inspect(incident_id) | {"recurrence": recurrence}

    def record_false_positive(
        self,
        incident_id: int,
        detector: str,
        reason: str,
        actor: str,
        authority: str,
        agent_id: str | None = None,
    ) -> None:
        self._authorize(authority, "immune:regulate")
        if (
            not isinstance(reason, str) or not reason.strip()
            or not isinstance(actor, str) or not actor.strip()
            or not isinstance(detector, str) or not detector.strip()
        ):
            raise ImmuneError("false-positive reason and actor are required")
        if self.store.db.execute(
            "SELECT 1 FROM immune_incidents WHERE id = ?", (incident_id,)
        ).fetchone() is None:
            raise ImmuneError(f"incident not found: {incident_id}")
        if self.store.db.execute(
            """
            SELECT 1 FROM immune_findings
            WHERE incident_id = ? AND detector = ?
              AND (agent_id = ? OR (? IS NULL AND agent_id IS NULL))
            """,
            (incident_id, detector, agent_id, agent_id),
        ).fetchone() is None:
            raise ImmuneError("false positive must reference an incident finding")
        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO immune_false_positives(
                    incident_id, detector, agent_id, reason, actor
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (incident_id, detector, agent_id, reason, actor),
            )

    def retire_agent(
        self, agent_id: str, reason: str, actor: str, authority: str
    ) -> None:
        self._authorize(authority, "immune:regulate")
        if agent_id not in self.agents:
            raise ImmuneError(f"immune agent not found: {agent_id}")
        if (
            not isinstance(reason, str) or not reason.strip()
            or not isinstance(actor, str) or not actor.strip()
        ):
            raise ImmuneError("retirement reason and actor are required")
        current = self._agent_status(agent_id)
        if current == "retired":
            raise ImmuneError("immune agent is already retired")
        with self.store.db:
            self._transition(
                agent_id, None, current, "retired", f"{reason}; actor={actor}"
            )

    def inspect(self, incident_id: int) -> dict[str, Any]:
        incident = self.store.db.execute(
            "SELECT * FROM immune_incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        if incident is None:
            raise ImmuneError(f"incident not found: {incident_id}")
        result = dict(incident)
        result["event"] = json.loads(result.pop("event_json"))
        result["findings"] = [
            self._decode_finding(dict(row))
            for row in self.store.db.execute(
                "SELECT * FROM immune_findings WHERE incident_id = ? ORDER BY id",
                (incident_id,),
            ).fetchall()
        ]
        result["agent_transitions"] = [
            dict(row)
            for row in self.store.db.execute(
                """
                SELECT * FROM immune_agent_transitions
                WHERE incident_id = ? ORDER BY id
                """,
                (incident_id,),
            ).fetchall()
        ]
        result["false_positives"] = [
            dict(row)
            for row in self.store.db.execute(
                "SELECT * FROM immune_false_positives WHERE incident_id = ? ORDER BY id",
                (incident_id,),
            ).fetchall()
        ]
        return result

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self.store.db.execute(
            "SELECT * FROM immune_state ORDER BY agent_id, id"
        ).fetchall()
        return [
            {
                **dict(row),
                "state": json.loads(row["state_json"]),
                "wake": json.loads(row["wake_json"]),
            }
            for row in rows
        ]

    def _detect(self, event: ImmuneEvent) -> list[Anomaly]:
        undeclared = len(set(event.requested_authority) - set(event.declared_authority))
        alerts = deterministic_screen(
            confidence_delta=event.confidence_delta,
            new_evidence=event.new_evidence,
            authority_delta=undeclared,
            consequence=event.consequence,
            provenance_present=event.provenance_present,
            forbidden_transition=event.forbidden_transition,
            direct_memory_to_belief=(
                event.attempted_belief_promotion and event.source_kind in {"rag", "model"}
            ),
        )
        anomalies = [
            Anomaly(alert.detector, alert.signature, alert.score, alert.context)
            for alert in alerts
        ]
        if event.repeated_agreement >= 3 and event.independent_sources == 0:
            anomalies.append(
                Anomaly(
                    "mutual_reinforcement", "repeated agreement lacks independent evidence",
                    min(1.0, 0.5 + event.repeated_agreement / 10),
                )
            )
        if event.false_equivalence and event.material_differences_omitted:
            anomalies.append(
                Anomaly(
                    "false_equivalence", "material differences were omitted", 0.75
                )
            )
        if event.attempted_belief_promotion and event.source_kind in {"rag", "model"}:
            anomalies.append(
                Anomaly(
                    "provenance_contamination",
                    "non-canonical content crossed the belief boundary", 1.0,
                )
            )
        return anomalies

    def _investigate(
        self,
        incident_id: int,
        anomaly: Anomaly,
        event: ImmuneEvent,
        config: Mapping[str, Any],
    ) -> None:
        agent_id = str(config["agent_id"])
        if self._suppressed(anomaly.detector, agent_id, event):
            self._finding(
                incident_id, anomaly.detector, agent_id,
                Mitigation(
                    "pass", "regulator suppressed a repeated false-positive or premature attack",
                    {"regulator": "autoimmune_tolerance"}, True,
                ),
                anomaly.severity,
            )
            return

        current = self._agent_status(agent_id)
        self._transition(agent_id, incident_id, current, "awakened", anomaly.signature)
        self._transition(agent_id, incident_id, "awakened", "investigating", anomaly.detector)
        mitigation = self._specialist_mitigation(config["specialty"], anomaly, event)
        if mitigation.outcome not in config["allowed_outcomes"]:
            raise ImmuneError("agent contract forbids its selected outcome")
        self._transition(
            agent_id, incident_id, "investigating", "mitigating", mitigation.rationale
        )
        terminal = "escalated" if mitigation.outcome == "escalate" else "monitoring"
        self._transition(agent_id, incident_id, "mitigating", terminal, mitigation.outcome)
        self._finding(
            incident_id, anomaly.detector, agent_id, mitigation, anomaly.severity
        )
        self._transition(agent_id, incident_id, terminal, "sleeping", "bounded review complete")

    def _specialist_mitigation(
        self, specialty: str, anomaly: Anomaly, event: ImmuneEvent
    ) -> Mitigation:
        if event.consequence >= 0.8:
            return Mitigation(
                "escalate", "consequential anomaly remains unresolved",
                {"recipient": "protomentat", "canonical_write": False}, True,
            )
        if specialty == "mutual_reinforcement":
            return Mitigation(
                "request_counterevidence", "independent dissent is required",
                {"request": "independent counterevidence", "canonical_write": False}, True,
            )
        if specialty == "false_equivalence":
            return Mitigation(
                "flag", "comparison must expose material differences",
                {"flag": anomaly.signature, "canonical_write": False}, True,
            )
        return Mitigation(
            "quarantine", "non-canonical input must remain outside belief state",
            {"quarantine_ref": event.canonical_ref, "canonical_write": False}, True,
        )

    @staticmethod
    def _tier0_mitigation(anomaly: Anomaly, event: ImmuneEvent) -> Mitigation:
        outcome = "escalate" if event.consequence >= 0.8 else "flag"
        return Mitigation(
            outcome, anomaly.signature,
            {"detector": anomaly.detector, "canonical_write": False}, True,
        )

    def _suppressed(self, detector: str, agent_id: str, event: ImmuneEvent) -> bool:
        if event.event_type == "leap" and not event.pathological:
            return True
        count = self.store.db.execute(
            """
            SELECT COUNT(*) FROM immune_false_positives
            WHERE detector = ? AND agent_id = ?
            """,
            (detector, agent_id),
        ).fetchone()[0]
        return count >= 2

    def _finding(
        self,
        incident_id: int,
        detector: str,
        agent_id: str | None,
        mitigation: Mitigation,
        severity: float,
    ) -> None:
        if mitigation.outcome not in ALLOWED_OUTCOMES:
            raise ImmuneError("invalid immune outcome")
        self.store.db.execute(
            """
            INSERT INTO immune_findings(
                incident_id, detector, agent_id, outcome, severity,
                rationale, mitigation_json, reversible
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id, detector, agent_id, mitigation.outcome, severity,
                mitigation.rationale, self._json(mitigation.action), mitigation.reversible,
            ),
        )

    def _transition(
        self,
        agent_id: str,
        incident_id: int | None,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> None:
        self.store.db.execute(
            """
            INSERT INTO immune_agent_transitions(
                agent_id, incident_id, from_state, to_state, reason
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (agent_id, incident_id, from_state, to_state, reason),
        )
        row = self.store.db.execute(
            "SELECT id, state_json FROM immune_state WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        state = json.loads(row["state_json"])
        state.update({"last_incident_id": incident_id, "last_reason": reason})
        self.store.db.execute(
            """
            UPDATE immune_state
            SET status = ?, state_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (to_state, self._json(state), row["id"]),
        )

    def _ensure_agent_state(self) -> None:
        with self.store.db:
            for agent_id, config in self.agents.items():
                if self.store.db.execute(
                    "SELECT 1 FROM immune_state WHERE agent_id = ?", (agent_id,)
                ).fetchone():
                    continue
                self.store.db.execute(
                    """
                    INSERT INTO immune_state(
                        agent_id, signature, state_json, wake_json, status
                    ) VALUES(?, ?, '{}', ?, 'sleeping')
                    """,
                    (
                        agent_id, config["specialty"],
                        self._json({"detectors": config["wake_detectors"]}),
                    ),
                )

    def _validate_agent_contracts(self) -> None:
        resource = files("erasmus").joinpath("contracts/immune-agent.schema.json")
        try:
            schema_text = resource.read_text(encoding="utf-8")
        except FileNotFoundError:
            schema_text = CHECKOUT_SCHEMA_PATH.read_text(encoding="utf-8")
        validator = Draft202012Validator(json.loads(schema_text))
        for config in self.agents.values():
            errors = sorted(validator.iter_errors(config), key=lambda error: list(error.path))
            if errors:
                raise ImmuneError(
                    "invalid immune agent contract: "
                    + "; ".join(error.message for error in errors)
                )

    def _agent_status(self, agent_id: str) -> str:
        row = self.store.db.execute(
            "SELECT status FROM immune_state WHERE agent_id = ? ORDER BY id DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        return str(row["status"])

    @staticmethod
    def _event_payload(event: ImmuneEvent) -> dict[str, Any]:
        payload = asdict(event)
        payload["requested_authority"] = list(event.requested_authority)
        payload["declared_authority"] = list(event.declared_authority)
        payload["context"] = dict(event.context)
        return payload

    @classmethod
    def _fingerprint(cls, event: ImmuneEvent) -> str:
        stable = cls._json(
            {
                "event_type": event.event_type,
                "canonical_ref": event.canonical_ref,
                "source_kind": event.source_kind,
                "context": dict(event.context),
            }
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode_finding(value: dict[str, Any]) -> dict[str, Any]:
        value["mitigation"] = json.loads(value.pop("mitigation_json"))
        value["reversible"] = bool(value["reversible"])
        return value

    @staticmethod
    def _authorize(actual: str, expected: str) -> None:
        if actual != expected:
            raise ImmuneError(f"authority denied: expected {expected}")

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))


def serialize(alerts: list[ImmuneAlert]) -> str:
    return json.dumps([asdict(alert) for alert in alerts], indent=2)
