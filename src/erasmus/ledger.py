"""Append-only proposition and evidence ledger."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any

from erasmus.store import Store


STATUSES = frozenset(
    {
        "established", "supported", "plausible", "speculative", "analogy",
        "leap", "contradicted", "falsified", "unresolved",
    }
)
INITIAL_STATUSES = frozenset({"speculative", "analogy", "leap", "unresolved"})
RECORD_TYPES = frozenset(
    {"evidence", "contradiction", "falsification_test", "tangible_wrongness"}
)
SOURCE_KINDS = frozenset({"rag", "model", "document", "observation", "test", "human"})
SUPPORT_TRANSITIONS = {
    "speculative": "plausible",
    "analogy": "plausible",
    "leap": "plausible",
    "unresolved": "plausible",
    "plausible": "supported",
    "contradicted": "supported",
    "supported": "established",
}
TRUST_ORDER = {
    "untrusted": 0,
    "contextual": 1,
    "corroborated": 2,
    "primary": 3,
    "deterministic": 4,
}


class LedgerError(RuntimeError):
    """Raised when an epistemic operation fails closed."""


class EpistemicLedger:
    def __init__(self, store: Store):
        self.store = store

    def add_evidence(
        self,
        record_type: str,
        content: str,
        source_kind: str,
        provenance: Mapping[str, Any],
        trust_class: str,
        effective_date: str,
        scope: str,
        actor: str,
        authority: str,
        source_event_id: int | None = None,
        supersedes_id: int | None = None,
    ) -> int:
        self._authorize(authority, "evidence:write", "ledger:write")
        self._text(content, "content")
        self._text(scope, "scope")
        self._text(actor, "actor")
        if record_type not in RECORD_TYPES:
            raise LedgerError("invalid evidence record type")
        if source_kind not in SOURCE_KINDS:
            raise LedgerError("invalid evidence source kind")
        if not isinstance(provenance, Mapping) or not provenance:
            raise LedgerError("evidence provenance is required")
        try:
            date.fromisoformat(effective_date)
        except (TypeError, ValueError) as error:
            raise LedgerError("effective_date must use YYYY-MM-DD") from error
        if trust_class not in TRUST_ORDER:
            raise LedgerError("invalid trust class")
        if source_event_id is not None and self.store.db.execute(
            "SELECT 1 FROM events WHERE id = ?", (source_event_id,)
        ).fetchone() is None:
            raise LedgerError(f"source event not found: {source_event_id}")
        if supersedes_id is not None:
            prior = self._evidence(supersedes_id)
            if prior["scope"] != scope:
                raise LedgerError("superseding evidence must preserve scope")
            if self.store.db.execute(
                "SELECT 1 FROM epistemic_evidence WHERE supersedes_id = ?", (supersedes_id,)
            ).fetchone():
                raise LedgerError("evidence is already superseded")
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO epistemic_evidence(
                    record_type, content, source_kind, provenance_json, trust_class,
                    effective_date, scope, supersedes_id, source_event_id, actor
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_type, content, source_kind, self._json(provenance), trust_class,
                    effective_date, scope, supersedes_id, source_event_id, actor,
                ),
            )
        return int(cursor.lastrowid)

    def propose(
        self,
        statement: str,
        evidence_id: int,
        actor: str,
        authority: str,
        scope: str = "global",
        status: str = "speculative",
        reason: str = "proposed for evaluation",
    ) -> int:
        self._authorize(authority, "ledger:write")
        self._text(statement, "statement")
        self._text(actor, "actor")
        self._text(reason, "reason")
        if status not in INITIAL_STATUSES:
            raise LedgerError("initial status must be speculative, analogy, leap, or unresolved")
        evidence = self._evidence(evidence_id)
        self._same_scope(scope, evidence)
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO propositions(statement, status, confidence, scope, created_by)
                VALUES(?, ?, 0.5, ?, ?)
                """,
                (statement, status, scope, actor),
            )
            proposition_id = int(cursor.lastrowid)
            self._link(proposition_id, evidence_id, "origin", actor, reason)
            self._record_transition(
                proposition_id, "propose", None, status, evidence_id, actor, scope, reason
            )
            self.store.db.execute(
                """
                INSERT INTO confidence_history(
                    proposition_id, confidence, evidence_id, actor, reason
                ) VALUES(?, 0.5, ?, ?, 'initial uncertainty')
                """,
                (proposition_id, evidence_id, actor),
            )
        return proposition_id

    def transition(
        self,
        proposition_id: int,
        operation: str,
        evidence_id: int,
        actor: str,
        authority: str,
        reason: str,
        target_status: str | None = None,
        test_id: int | None = None,
    ) -> str:
        self._authorize(authority, "ledger:write")
        self._text(actor, "actor")
        self._text(reason, "reason")
        proposition = self._proposition(proposition_id)
        if proposition["superseded_by"] is not None:
            raise LedgerError("superseded propositions cannot transition")
        current = proposition["status"]
        evidence = self._evidence(evidence_id)
        self._same_scope(proposition["scope"], evidence)
        provenance = json.loads(evidence["provenance_json"])
        if provenance.get("basis") in {"agreement", "repetition"}:
            raise LedgerError("agreement or repetition is not promotion evidence")

        relation: str
        if operation == "support":
            expected = SUPPORT_TRANSITIONS.get(current)
            if expected is None or target_status != expected:
                raise LedgerError(f"support requires the next status {expected!r}")
            if evidence["record_type"] != "evidence":
                raise LedgerError("support requires an evidence record")
            new_status, relation = expected, "support"
        elif operation == "contradict":
            if current == "falsified":
                raise LedgerError("a falsified proposition must be reopened first")
            if evidence["record_type"] not in {"contradiction", "tangible_wrongness"}:
                raise LedgerError("contradiction requires counter-evidence")
            new_status, relation = "contradicted", "contradiction"
        elif operation == "falsify":
            if evidence["record_type"] != "tangible_wrongness" or test_id is None:
                raise LedgerError("falsification requires tangible wrongness and a test")
            test = self._evidence(test_id)
            self._same_scope(proposition["scope"], test)
            if test["record_type"] != "falsification_test":
                raise LedgerError("test_id must reference a falsification test")
            new_status, relation = "falsified", "falsification"
        elif operation == "reopen":
            if current != "falsified":
                raise LedgerError("only a falsified proposition can be reopened")
            if evidence["record_type"] != "evidence":
                raise LedgerError("reopening requires a new evidence record")
            falsification = self.store.db.execute(
                """
                SELECT evidence_id FROM proposition_transitions
                WHERE proposition_id = ? AND operation = 'falsify'
                ORDER BY id DESC LIMIT 1
                """,
                (proposition_id,),
            ).fetchone()
            if falsification is None or evidence_id <= falsification["evidence_id"]:
                raise LedgerError("reopening requires new evidence")
            new_status, relation = "unresolved", "reopening"
        else:
            raise LedgerError("invalid epistemic operation")

        with self.store.db:
            self._link(proposition_id, evidence_id, relation, actor, reason)
            if operation == "falsify":
                self._link(proposition_id, test_id, "test", actor, reason)
            self._record_transition(
                proposition_id, operation, current, new_status,
                evidence_id, actor, proposition["scope"], reason,
            )
        return new_status

    def record_confidence(
        self,
        proposition_id: int,
        confidence: float,
        evidence_id: int,
        actor: str,
        authority: str,
        reason: str,
    ) -> None:
        self._authorize(authority, "ledger:write")
        self._text(actor, "actor")
        self._text(reason, "reason")
        if not 0 <= confidence <= 1:
            raise LedgerError("confidence must be between 0 and 1")
        proposition = self._proposition(proposition_id)
        if proposition["superseded_by"] is not None:
            raise LedgerError("superseded propositions cannot record confidence")
        evidence = self._evidence(evidence_id)
        self._same_scope(proposition["scope"], evidence)
        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO confidence_history(
                    proposition_id, confidence, evidence_id, actor, reason
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (proposition_id, confidence, evidence_id, actor, reason),
            )

    def supersede(
        self,
        proposition_id: int,
        replacement_id: int,
        evidence_id: int,
        actor: str,
        authority: str,
        reason: str,
    ) -> None:
        self._authorize(authority, "ledger:write")
        self._text(actor, "actor")
        self._text(reason, "reason")
        original = self._proposition(proposition_id)
        replacement = self._proposition(replacement_id)
        if original["superseded_by"] is not None:
            raise LedgerError("proposition is already superseded")
        if replacement["superseded_by"] is not None:
            raise LedgerError("replacement proposition is already superseded")
        evidence = self._evidence(evidence_id)
        self._same_scope(original["scope"], replacement)
        self._same_scope(original["scope"], evidence)
        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO proposition_supersessions(
                    proposition_id, replacement_id, evidence_id, actor, reason
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (proposition_id, replacement_id, evidence_id, actor, reason),
            )
            self._link(proposition_id, evidence_id, "supersession", actor, reason)
            self._record_transition(
                proposition_id, "supersede", original["status"], original["status"],
                evidence_id, actor, original["scope"], reason,
            )

    def inspect(self, proposition_id: int) -> dict[str, Any]:
        proposition = self._proposition(proposition_id)
        transitions = self.store.db.execute(
            "SELECT * FROM proposition_transitions WHERE proposition_id = ? ORDER BY id",
            (proposition_id,),
        ).fetchall()
        confidence = self.store.db.execute(
            "SELECT * FROM confidence_history WHERE proposition_id = ? ORDER BY id",
            (proposition_id,),
        ).fetchall()
        evidence = self.store.db.execute(
            """
            SELECT pe.relation, pe.reason, pe.actor AS linked_by, e.*,
                   successor.id AS superseded_by
            FROM proposition_evidence pe
            JOIN epistemic_evidence e ON e.id = pe.evidence_id
            LEFT JOIN epistemic_evidence successor ON successor.supersedes_id = e.id
            WHERE pe.proposition_id = ? ORDER BY pe.id
            """,
            (proposition_id,),
        ).fetchall()
        return {
            **proposition,
            "transitions": [dict(row) for row in transitions],
            "confidence_history": [dict(row) for row in confidence],
            "evidence": [self._decode_evidence(dict(row)) for row in evidence],
        }

    def query(self, proposition_id: int) -> dict[str, Any]:
        proposition = self._proposition(proposition_id)
        support = self._strongest(proposition_id, ("origin", "support"))
        contradiction = self._strongest(
            proposition_id, ("contradiction", "falsification")
        )
        tests = self.store.db.execute(
            """
            SELECT e.* FROM proposition_evidence pe
            JOIN epistemic_evidence e ON e.id = pe.evidence_id
            WHERE pe.proposition_id = ? AND pe.relation = 'test'
              AND NOT EXISTS(
                  SELECT 1 FROM epistemic_evidence newer WHERE newer.supersedes_id = e.id
              )
            ORDER BY e.id
            """,
            (proposition_id,),
        ).fetchall()
        closed = self.store.db.execute(
            """
            SELECT p.id, p.statement,
                   COALESCE(t.new_status, p.status) AS status,
                   s.replacement_id
            FROM propositions p
            LEFT JOIN proposition_transitions t ON t.id = (
                SELECT id FROM proposition_transitions
                WHERE proposition_id = p.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN proposition_supersessions s ON s.proposition_id = p.id
            WHERE p.scope = ? AND p.id != ?
              AND (COALESCE(t.new_status, p.status) = 'falsified' OR s.id IS NOT NULL)
            ORDER BY p.id
            """,
            (proposition["scope"], proposition_id),
        ).fetchall()
        return {
            "proposition_id": proposition_id,
            "status": proposition["status"],
            "confidence": proposition["confidence"],
            "strongest_support": support,
            "strongest_contradiction": contradiction,
            "unresolved_tests": [] if proposition["status"] == "falsified" else [
                self._decode_evidence(dict(row)) for row in tests
            ],
            "relevant_closed_paths": [dict(row) for row in closed],
        }

    def _proposition(self, proposition_id: int) -> dict[str, Any]:
        row = self.store.db.execute(
            """
            SELECT p.*, latest.new_status, latest.id AS transition_id,
                   confidence.confidence AS latest_confidence,
                   supersession.replacement_id AS superseded_by
            FROM propositions p
            LEFT JOIN proposition_transitions latest ON latest.id = (
                SELECT id FROM proposition_transitions
                WHERE proposition_id = p.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN confidence_history confidence ON confidence.id = (
                SELECT id FROM confidence_history
                WHERE proposition_id = p.id ORDER BY id DESC LIMIT 1
            )
            LEFT JOIN proposition_supersessions supersession
                ON supersession.proposition_id = p.id
            WHERE p.id = ?
            """,
            (proposition_id,),
        ).fetchone()
        if row is None:
            raise LedgerError(f"proposition not found: {proposition_id}")
        result = dict(row)
        result["status"] = result.pop("new_status") or result["status"]
        latest_confidence = result.pop("latest_confidence")
        if latest_confidence is not None:
            result["confidence"] = latest_confidence
        return result

    def _evidence(self, evidence_id: int):
        row = self.store.db.execute(
            "SELECT * FROM epistemic_evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        if row is None:
            raise LedgerError(f"evidence not found: {evidence_id}")
        return row

    def _strongest(self, proposition_id: int, relations: tuple[str, ...]):
        placeholders = ",".join("?" for _ in relations)
        rows = self.store.db.execute(
            f"""
            SELECT e.* FROM proposition_evidence pe
            JOIN epistemic_evidence e ON e.id = pe.evidence_id
            WHERE pe.proposition_id = ? AND pe.relation IN ({placeholders})
              AND NOT EXISTS(
                  SELECT 1 FROM epistemic_evidence newer WHERE newer.supersedes_id = e.id
              )
            """,  # noqa: S608
            (proposition_id, *relations),
        ).fetchall()
        if not rows:
            return None
        strongest = max(rows, key=lambda row: (TRUST_ORDER[row["trust_class"]], row["id"]))
        return self._decode_evidence(dict(strongest))

    def _record_transition(
        self, proposition_id: int, operation: str, prior_status: str | None,
        new_status: str, evidence_id: int, actor: str, scope: str, reason: str,
    ) -> None:
        self.store.db.execute(
            """
            INSERT INTO proposition_transitions(
                proposition_id, operation, prior_status, new_status,
                evidence_id, actor, scope, reason
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposition_id, operation, prior_status, new_status,
                evidence_id, actor, scope, reason,
            ),
        )

    def _link(
        self, proposition_id: int, evidence_id: int, relation: str,
        actor: str, reason: str,
    ) -> None:
        self.store.db.execute(
            """
            INSERT INTO proposition_evidence(
                proposition_id, evidence_id, relation, actor, reason
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (proposition_id, evidence_id, relation, actor, reason),
        )

    @staticmethod
    def _authorize(actual: str, *allowed: str) -> None:
        if actual not in allowed:
            raise LedgerError(f"authority denied: expected one of {sorted(allowed)}")

    @staticmethod
    def _same_scope(scope: str, record: Mapping[str, Any]) -> None:
        if record["scope"] != scope:
            raise LedgerError("record scope does not match proposition scope")

    @staticmethod
    def _text(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise LedgerError(f"{name} must be non-empty")

    @staticmethod
    def _decode_evidence(value: dict[str, Any]) -> dict[str, Any]:
        value["provenance"] = json.loads(value.pop("provenance_json"))
        return value

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
