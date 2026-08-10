from __future__ import annotations

import json
from typing import Any

from .knowledge_runtime import _digest, _json, _urn


class EvolutionFacadeMixin:
    """P3.12-P3.14 freshness, bounded intake, and routing integration."""

    def assess_freshness(
        self,
        source_id: str,
        freshness_state: str,
        materiality: str,
        actor: str,
        authority: str,
        stale_after: str | None = None,
    ) -> dict[str, Any]:
        self._gate("knowledge:revalidate", actor)
        if authority != "knowledge:revalidate":
            raise PermissionError("knowledge:revalidate required")
        if freshness_state not in {
            "current", "approaching_stale", "stale", "unknown", "source_unavailable"
        }:
            raise ValueError("invalid freshness state")
        if materiality not in {"routine", "consequential", "protected"}:
            raise ValueError("invalid materiality")
        if self.db.execute(
            "SELECT 1 FROM knowledge_sources WHERE source_id=?", (source_id,)
        ).fetchone() is None:
            raise ValueError("source not found")
        assessment_id = _urn("freshness", _digest({
            "source": source_id,
            "state": freshness_state,
            "materiality": materiality,
            "stale_after": stale_after,
            "ordinal": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_freshness_assessments WHERE source_id=?",
                (source_id,),
            ).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_freshness_assessments(assessment_id,source_id,freshness_state,materiality,stale_after,actor,authority) VALUES(?,?,?,?,?,?,?)",
                (
                    assessment_id, source_id, freshness_state, materiality,
                    stale_after, actor, authority,
                ),
            )
        return dict(self.db.execute(
            "SELECT * FROM knowledge_freshness_assessments WHERE assessment_id=?",
            (assessment_id,),
        ).fetchone())

    def _claims_for_source(self, source_id: str) -> set[int]:
        spans = {
            row[0] for row in self.db.execute(
                "SELECT span_id FROM knowledge_source_spans WHERE source_id=?",
                (source_id,),
            ).fetchall()
        }
        candidate_claim_ids: set[str] = set()
        for row in self.db.execute(
            "SELECT candidate_claim_id,source_span_ids_json FROM knowledge_candidate_claims"
        ).fetchall():
            if spans.intersection(json.loads(row["source_span_ids_json"])):
                candidate_claim_ids.add(row["candidate_claim_id"])
        if not candidate_claim_ids:
            return set()
        placeholders = ",".join("?" for _ in candidate_claim_ids)
        return {
            int(row[0]) for row in self.db.execute(
                f"SELECT proposition_id FROM knowledge_claim_bindings WHERE candidate_claim_id IN ({placeholders})",
                tuple(sorted(candidate_claim_ids)),
            ).fetchall()
        }

    def invalidate_source(
        self, source_id: str, reason: str, actor: str, authority: str
    ) -> dict[str, Any]:
        self._gate("knowledge:serve-control", actor)
        if authority != "knowledge:serve-control":
            raise PermissionError("knowledge:serve-control required")
        if not reason.strip():
            raise ValueError("invalidation reason required")
        assessment = self.db.execute(
            "SELECT * FROM knowledge_freshness_assessments WHERE source_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        materiality = assessment["materiality"] if assessment else "consequential"
        proposition_ids = self._claims_for_source(source_id)
        revision_ids: set[str] = set()
        for row in self.db.execute(
            "SELECT revision_id,claim_ids_json FROM knowledge_concept_revisions"
        ).fetchall():
            if proposition_ids.intersection(
                int(value) for value in json.loads(row["claim_ids_json"])
            ):
                revision_ids.add(row["revision_id"])
        snapshot_ids: set[str] = set()
        for row in self.db.execute(
            "SELECT snapshot_id,revision_ids_json FROM knowledge_snapshots WHERE snapshot_state='published'"
        ).fetchall():
            if revision_ids.intersection(json.loads(row["revision_ids_json"])):
                snapshot_ids.add(row["snapshot_id"])
        invalidation_id = _urn("invalidation", _digest({
            "source": source_id,
            "reason": reason,
            "ordinal": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_invalidation_events WHERE target_type='source' AND target_id=?",
                (source_id,),
            ).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_invalidation_events(invalidation_id,target_type,target_id,reason,actor) VALUES(?,?,?,?,?)",
                (invalidation_id, "source", source_id, reason, actor),
            )
            for proposition_id in sorted(proposition_ids):
                action = (
                    "exclude"
                    if materiality in {"consequential", "protected"}
                    else "qualify"
                )
                for channel in self.db.execute(
                    "SELECT channel_id FROM knowledge_publication_channels WHERE state='active'"
                ).fetchall():
                    directive_id = _urn("serving-directive", _digest({
                        "action": action,
                        "target": proposition_id,
                        "channel": channel["channel_id"],
                        "invalidation": invalidation_id,
                    }))
                    self.db.execute(
                        "INSERT OR IGNORE INTO knowledge_serving_directives(directive_id,action,target_type,target_id,channel_id,reason,actor) VALUES(?,?,?,?,?,?,?)",
                        (
                            directive_id, action, "claim", str(proposition_id),
                            channel["channel_id"], reason, actor,
                        ),
                    )
            for snapshot_id in snapshot_ids:
                self.db.execute(
                    "UPDATE knowledge_projection_manifests SET projection_state='stale' WHERE source_snapshot_id=? AND projection_state='ready'",
                    (snapshot_id,),
                )
        synthesis_ids: list[str] = []
        question_ids: list[str] = []
        for row in self.db.execute(
            "SELECT synthesis_id,input_claim_ids_json FROM knowledge_syntheses"
        ).fetchall():
            if proposition_ids.intersection(
                int(v) for v in json.loads(row["input_claim_ids_json"])
            ):
                synthesis_ids.append(row["synthesis_id"])
        for row in self.db.execute(
            "SELECT question_id,related_claim_ids_json FROM knowledge_questions"
        ).fetchall():
            if proposition_ids.intersection(
                int(v) for v in json.loads(row["related_claim_ids_json"])
            ):
                question_ids.append(row["question_id"])
        return {
            "contract": "erasmus.knowledge-impact/v1",
            "invalidation_id": invalidation_id,
            "source_id": source_id,
            "proposition_ids": [str(v) for v in sorted(proposition_ids)],
            "revision_ids": sorted(revision_ids),
            "snapshot_ids": sorted(snapshot_ids),
            "synthesis_ids": sorted(synthesis_ids),
            "question_ids": sorted(question_ids),
            "materiality": materiality,
        }

    def set_intake_state(self, enabled: bool, actor: str, authority: str) -> None:
        self._gate("knowledge:intake-admin", actor)
        if authority != "knowledge:intake-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:intake-admin required")
        with self.db:
            self.db.execute(
                "UPDATE knowledge_intake_control SET enabled=?,actor=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (int(bool(enabled)), actor),
            )

    def enqueue_intake(
        self,
        producer: str,
        payload: dict[str, Any],
        actor: str,
        authority: str,
        max_pending: int = 1000,
    ) -> dict[str, Any]:
        self._gate("knowledge:intake", actor)
        if authority != "knowledge:intake":
            raise PermissionError("knowledge:intake required")
        if producer not in {
            "foundry", "sleep", "mission", "deterministic", "repository",
            "reconnaissance", "model", "route",
        }:
            raise ValueError("unsupported intake producer")
        control = self.db.execute(
            "SELECT enabled FROM knowledge_intake_control WHERE id=1"
        ).fetchone()
        if control is None or not control["enabled"]:
            raise RuntimeError("knowledge intake is stopped")
        pending = self.db.execute(
            "SELECT COUNT(*) FROM knowledge_intake_queue WHERE state IN ('queued','processing')"
        ).fetchone()[0]
        if pending >= max_pending:
            raise RuntimeError("knowledge intake backpressure budget exceeded")
        payload_digest = _digest(payload)
        existing = self.db.execute(
            "SELECT * FROM knowledge_intake_queue WHERE producer=? AND payload_digest=?",
            (producer, payload_digest),
        ).fetchone()
        if existing:
            return dict(existing)
        intake_id = _urn("intake", _digest({
            "producer": producer, "payload": payload_digest
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_intake_queue(intake_id,producer,payload_json,payload_digest,disposition,state,actor,authority) VALUES(?,?,?,?,?,'queued',?,?)",
                (
                    intake_id, producer, _json(payload), payload_digest,
                    "quarantined", actor, authority,
                ),
            )
        return dict(self.db.execute(
            "SELECT * FROM knowledge_intake_queue WHERE intake_id=?", (intake_id,)
        ).fetchone())

    def list_intake(self, state: str | None = None) -> list[dict[str, Any]]:
        if state is None:
            rows = self.db.execute(
                "SELECT * FROM knowledge_intake_queue ORDER BY created_at,intake_id"
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM knowledge_intake_queue WHERE state=? ORDER BY created_at,intake_id",
                (state,),
            ).fetchall()
        return [dict(row) for row in rows]

    def routing_context(
        self, query: str, channel_id: str, limit: int, actor: str, authority: str
    ) -> dict[str, Any]:
        return self.hybrid_retrieve(
            query, channel_id, limit, actor, authority, adapter=None
        )

    def _packet_source_ids(self, packet: dict[str, Any]) -> list[str]:
        source_ids: set[str] = set()
        for item in packet.get("items", []):
            try:
                inspected = self.ledger.inspect(int(item["claim_id"]))
            except (ValueError, KeyError):
                continue
            for evidence in inspected["evidence"]:
                provenance = evidence.get("provenance")
                if provenance is None:
                    provenance = evidence.get("provenance_json")
                    if isinstance(provenance, str):
                        try:
                            provenance = json.loads(provenance)
                        except json.JSONDecodeError:
                            continue
                if not isinstance(provenance, dict):
                    continue
                for span_id in provenance.get("source_span_ids", []):
                    row = self.db.execute(
                        "SELECT source_id FROM knowledge_source_spans WHERE span_id=?",
                        (span_id,),
                    ).fetchone()
                    if row:
                        source_ids.add(row["source_id"])
        return sorted(source_ids)

    def record_route_decision(
        self,
        route_id: str,
        selected_route: str,
        packet: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        if authority != "routing:decide":
            raise PermissionError("routing:decide required")
        if packet.get("contract") != "erasmus.evidence-packet/v1":
            raise ValueError("routing requires a governed evidence packet")
        claim_ids = [item["claim_id"] for item in packet.get("items", [])]
        source_ids = self._packet_source_ids(packet)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_route_decisions(route_id,selected_route,packet_id,claim_ids_json,source_ids_json,actor,authority) VALUES(?,?,?,?,?,?,?)",
                (
                    route_id, selected_route, packet["packet_id"],
                    _json(claim_ids), _json(source_ids), actor, authority,
                ),
            )
        row = dict(self.db.execute(
            "SELECT * FROM knowledge_route_decisions WHERE route_id=?", (route_id,)
        ).fetchone())
        row["claim_ids"] = json.loads(row["claim_ids_json"])
        row["source_ids"] = json.loads(row["source_ids_json"])
        return row

    def record_route_outcome(
        self,
        route_id: str,
        outcome: str,
        detail: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        if authority != "routing:feedback":
            raise PermissionError("routing:feedback required")
        if outcome not in {"success", "failure", "cancelled"}:
            raise ValueError("invalid route outcome")
        if self.db.execute(
            "SELECT 1 FROM knowledge_route_decisions WHERE route_id=?", (route_id,)
        ).fetchone() is None:
            raise ValueError("route decision not found")
        outcome_id = _urn("route-outcome", _digest({
            "route": route_id, "outcome": outcome, "detail": detail
        }))
        payload = {"route_id": route_id, "outcome": outcome, "detail": detail}
        payload_digest = _digest(payload)
        intake_id = _urn("intake", _digest({
            "producer": "route", "payload": payload_digest
        }))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_route_outcomes(outcome_id,route_id,outcome,detail_json,actor,authority) VALUES(?,?,?,?,?,?)",
                (outcome_id, route_id, outcome, _json(detail), actor, authority),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_intake_queue(intake_id,producer,payload_json,payload_digest,disposition,state,actor,authority) VALUES(?,?,?,?,?,'queued',?,?)",
                (
                    intake_id, "route", _json(payload), payload_digest,
                    "quarantined", actor, authority,
                ),
            )
        return dict(self.db.execute(
            "SELECT * FROM knowledge_intake_queue WHERE intake_id=?", (intake_id,)
        ).fetchone())
