from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .ledger import EpistemicLedger
from .store import Store


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _urn(kind: str, value: str) -> str:
    return f"urn:erasmus:{kind}:{value}"


def _row(row: Any) -> dict[str, Any] | None:
    return None if row is None else dict(row)


class KnowledgeRuntime:
    """Governed Phase 3 knowledge runtime.

    The service owns semantic records and projections but delegates proposition
    truth-state transitions to :class:`EpistemicLedger`.
    """

    def __init__(self, store: Store, artifact_root: str | Path = "state/knowledge") -> None:
        self.store = store
        self.db = store.db
        self.ledger = EpistemicLedger(store)
        self.root = Path(artifact_root).resolve()
        self.sources_root = self.root / "sources"
        self.snapshots_root = self.root / "snapshots"
        self.sources_root.mkdir(parents=True, exist_ok=True)
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self._ensure_private_channel()

    # ---------- policy / registry / channels ----------
    def _ensure_private_channel(self) -> None:
        scope = {"visibility": "private", "tenant": "local", "project": None, "domain": None, "labels": []}
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_publication_channels(channel_id, scope_json, audience) VALUES('private', ?, 'private')",
                (_json(scope),),
            )

    def register_policy_set(self, policy_set_id: str, rules: list[dict[str, Any]], actor: str, authority: str) -> str:
        if authority != "knowledge:policy-admin":
            raise PermissionError("knowledge:policy-admin required")
        if not policy_set_id or not isinstance(rules, list) or not rules:
            raise ValueError("policy set id and rules are required")
        for rule in rules:
            if rule.get("effect") not in {"permit", "deny"} or not rule.get("operation") or not rule.get("actor"):
                raise ValueError("invalid policy rule")
        digest = _digest({"policy_set_id": policy_set_id, "rules": rules})
        with self.db:
            existing = self.db.execute("SELECT digest FROM knowledge_policy_sets WHERE policy_set_id=?", (policy_set_id,)).fetchone()
            if existing and existing["digest"] != digest:
                raise ValueError("policy set id already identifies different content")
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_policy_sets(policy_set_id,digest,rules_json,actor) VALUES(?,?,?,?)",
                (policy_set_id, digest, _json(rules), actor),
            )
        return digest

    def activate_policy_set(self, policy_set_id: str, digest: str, actor: str, authority: str) -> None:
        if authority != "knowledge:policy-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:policy-admin required")
        row = self.db.execute("SELECT digest FROM knowledge_policy_sets WHERE policy_set_id=?", (policy_set_id,)).fetchone()
        if row is None or row["digest"] != digest:
            raise ValueError("exact policy digest required")
        with self.db:
            self.db.execute("UPDATE knowledge_policy_sets SET state='inactive' WHERE state='active'")
            self.db.execute("UPDATE knowledge_policy_sets SET state='active' WHERE policy_set_id=? AND digest=?", (policy_set_id, digest))

    def evaluate_policy(self, operation: str, actor: str, scope: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        active = self.db.execute("SELECT * FROM knowledge_policy_sets WHERE state='active' ORDER BY created_at DESC LIMIT 1").fetchone()
        matched: list[dict[str, Any]] = []
        decision = "deny"
        policy_id = policy_digest = None
        if active:
            policy_id, policy_digest = active["policy_set_id"], active["digest"]
            rules = json.loads(active["rules_json"])
            matched = [r for r in rules if fnmatch.fnmatchcase(operation, r["operation"]) and fnmatch.fnmatchcase(actor, r["actor"])]
            if matched and any(r["effect"] == "permit" for r in matched) and not any(r["effect"] == "deny" for r in matched):
                decision = "permit"
        payload = {
            "policy_set_id": policy_id,
            "policy_digest": policy_digest,
            "operation": operation,
            "actor": actor,
            "scope": scope,
            "decision": decision,
            "matched_rules": matched,
            "dry_run": bool(dry_run),
        }
        receipt_id = _urn("policy-receipt", _digest(payload))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_policy_receipts(receipt_id,policy_set_id,policy_digest,operation,actor,scope_json,decision,matched_rules_json,dry_run) VALUES(?,?,?,?,?,?,?,?,?)",
                (receipt_id, policy_id, policy_digest, operation, actor, _json(scope), decision, _json(matched), int(bool(dry_run))),
            )
        return {"receipt_id": receipt_id, **payload}

    def register_semantic_registry(self, registry_id: str, definitions: dict[str, Any], actor: str, authority: str) -> str:
        if authority != "knowledge:registry-admin":
            raise PermissionError("knowledge:registry-admin required")
        digest = _digest({"registry_id": registry_id, "definitions": definitions})
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_semantic_registry(registry_id,digest,definitions_json,actor) VALUES(?,?,?,?)", (registry_id, digest, _json(definitions), actor))
        return digest

    def ensure_channel(self, channel_id: str, scope: dict[str, Any], audience: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:channel-admin":
            raise PermissionError("knowledge:channel-admin required")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_publication_channels(channel_id,scope_json,audience) VALUES(?,?,?)", (channel_id, _json(scope), audience))
        return _row(self.db.execute("SELECT * FROM knowledge_publication_channels WHERE channel_id=?", (channel_id,)).fetchone()) or {}

    # ---------- sources / candidates / claims ----------
    def register_source_bytes(self, data: bytes, locator: str, media_type: str, scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:source-register":
            raise PermissionError("knowledge:source-register required")
        if not isinstance(data, bytes) or not locator or not media_type:
            raise ValueError("source bytes, locator and media type are required")
        digest = hashlib.sha256(data).hexdigest()
        source_id = _urn("source", digest)
        target = (self.sources_root / digest[:2] / digest).resolve()
        if not target.is_relative_to(self.sources_root):
            raise ValueError("source storage escaped root")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise ValueError("existing digest path contains different bytes")
        if not target.exists():
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_sources(source_id,digest,locator,media_type,byte_size,scope_json,storage_path,actor) VALUES(?,?,?,?,?,?,?,?)",
                (source_id, digest, locator, media_type, len(data), _json(scope), str(target), actor),
            )
        return _row(self.db.execute("SELECT * FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone()) or {}

    def register_source_span(self, source_id: str, coordinate: dict[str, Any], extracted_text: str, scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:source-register":
            raise PermissionError("knowledge:source-register required")
        source = self.db.execute("SELECT * FROM knowledge_sources WHERE source_id=? AND tombstoned=0", (source_id,)).fetchone()
        if source is None:
            raise ValueError("source not found")
        text_digest = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
        span_id = _urn("span", _digest({"source_id": source_id, "coordinate": coordinate, "text_digest": text_digest}))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_source_spans(span_id,source_id,coordinate_json,text_digest,extracted_text,scope_json,actor) VALUES(?,?,?,?,?,?,?)",
                (span_id, source_id, _json(coordinate), text_digest, extracted_text, _json(scope), actor),
            )
        result = _row(self.db.execute("SELECT * FROM knowledge_source_spans WHERE span_id=?", (span_id,)).fetchone()) or {}
        result["coordinate"] = json.loads(result.pop("coordinate_json"))
        result["scope"] = json.loads(result.pop("scope_json"))
        return result

    def get_source_span(self, span_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM knowledge_source_spans WHERE span_id=?", (span_id,)).fetchone()
        if row is None:
            raise ValueError("source span not found")
        return dict(row)

    def import_candidate(self, producer: str, title: str, body: str, source_ids: list[str], source_span_ids: list[str], scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:candidate-import":
            raise PermissionError("knowledge:candidate-import required")
        if not producer or not title or not body or not source_ids:
            raise ValueError("producer, title, body and source ids are required")
        for source_id in source_ids:
            if self.db.execute("SELECT 1 FROM knowledge_sources WHERE source_id=? AND tombstoned=0", (source_id,)).fetchone() is None:
                raise ValueError(f"missing source: {source_id}")
        for span_id in source_span_ids:
            if self.db.execute("SELECT 1 FROM knowledge_source_spans WHERE span_id=?", (span_id,)).fetchone() is None:
                raise ValueError(f"missing source span: {span_id}")
        content = {"producer": producer, "title": title, "body": body, "source_ids": sorted(source_ids), "source_span_ids": sorted(source_span_ids), "scope": scope}
        content_digest = _digest(content)
        candidate_id = _urn("candidate", content_digest)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_candidates(candidate_id,producer,title,body,source_ids_json,source_span_ids_json,scope_json,candidate_disposition,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (candidate_id, producer, title, body, _json(sorted(source_ids)), _json(sorted(source_span_ids)), _json(scope), "quarantined", content_digest, actor),
            )
        return _row(self.db.execute("SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()) or {}

    def add_candidate_claim(self, candidate_id: str, statement: str, source_span_ids: list[str], qualifiers: dict[str, Any], scope: dict[str, Any], risk_class: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:claim-decompose":
            raise PermissionError("knowledge:claim-decompose required")
        if not statement.strip() or not source_span_ids:
            raise ValueError("candidate claims require a statement and source spans")
        if risk_class not in {"routine", "consequential", "protected"}:
            raise ValueError("invalid risk class")
        candidate = self.db.execute("SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if candidate is None:
            raise ValueError("candidate not found")
        for span_id in source_span_ids:
            if self.db.execute("SELECT 1 FROM knowledge_source_spans WHERE span_id=?", (span_id,)).fetchone() is None:
                raise ValueError("source span not found")
        content_digest = _digest({"statement": statement.strip(), "spans": sorted(source_span_ids), "qualifiers": qualifiers, "scope": scope, "risk": risk_class})
        claim_id = _urn("candidate-claim", content_digest)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_candidate_claims(candidate_claim_id,candidate_id,statement,source_span_ids_json,qualifiers_json,scope_json,risk_class,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?)",
                (claim_id, candidate_id, statement.strip(), _json(sorted(source_span_ids)), _json(qualifiers), _json(scope), risk_class, content_digest, actor),
            )
        return _row(self.db.execute("SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?", (claim_id,)).fetchone()) or {}

    # ---------- identity ----------
    def create_entity(self, entity_type: str, canonical_name: str, scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:identity-write":
            raise PermissionError("knowledge:identity-write required")
        if not entity_type or not canonical_name.strip():
            raise ValueError("entity type and canonical name required")
        entity_id = _urn("entity", _digest({"type": entity_type, "name": canonical_name, "scope": scope, "nonce": self.db.execute("SELECT COUNT(*) FROM knowledge_entities").fetchone()[0]}))
        with self.db:
            self.db.execute("INSERT INTO knowledge_entities(entity_id,entity_type,canonical_name,scope_json,actor) VALUES(?,?,?,?,?)", (entity_id, entity_type, canonical_name, _json(scope), actor))
        return _row(self.db.execute("SELECT * FROM knowledge_entities WHERE entity_id=?", (entity_id,)).fetchone()) or {}

    def add_entity_alias(self, entity_id: str, alias: str, namespace: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:identity-write":
            raise PermissionError("knowledge:identity-write required")
        if self.db.execute("SELECT 1 FROM knowledge_entities WHERE entity_id=?", (entity_id,)).fetchone() is None:
            raise ValueError("entity not found")
        alias_id = _urn("entity-alias", _digest({"entity": entity_id, "alias": alias, "namespace": namespace}))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_entity_aliases(alias_id,entity_id,alias,namespace,actor) VALUES(?,?,?,?,?)", (alias_id, entity_id, alias, namespace, actor))
        return _row(self.db.execute("SELECT * FROM knowledge_entity_aliases WHERE alias_id=?", (alias_id,)).fetchone()) or {}

    def resolve_entity_exact(self, value: str, scope: dict[str, Any]) -> dict[str, Any]:
        scope_json = _json(scope)
        rows = self.db.execute(
            """
            SELECT entity_id FROM knowledge_entities WHERE canonical_name=? AND scope_json=? AND retired=0
            UNION
            SELECT a.entity_id FROM knowledge_entity_aliases a JOIN knowledge_entities e ON e.entity_id=a.entity_id
            WHERE a.alias=? AND e.scope_json=? AND e.retired=0
            """, (value, scope_json, value, scope_json),
        ).fetchall()
        ids = sorted({row[0] for row in rows})
        return {"query": value, "entity_ids": ids, "ambiguous": len(ids) != 1}

    def record_identity_decision(self, left_entity_id: str, right_entity_id: str, decision: str, actor: str, authority: str, rationale: str) -> dict[str, Any]:
        if authority != "knowledge:identity-decide" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:identity-decide required")
        if decision not in {"same_entity","distinct_entity","alias_of","successor_of","version_of","part_of","unresolved"}:
            raise ValueError("invalid identity decision")
        for entity_id in (left_entity_id, right_entity_id):
            if self.db.execute("SELECT 1 FROM knowledge_entities WHERE entity_id=?", (entity_id,)).fetchone() is None:
                raise ValueError("entity not found")
        decision_id = _urn("identity-decision", _digest({"left": left_entity_id, "right": right_entity_id, "decision": decision, "rationale": rationale}))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_identity_decisions(decision_id,left_entity_id,right_entity_id,decision,rationale,actor) VALUES(?,?,?,?,?,?)", (decision_id,left_entity_id,right_entity_id,decision,rationale,actor))
        return _row(self.db.execute("SELECT * FROM knowledge_identity_decisions WHERE decision_id=?", (decision_id,)).fetchone()) or {}

    # ---------- comparison / reconciliation ----------
    def compare_claim(self, candidate_claim_id: str, limit: int = 10) -> dict[str, Any]:
        claim = self.db.execute("SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?", (candidate_claim_id,)).fetchone()
        if claim is None:
            raise ValueError("candidate claim not found")
        rows = self.db.execute(
            """
            SELECT p.id, p.statement, COALESCE(t.new_status,p.status) status
            FROM propositions p
            LEFT JOIN proposition_transitions t ON t.id=(SELECT id FROM proposition_transitions WHERE proposition_id=p.id ORDER BY id DESC LIMIT 1)
            WHERE lower(p.statement)=lower(?) ORDER BY p.id LIMIT ?
            """, (claim["statement"], limit),
        ).fetchall()
        return {"candidate_claim_id": candidate_claim_id, "targets": [{"proposition_id": r["id"], "statement": r["statement"], "status": r["status"], "reason": "exact_statement"} for r in rows], "budget": {"limit": limit, "used": len(rows)}}

    def reconcile_claim(self, candidate_claim_id: str, action: str, actor: str, authority: str, mission_id: int, idempotency_key: str, target_proposition_ids: list[int] | None = None) -> dict[str, Any]:
        if authority != "knowledge:reconcile" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:reconcile required")
        prior = self.db.execute("SELECT result_json,decision_id FROM knowledge_reconciliation_decisions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if prior:
            result = json.loads(prior["result_json"])
            result["decision_id"] = prior["decision_id"]
            return result
        claim = self.db.execute("SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?", (candidate_claim_id,)).fetchone()
        if claim is None:
            raise ValueError("candidate claim not found")
        target_proposition_ids = target_proposition_ids or []
        if action not in {"create","corroborate","amend","contradict","supersede","duplicate","reject","insufficient_evidence"}:
            raise ValueError("invalid reconciliation action")
        proposition_id: int | None = None
        if action == "create":
            if self.compare_claim(candidate_claim_id)["targets"]:
                raise ValueError("exact duplicate cannot create proposition")
            evidence_id = self.ledger.add_evidence(
                "evidence", claim["statement"], "document",
                {"candidate_claim_id": candidate_claim_id, "source_span_ids": json.loads(claim["source_span_ids_json"])},
                "contextual", date.today().isoformat(), "global", actor, "ledger:write",
            )
            proposition_id = self.ledger.propose(claim["statement"], evidence_id, actor, "ledger:write", scope="global", status="speculative", reason="Phase 3 governed reconciliation")
        elif action in {"corroborate","contradict","supersede"} and not target_proposition_ids:
            raise ValueError(f"{action} requires target proposition ids")
        elif action == "corroborate":
            evidence_id = self.ledger.add_evidence("evidence", claim["statement"], "document", {"candidate_claim_id": candidate_claim_id}, "contextual", date.today().isoformat(), "global", actor, "ledger:write")
            target = self.ledger.inspect(target_proposition_ids[0])
            next_status = {"speculative":"plausible","analogy":"plausible","leap":"plausible","unresolved":"plausible","plausible":"supported","contradicted":"supported","supported":"established"}.get(target["status"])
            if next_status is None:
                raise ValueError("target cannot be corroborated further")
            self.ledger.transition(target_proposition_ids[0], "support", evidence_id, actor, "ledger:write", "Phase 3 corroboration", target_status=next_status)
            proposition_id = target_proposition_ids[0]
        elif action == "contradict":
            evidence_id = self.ledger.add_evidence("contradiction", claim["statement"], "document", {"candidate_claim_id": candidate_claim_id}, "contextual", date.today().isoformat(), "global", actor, "ledger:write")
            self.ledger.transition(target_proposition_ids[0], "contradict", evidence_id, actor, "ledger:write", "Phase 3 contradiction")
            proposition_id = target_proposition_ids[0]
        result = {"action": action, "candidate_claim_id": candidate_claim_id, "proposition_id": proposition_id, "target_proposition_ids": target_proposition_ids}
        decision_id = _urn("reconciliation-decision", _digest({"claim": candidate_claim_id, "action": action, "mission": mission_id, "key": idempotency_key, "targets": target_proposition_ids}))
        with self.db:
            self.db.execute("INSERT INTO knowledge_reconciliation_decisions(decision_id,candidate_claim_id,action,target_proposition_ids_json,mission_id,idempotency_key,actor,authority,result_json) VALUES(?,?,?,?,?,?,?,?,?)", (decision_id,candidate_claim_id,action,_json(target_proposition_ids),mission_id,idempotency_key,actor,authority,_json(result)))
            if proposition_id is not None:
                binding_id = _urn("claim-binding", _digest({"claim": candidate_claim_id, "proposition": proposition_id, "decision": decision_id}))
                self.db.execute("INSERT INTO knowledge_claim_bindings(binding_id,candidate_claim_id,proposition_id,relation,decision_id) VALUES(?,?,?,?,?)", (binding_id,candidate_claim_id,proposition_id,action,decision_id))
        return {"decision_id": decision_id, **result}

    # ---------- concepts / review / questions ----------
    def create_concept(self, title: str, concept_type: str, claim_ids: list[int], scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:concept-write":
            raise PermissionError("knowledge:concept-write required")
        for claim_id in claim_ids:
            self.ledger.inspect(claim_id)
        concept_id = _urn("concept", _digest({"title": title, "type": concept_type, "scope": scope, "nonce": self.db.execute("SELECT COUNT(*) FROM knowledge_concepts").fetchone()[0]}))
        with self.db:
            self.db.execute("INSERT INTO knowledge_concepts(concept_id,concept_type,scope_json,actor) VALUES(?,?,?,?)", (concept_id,concept_type,_json(scope),actor))
        return _row(self.db.execute("SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone()) or {}

    def create_concept_revision(self, concept_id: str, title: str, description: str, claim_ids: list[int], relationship_ids: list[str], okf_path: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:concept-write":
            raise PermissionError("knowledge:concept-write required")
        if not okf_path or okf_path.startswith("/") or ".." in Path(okf_path).parts:
            raise ValueError("invalid OKF path")
        if self.db.execute("SELECT 1 FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone() is None:
            raise ValueError("concept not found")
        for claim_id in claim_ids:
            self.ledger.inspect(claim_id)
        revision_number = self.db.execute("SELECT COALESCE(MAX(revision_number),0)+1 FROM knowledge_concept_revisions WHERE concept_id=?", (concept_id,)).fetchone()[0]
        content_digest = _digest({"concept_id":concept_id,"revision":revision_number,"title":title,"description":description,"claims":claim_ids,"relationships":relationship_ids,"path":okf_path})
        revision_id = _urn("concept-revision", content_digest)
        with self.db:
            self.db.execute("INSERT INTO knowledge_concept_revisions(revision_id,concept_id,revision_number,title,description,claim_ids_json,relationship_ids_json,okf_path,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?,?)", (revision_id,concept_id,revision_number,title,description,_json(claim_ids),_json(relationship_ids),okf_path,content_digest,actor))
        return _row(self.db.execute("SELECT * FROM knowledge_concept_revisions WHERE revision_id=?", (revision_id,)).fetchone()) or {}

    def record_review(self, revision_id: str, review_type: str, verdict: str, reviewer: str, producer: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:review":
            raise PermissionError("knowledge:review required")
        if reviewer == producer:
            raise ValueError("producer/reviewer independence required")
        if verdict not in {"pass","pass_with_conditions","fail","insufficient_evidence"}:
            raise ValueError("invalid review verdict")
        revision = self.db.execute("SELECT * FROM knowledge_concept_revisions WHERE revision_id=?", (revision_id,)).fetchone()
        if revision is None:
            raise ValueError("revision not found")
        review_id = _urn("review", _digest({"revision": revision_id, "type": review_type, "reviewer": reviewer, "verdict": verdict, "inputs": revision["content_digest"]}))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_reviews(review_id,revision_id,review_type,verdict,reviewer,producer,inputs_digest,authority) VALUES(?,?,?,?,?,?,?,?)", (review_id,revision_id,review_type,verdict,reviewer,producer,revision["content_digest"],authority))
        return _row(self.db.execute("SELECT * FROM knowledge_reviews WHERE review_id=?", (review_id,)).fetchone()) or {}

    def transition_concept(self, concept_id: str, target: str, revision_id: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:promote":
            raise PermissionError("knowledge:promote required")
        concept = self.db.execute("SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone()
        revision = self.db.execute("SELECT * FROM knowledge_concept_revisions WHERE revision_id=? AND concept_id=?", (revision_id,concept_id)).fetchone()
        if concept is None or revision is None:
            raise ValueError("concept/revision mismatch")
        current = concept["concept_lifecycle"]
        allowed = {"provisional":{"reviewed","rejected"},"reviewed":{"validated","contested","rejected"},"validated":{"contested","canonical","deprecated"},"contested":{"reviewed","rejected"},"canonical":{"superseded","deprecated"}}
        if target not in allowed.get(current, set()):
            raise ValueError(f"illegal concept transition {current}->{target}")
        if target in {"reviewed","validated"}:
            passing = self.db.execute("SELECT 1 FROM knowledge_reviews WHERE revision_id=? AND inputs_digest=? AND verdict IN ('pass','pass_with_conditions') LIMIT 1", (revision_id,revision["content_digest"])).fetchone()
            if passing is None:
                raise ValueError("passing revision-bound review required")
        with self.db:
            self.db.execute("UPDATE knowledge_concepts SET concept_lifecycle=? WHERE concept_id=?", (target, concept_id))
        return _row(self.db.execute("SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone()) or {}

    def create_question(self, text: str, related_claim_ids: list[int], scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:question-write":
            raise PermissionError("knowledge:question-write required")
        for claim_id in related_claim_ids:
            self.ledger.inspect(claim_id)
        question_id = _urn("question", _digest({"text":text,"claims":related_claim_ids,"scope":scope,"nonce":self.db.execute("SELECT COUNT(*) FROM knowledge_questions").fetchone()[0]}))
        with self.db:
            self.db.execute("INSERT INTO knowledge_questions(question_id,text,related_claim_ids_json,scope_json,actor) VALUES(?,?,?,?,?)", (question_id,text,_json(related_claim_ids),_json(scope),actor))
        return _row(self.db.execute("SELECT * FROM knowledge_questions WHERE question_id=?", (question_id,)).fetchone()) or {}

    def answer_question(self, question_id: str, answer_claim_ids: list[int], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:question-write":
            raise PermissionError("knowledge:question-write required")
        if not answer_claim_ids:
            raise ValueError("grounded answer claims required")
        for claim_id in answer_claim_ids:
            state = self.ledger.inspect(claim_id)["status"]
            if state in {"unresolved","falsified","contradicted"}:
                raise ValueError("answer claim is not suitable for closure")
        with self.db:
            changed = self.db.execute("UPDATE knowledge_questions SET question_state='answered',answer_claim_ids_json=? WHERE question_id=?", (_json(answer_claim_ids),question_id)).rowcount
        if not changed:
            raise ValueError("question not found")
        return _row(self.db.execute("SELECT * FROM knowledge_questions WHERE question_id=?", (question_id,)).fetchone()) or {}

    def create_synthesis(self, text: str, input_claim_ids: list[int], interpretations: list[str], scope: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:synthesis-write":
            raise PermissionError("knowledge:synthesis-write required")
        states = {str(claim_id): self.ledger.inspect(claim_id)["status"] for claim_id in input_claim_ids}
        inputs_digest = _digest({"claims": input_claim_ids, "states": states})
        synthesis_id = _urn("synthesis", _digest({"text":text,"inputs":inputs_digest,"interpretations":interpretations,"scope":scope}))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_syntheses(synthesis_id,text,input_claim_ids_json,interpretations_json,claim_states_json,scope_json,inputs_digest,actor) VALUES(?,?,?,?,?,?,?,?)", (synthesis_id,text,_json(input_claim_ids),_json(interpretations),_json(states),_json(scope),inputs_digest,actor))
        result = _row(self.db.execute("SELECT * FROM knowledge_syntheses WHERE synthesis_id=?", (synthesis_id,)).fetchone()) or {}
        result["claim_states"] = json.loads(result["claim_states_json"])
        return result

    # ---------- publication / projections / retrieval ----------
    def _revision_payload(self, revision_id: str) -> dict[str, Any]:
        revision = self.db.execute("SELECT r.*,c.concept_type,c.concept_lifecycle,c.scope_json FROM knowledge_concept_revisions r JOIN knowledge_concepts c ON c.concept_id=r.concept_id WHERE r.revision_id=?", (revision_id,)).fetchone()
        if revision is None:
            raise ValueError("revision not found")
        payload = dict(revision)
        payload["claim_ids"] = json.loads(payload.pop("claim_ids_json"))
        payload["relationship_ids"] = json.loads(payload.pop("relationship_ids_json"))
        payload["scope"] = json.loads(payload.pop("scope_json"))
        return payload

    def render_snapshot_bytes(self, revision_ids: list[str]) -> bytes:
        records: list[dict[str, Any]] = []
        for revision_id in sorted(revision_ids):
            revision = self._revision_payload(revision_id)
            if revision["concept_lifecycle"] not in {"validated","canonical"}:
                raise ValueError("only validated/canonical revisions can publish")
            claims = []
            for claim_id in revision["claim_ids"]:
                inspected = self.ledger.inspect(int(claim_id))
                claims.append({"id": claim_id, "statement": inspected["statement"], "status": inspected["status"]})
            records.append({
                "revision_id": revision_id,
                "concept_id": revision["concept_id"],
                "title": revision["title"],
                "description": revision["description"],
                "concept_type": revision["concept_type"],
                "okf_path": revision["okf_path"],
                "claims": claims,
            })
        return (_json({"contract":"erasmus.okf-snapshot-render/v1","revisions":records}) + "\n").encode("utf-8")

    def publish_snapshot(self, channel_id: str, revision_ids: list[str], actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:publish" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:publish required")
        channel = self.db.execute("SELECT * FROM knowledge_publication_channels WHERE channel_id=? AND state='active'", (channel_id,)).fetchone()
        if channel is None:
            if channel_id == "public":
                return self._publish_missing_channel_error(channel_id)
            raise ValueError("active publication channel not found")
        rendered = self.render_snapshot_bytes(revision_ids)
        manifest_digest = hashlib.sha256(rendered).hexdigest()
        existing = self.db.execute("SELECT * FROM knowledge_snapshots WHERE channel_id=? AND manifest_digest=? AND snapshot_state='published'", (channel_id, manifest_digest)).fetchone()
        if existing:
            return dict(existing)
        sequence = self.db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM knowledge_snapshots WHERE channel_id=?", (channel_id,)).fetchone()[0]
        snapshot_id = _urn("snapshot", f"{channel_id}:{sequence}:{manifest_digest}")
        target = (self.snapshots_root / channel_id / f"{sequence:08d}-{manifest_digest[:12]}").resolve()
        if not target.is_relative_to(self.snapshots_root):
            raise ValueError("snapshot path escaped root")
        staging = target.with_name(target.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            (staging / "snapshot.json").write_bytes(rendered)
            manifest = {"snapshot_id":snapshot_id,"channel_id":channel_id,"sequence":sequence,"revision_ids":sorted(revision_ids),"manifest_digest":manifest_digest}
            (staging / "manifest.json").write_text(_json(manifest)+"\n", encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(target)
            with self.db:
                self.db.execute("INSERT INTO knowledge_snapshots(snapshot_id,channel_id,sequence,revision_ids_json,root_path,manifest_digest,snapshot_state,actor) VALUES(?,?,?,?,?,?,?,?)", (snapshot_id,channel_id,sequence,_json(sorted(revision_ids)),str(target),manifest_digest,"published",actor))
                self.db.execute("UPDATE knowledge_publication_channels SET current_snapshot_id=? WHERE channel_id=?", (snapshot_id,channel_id))
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if target.exists() and self.db.execute("SELECT 1 FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone() is None:
                shutil.rmtree(target, ignore_errors=True)
            raise
        return _row(self.db.execute("SELECT * FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()) or {}

    def _publish_missing_channel_error(self, channel_id: str) -> dict[str, Any]:
        raise ValueError(f"active publication channel not found: {channel_id}")

    def current_snapshot(self, channel_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT s.* FROM knowledge_publication_channels c JOIN knowledge_snapshots s ON s.snapshot_id=c.current_snapshot_id WHERE c.channel_id=?", (channel_id,)).fetchone()
        return _row(row)

    def build_fts_projection(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.db.execute("SELECT * FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'", (snapshot_id,)).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        revision_ids = json.loads(snapshot["revision_ids_json"])
        with self.db:
            self.db.execute("DELETE FROM knowledge_fts WHERE snapshot_id=?", (snapshot_id,))
            self.db.execute("DELETE FROM knowledge_fts_documents WHERE snapshot_id=?", (snapshot_id,))
            for revision_id in revision_ids:
                revision = self._revision_payload(revision_id)
                for claim_id in revision["claim_ids"]:
                    claim = self.ledger.inspect(int(claim_id))
                    row = (snapshot_id, revision_id, revision["concept_id"], str(claim_id), revision["title"], f"{revision['description']}\n{claim['statement']}")
                    self.db.execute("INSERT INTO knowledge_fts_documents(snapshot_id,revision_id,concept_id,claim_id,title,body) VALUES(?,?,?,?,?,?)", row)
                    self.db.execute("INSERT INTO knowledge_fts(snapshot_id,revision_id,concept_id,claim_id,title,body) VALUES(?,?,?,?,?,?)", row)
        artifact_digest = _digest([dict(r) for r in self.db.execute("SELECT * FROM knowledge_fts_documents WHERE snapshot_id=? ORDER BY revision_id,claim_id", (snapshot_id,)).fetchall()])
        projection_id = _urn("projection", _digest({"kind":"fts","snapshot":snapshot_id,"artifact":artifact_digest}))
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)", (projection_id,"fts",snapshot_id,"ready",_json({"engine":"sqlite-fts5"}),artifact_digest))
        return _row(self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,)).fetchone()) or {}

    def add_serving_directive(self, action: str, target_type: str, target_id: str, channel_id: str | None, reason: str, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:serve-control":
            raise PermissionError("knowledge:serve-control required")
        directive_id = _urn("serving-directive", _digest({"action":action,"target_type":target_type,"target_id":target_id,"channel":channel_id,"reason":reason,"nonce":self.db.execute("SELECT COUNT(*) FROM knowledge_serving_directives").fetchone()[0]}))
        with self.db:
            self.db.execute("INSERT INTO knowledge_serving_directives(directive_id,action,target_type,target_id,channel_id,reason,actor) VALUES(?,?,?,?,?,?,?)", (directive_id,action,target_type,target_id,channel_id,reason,actor))
        return _row(self.db.execute("SELECT * FROM knowledge_serving_directives WHERE directive_id=?", (directive_id,)).fetchone()) or {}

    def retrieve(self, query: str, channel_id: str, limit: int, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:read":
            raise PermissionError("knowledge:read required")
        snapshot = self.current_snapshot(channel_id)
        if snapshot is None:
            raise ValueError("channel has no current snapshot")
        projection = self.db.execute("SELECT 1 FROM knowledge_projection_manifests WHERE source_snapshot_id=? AND kind='fts' AND projection_state='ready'", (snapshot["snapshot_id"],)).fetchone()
        if projection is None:
            raise ValueError("ready FTS projection required")
        terms = " ".join(part for part in query.split() if part.strip())
        rows = self.db.execute("SELECT snapshot_id,revision_id,concept_id,claim_id,title,body,bm25(knowledge_fts) rank FROM knowledge_fts WHERE knowledge_fts MATCH ? AND snapshot_id=? ORDER BY rank LIMIT ?", (terms, snapshot["snapshot_id"], max(limit * 4, limit))).fetchall()
        items: list[dict[str, Any]] = []
        omitted = 0
        reasons: list[str] = []
        for result in rows:
            excluded = self.db.execute("SELECT reason FROM knowledge_serving_directives WHERE active=1 AND action IN ('exclude','block') AND target_type='claim' AND target_id=? AND (channel_id IS NULL OR channel_id=?) LIMIT 1", (result["claim_id"], channel_id)).fetchone()
            if excluded:
                omitted += 1
                reasons.append(excluded["reason"])
                continue
            inspected = self.ledger.inspect(int(result["claim_id"]))
            items.append({
                "claim_id": result["claim_id"],
                "proposition_id": int(result["claim_id"]),
                "concept_id": result["concept_id"],
                "concept_path": self._revision_payload(result["revision_id"])["okf_path"],
                "selected_text": result["body"],
                "epistemic_status": inspected["status"],
                "source_refs": [e["id"] for e in inspected["evidence"]],
                "retrieval_features": {"lexical": True, "rank": result["rank"]},
            })
            if len(items) >= limit:
                break
        packet_core = {"snapshot_id":snapshot["snapshot_id"],"channel_id":channel_id,"query":query,"items":items,"budget":{"used":len(items),"limit":limit},"omitted":{"count":omitted,"reasons":sorted(set(reasons))}}
        packet_id = _urn("evidence-packet", _digest(packet_core))
        receipt_id = _urn("use-receipt", _digest({"packet":packet_id,"actor":actor}))
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO knowledge_use_receipts(receipt_id,packet_id,channel_id,snapshot_id,item_ids_json,actor) VALUES(?,?,?,?,?,?)", (receipt_id,packet_id,channel_id,snapshot["snapshot_id"],_json([i["claim_id"] for i in items]),actor))
        return {"contract":"erasmus.evidence-packet/v1","packet_id":packet_id,**packet_core}

    def get_use_receipt(self, packet_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM knowledge_use_receipts WHERE packet_id=?", (packet_id,)).fetchone()
        if row is None:
            raise ValueError("use receipt not found")
        result = dict(row)
        result["packet_id"] = packet_id
        return result

    def authoritative_digest(self) -> str:
        tables = [
            "knowledge_policy_sets","knowledge_semantic_registry","knowledge_sources","knowledge_source_spans",
            "knowledge_candidates","knowledge_candidate_claims","knowledge_entities","knowledge_entity_aliases",
            "knowledge_identity_decisions","knowledge_reconciliation_decisions","knowledge_claim_bindings",
            "knowledge_concepts","knowledge_concept_revisions","knowledge_relationships","knowledge_reviews",
            "knowledge_questions","knowledge_syntheses","knowledge_snapshots","knowledge_serving_directives",
            "knowledge_invalidation_events",
        ]
        payload: dict[str, Any] = {}
        for table in tables:
            payload[table] = [dict(row) for row in self.db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()]
        return _digest(payload)

    def run_maintenance(self, actor: str, authority: str) -> dict[str, Any]:
        if authority != "knowledge:maintain":
            raise PermissionError("knowledge:maintain required")
        stale = [dict(row) for row in self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_state='stale'").fetchall()]
        return {"contract":"erasmus.knowledge-maintenance/v1","status":"completed","actor":actor,"stale_projections":stale,"authoritative_mutations":0}

    def status(self) -> dict[str, Any]:
        version = self.db.execute("SELECT COALESCE(MAX(version),0) FROM schema_version").fetchone()[0]
        return {
            "contract":"erasmus.knowledge-status/v1",
            "schema_version":version,
            "active_policy":_row(self.db.execute("SELECT policy_set_id,digest,state FROM knowledge_policy_sets WHERE state='active' LIMIT 1").fetchone()),
            "sources":self.db.execute("SELECT COUNT(*) FROM knowledge_sources WHERE tombstoned=0").fetchone()[0],
            "candidates":self.db.execute("SELECT COUNT(*) FROM knowledge_candidates").fetchone()[0],
            "concepts":self.db.execute("SELECT COUNT(*) FROM knowledge_concepts").fetchone()[0],
            "snapshots":self.db.execute("SELECT COUNT(*) FROM knowledge_snapshots").fetchone()[0],
        }
