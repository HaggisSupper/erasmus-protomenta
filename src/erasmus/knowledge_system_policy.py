from __future__ import annotations

import json
from datetime import date
from typing import Any

from .knowledge_runtime import _digest, _json, _urn


class PolicyFacadeMixin:
    """Mandatory active-policy gate and governed core mutation facade."""

    def _gate(self, operation: str, actor: str, scope: dict[str, Any] | None = None) -> None:
        scope = scope or {
            "visibility": "private",
            "tenant": "local",
            "project": None,
            "domain": None,
            "labels": [],
        }
        receipt = self.evaluate_policy(operation, actor, scope)
        if receipt["decision"] != "permit":
            raise PermissionError(f"active policy denied {operation}")

    def register_source_bytes(self, data, locator, media_type, scope, actor, authority):
        self._gate("knowledge:source-register", actor, scope)
        return super().register_source_bytes(data, locator, media_type, scope, actor, authority)

    def register_source_span(self, source_id, coordinate, extracted_text, scope, actor, authority):
        self._gate("knowledge:source-register", actor, scope)
        return super().register_source_span(source_id, coordinate, extracted_text, scope, actor, authority)

    def import_candidate(self, producer, title, body, source_ids, source_span_ids, scope, actor, authority):
        self._gate("knowledge:candidate-import", actor, scope)
        return super().import_candidate(producer, title, body, source_ids, source_span_ids, scope, actor, authority)

    def add_candidate_claim(self, candidate_id, statement, source_span_ids, qualifiers, scope, risk_class, actor, authority):
        self._gate("knowledge:claim-decompose", actor, scope)
        return super().add_candidate_claim(candidate_id, statement, source_span_ids, qualifiers, scope, risk_class, actor, authority)

    def create_entity(self, entity_type, canonical_name, scope, actor, authority):
        self._gate("knowledge:identity-write", actor, scope)
        return super().create_entity(entity_type, canonical_name, scope, actor, authority)

    def add_entity_alias(self, entity_id, alias, namespace, actor, authority):
        entity = self.db.execute(
            "SELECT scope_json FROM knowledge_entities WHERE entity_id=?", (entity_id,)
        ).fetchone()
        self._gate(
            "knowledge:identity-write", actor,
            json.loads(entity["scope_json"]) if entity else None,
        )
        return super().add_entity_alias(entity_id, alias, namespace, actor, authority)

    def record_identity_decision(self, left_entity_id, right_entity_id, decision, actor, authority, rationale):
        self._gate("knowledge:identity-decide", actor)
        return super().record_identity_decision(
            left_entity_id, right_entity_id, decision, actor, authority, rationale
        )

    def create_concept(self, title, concept_type, claim_ids, scope, actor, authority):
        self._gate("knowledge:concept-write", actor, scope)
        return super().create_concept(title, concept_type, claim_ids, scope, actor, authority)

    def create_concept_revision(self, concept_id, title, description, claim_ids, relationship_ids, okf_path, actor, authority):
        concept = self.db.execute(
            "SELECT scope_json FROM knowledge_concepts WHERE concept_id=?", (concept_id,)
        ).fetchone()
        self._gate(
            "knowledge:concept-write", actor,
            json.loads(concept["scope_json"]) if concept else None,
        )
        return super().create_concept_revision(
            concept_id, title, description, claim_ids, relationship_ids,
            okf_path, actor, authority,
        )

    def record_review(self, revision_id, review_type, verdict, reviewer, producer, authority):
        self._gate("knowledge:review", reviewer)
        return super().record_review(
            revision_id, review_type, verdict, reviewer, producer, authority
        )

    def transition_concept(self, concept_id, target, revision_id, actor, authority):
        self._gate("knowledge:promote", actor)
        before = self.db.execute(
            "SELECT concept_lifecycle FROM knowledge_concepts WHERE concept_id=?",
            (concept_id,),
        ).fetchone()
        result = super().transition_concept(
            concept_id, target, revision_id, actor, authority
        )
        transition_id = _urn("concept-transition", _digest({
            "concept": concept_id,
            "revision": revision_id,
            "from": before["concept_lifecycle"] if before else None,
            "to": target,
            "actor": actor,
            "ordinal": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_concept_transitions WHERE concept_id=?",
                (concept_id,),
            ).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_concept_transitions(transition_id,concept_id,revision_id,from_state,to_state,actor,authority,reason) VALUES(?,?,?,?,?,?,?,?)",
                (
                    transition_id, concept_id, revision_id,
                    before["concept_lifecycle"], target, actor, authority,
                    "governed lifecycle transition",
                ),
            )
        return result

    def create_question(self, text, related_claim_ids, scope, actor, authority):
        self._gate("knowledge:question-write", actor, scope)
        return super().create_question(text, related_claim_ids, scope, actor, authority)

    def answer_question(self, question_id, answer_claim_ids, actor, authority):
        self._gate("knowledge:question-write", actor)
        return super().answer_question(question_id, answer_claim_ids, actor, authority)

    def create_synthesis(self, text, input_claim_ids, interpretations, scope, actor, authority):
        self._gate("knowledge:synthesis-write", actor, scope)
        return super().create_synthesis(
            text, input_claim_ids, interpretations, scope, actor, authority
        )


class ReconciliationFacadeMixin:
    """Complete P3.6 reconciliation semantics over the existing ledger."""

    def reconcile_claim(
        self,
        candidate_claim_id: str,
        action: str,
        actor: str,
        authority: str,
        mission_id: int,
        idempotency_key: str,
        target_proposition_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        self._gate("knowledge:reconcile", actor)
        if action not in {"amend", "supersede"}:
            return super().reconcile_claim(
                candidate_claim_id, action, actor, authority, mission_id,
                idempotency_key, target_proposition_ids,
            )
        if authority != "knowledge:reconcile" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:reconcile required")
        prior = self.db.execute(
            "SELECT decision_id,result_json FROM knowledge_reconciliation_decisions WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if prior:
            return {"decision_id": prior["decision_id"], **json.loads(prior["result_json"])}
        targets = target_proposition_ids or []
        if len(targets) != 1:
            raise ValueError(f"{action} requires exactly one target proposition")
        claim = self.db.execute(
            "SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?",
            (candidate_claim_id,),
        ).fetchone()
        if claim is None:
            raise ValueError("candidate claim not found")
        old_id = targets[0]
        old = self.ledger.inspect(old_id)
        evidence_id = self.ledger.add_evidence(
            "evidence", claim["statement"], "document",
            {"candidate_claim_id": candidate_claim_id, "action": action},
            "contextual", date.today().isoformat(), old["scope"], actor,
            "ledger:write",
        )
        new_id = self.ledger.propose(
            claim["statement"], evidence_id, actor, "ledger:write",
            scope=old["scope"], status="speculative",
            reason=f"Phase 3 governed {action}",
        )
        self.ledger.supersede(
            old_id, new_id, evidence_id, actor, "ledger:write",
            f"Phase 3 governed {action}",
        )
        result = {
            "action": action,
            "candidate_claim_id": candidate_claim_id,
            "proposition_id": new_id,
            "target_proposition_ids": targets,
        }
        decision_id = _urn("reconciliation-decision", _digest({
            "claim": candidate_claim_id,
            "action": action,
            "mission": mission_id,
            "key": idempotency_key,
            "targets": targets,
        }))
        binding_id = _urn("claim-binding", _digest({
            "claim": candidate_claim_id,
            "proposition": new_id,
            "decision": decision_id,
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_reconciliation_decisions(decision_id,candidate_claim_id,action,target_proposition_ids_json,mission_id,idempotency_key,actor,authority,result_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    decision_id, candidate_claim_id, action, _json(targets),
                    mission_id, idempotency_key, actor, authority, _json(result),
                ),
            )
            self.db.execute(
                "INSERT INTO knowledge_claim_bindings(binding_id,candidate_claim_id,proposition_id,relation,decision_id) VALUES(?,?,?,?,?)",
                (binding_id, candidate_claim_id, new_id, action, decision_id),
            )
        return {"decision_id": decision_id, **result}
