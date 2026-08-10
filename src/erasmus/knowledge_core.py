from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

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
    """Governed deterministic Phase 3 core.

    Every ordinary Phase 3 read or mutation is policy-gated. Policy and registry
    administration remain explicit bootstrap authorities. Proposition truth-state
    is delegated exclusively to :class:`EpistemicLedger`.
    """

    DEFAULT_SCOPE = {
        "visibility": "private",
        "tenant": "local",
        "project": None,
        "domain": None,
        "labels": [],
    }

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

    # ------------------------------------------------------------------
    # Policy, registry, channels, audit
    # ------------------------------------------------------------------
    def _ensure_private_channel(self) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_publication_channels(channel_id,scope_json,audience) VALUES('private',?,'private')",
                (_json(self.DEFAULT_SCOPE),),
            )

    def register_policy_set(
        self,
        policy_set_id: str,
        rules: list[dict[str, Any]],
        actor: str,
        authority: str,
    ) -> str:
        if authority != "knowledge:policy-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:policy-admin required")
        if not policy_set_id or not isinstance(rules, list) or not rules:
            raise ValueError("policy set id and rules are required")
        for rule in rules:
            if (
                rule.get("effect") not in {"permit", "deny"}
                or not rule.get("operation")
                or not rule.get("actor")
            ):
                raise ValueError("invalid policy rule")
        digest = _digest({"policy_set_id": policy_set_id, "rules": rules})
        with self.db:
            existing = self.db.execute(
                "SELECT digest FROM knowledge_policy_sets WHERE policy_set_id=?",
                (policy_set_id,),
            ).fetchone()
            if existing and existing["digest"] != digest:
                raise ValueError("policy set id already identifies different content")
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_policy_sets(policy_set_id,digest,rules_json,actor) VALUES(?,?,?,?)",
                (policy_set_id, digest, _json(rules), actor),
            )
        return digest

    def activate_policy_set(
        self,
        policy_set_id: str,
        digest: str,
        actor: str,
        authority: str,
    ) -> None:
        if authority != "knowledge:policy-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:policy-admin required")
        row = self.db.execute(
            "SELECT digest FROM knowledge_policy_sets WHERE policy_set_id=?",
            (policy_set_id,),
        ).fetchone()
        if row is None or row["digest"] != digest:
            raise ValueError("exact policy digest required")
        with self.db:
            self.db.execute(
                "UPDATE knowledge_policy_sets SET state='inactive' WHERE state='active'"
            )
            self.db.execute(
                "UPDATE knowledge_policy_sets SET state='active' WHERE policy_set_id=? AND digest=?",
                (policy_set_id, digest),
            )

    def evaluate_policy(
        self,
        operation: str,
        actor: str,
        scope: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        active = self.db.execute(
            "SELECT * FROM knowledge_policy_sets WHERE state='active' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        matched: list[dict[str, Any]] = []
        decision = "deny"
        policy_id = policy_digest = None
        if active:
            policy_id, policy_digest = active["policy_set_id"], active["digest"]
            rules = json.loads(active["rules_json"])
            matched = [
                rule
                for rule in rules
                if fnmatch.fnmatchcase(operation, rule["operation"])
                and fnmatch.fnmatchcase(actor, rule["actor"])
            ]
            if (
                matched
                and any(rule["effect"] == "permit" for rule in matched)
                and not any(rule["effect"] == "deny" for rule in matched)
            ):
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
                (
                    receipt_id,
                    policy_id,
                    policy_digest,
                    operation,
                    actor,
                    _json(scope),
                    decision,
                    _json(matched),
                    int(bool(dry_run)),
                ),
            )
        return {"receipt_id": receipt_id, **payload}

    def _gate(
        self,
        operation: str,
        actor: str,
        scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        receipt = self.evaluate_policy(operation, actor, scope or self.DEFAULT_SCOPE)
        if receipt["decision"] != "permit":
            raise PermissionError(f"active policy denied {operation}")
        return receipt

    def _audit(
        self,
        *,
        operation: str,
        target_type: str,
        target_id: str,
        actor: str,
        authority: str,
        policy_receipt_id: str,
        scope: dict[str, Any],
        result: str = "accepted",
        mission_id: int | None = None,
        idempotency_key: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        audit_id = _urn(
            "mutation-audit",
            _digest(
                {
                    "operation": operation,
                    "target_type": target_type,
                    "target_id": target_id,
                    "actor": actor,
                    "authority": authority,
                    "mission_id": mission_id,
                    "idempotency_key": idempotency_key,
                    "receipt": policy_receipt_id,
                    "result": result,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_mutation_audit(audit_id,operation,target_type,target_id,actor,authority,mission_id,idempotency_key,policy_receipt_id,scope_json,result,detail_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id,
                    operation,
                    target_type,
                    target_id,
                    actor,
                    authority,
                    mission_id,
                    idempotency_key,
                    policy_receipt_id,
                    _json(scope),
                    result,
                    _json(detail or {}),
                ),
            )

    def register_semantic_registry(
        self,
        registry_id: str,
        definitions: dict[str, Any],
        actor: str,
        authority: str,
    ) -> str:
        if authority != "knowledge:registry-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:registry-admin required")
        digest = _digest({"registry_id": registry_id, "definitions": definitions})
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_semantic_registry(registry_id,digest,definitions_json,actor) VALUES(?,?,?,?)",
                (registry_id, digest, _json(definitions), actor),
            )
        return digest

    def ensure_channel(
        self,
        channel_id: str,
        scope: dict[str, Any],
        audience: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:channel-admin", actor, scope)
        if authority != "knowledge:channel-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:channel-admin required")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_publication_channels(channel_id,scope_json,audience) VALUES(?,?,?)",
                (channel_id, _json(scope), audience),
            )
        self._audit(
            operation="knowledge:channel-admin",
            target_type="channel",
            target_id=channel_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_publication_channels WHERE channel_id=?",
                (channel_id,),
            ).fetchone()
        )

    # ------------------------------------------------------------------
    # Sources, spans, candidates, admission, claims
    # ------------------------------------------------------------------
    def register_source_bytes(
        self,
        data: bytes,
        locator: str,
        media_type: str,
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:source-register", actor, scope)
        if authority != "knowledge:source-register":
            raise PermissionError("knowledge:source-register required")
        if not isinstance(data, bytes) or not locator or not media_type:
            raise ValueError("source bytes, locator and media type are required")
        digest = hashlib.sha256(data).hexdigest()
        source_id = _urn("source", digest)
        existing = self.db.execute(
            "SELECT * FROM knowledge_sources WHERE source_id=?", (source_id,)
        ).fetchone()
        if existing and existing["scope_json"] != _json(scope):
            raise ValueError("source digest is already registered in a different scope")
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
                "INSERT OR IGNORE INTO knowledge_sources(source_id,digest,locator,media_type,byte_size,scope_json,storage_path,actor,authority,idempotency_key,policy_receipt_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    source_id,
                    digest,
                    locator,
                    media_type,
                    len(data),
                    _json(scope),
                    str(target),
                    actor,
                    authority,
                    source_id,
                    receipt["receipt_id"],
                ),
            )
        self._audit(
            operation="knowledge:source-register",
            target_type="source",
            target_id=source_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            idempotency_key=source_id,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_sources WHERE source_id=?", (source_id,)
            ).fetchone()
        )

    def register_source_span(
        self,
        source_id: str,
        coordinate: dict[str, Any],
        extracted_text: str,
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:source-register", actor, scope)
        if authority != "knowledge:source-register":
            raise PermissionError("knowledge:source-register required")
        source = self.db.execute(
            "SELECT * FROM knowledge_sources WHERE source_id=? AND tombstoned=0",
            (source_id,),
        ).fetchone()
        if source is None:
            raise ValueError("source not found")
        if source["scope_json"] != _json(scope):
            raise ValueError("source span scope must match source scope")
        text_digest = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
        span_id = _urn(
            "span",
            _digest(
                {
                    "source_id": source_id,
                    "coordinate": coordinate,
                    "text_digest": text_digest,
                }
            ),
        )
        existing = self.db.execute(
            "SELECT scope_json FROM knowledge_source_spans WHERE span_id=?", (span_id,)
        ).fetchone()
        if existing and existing["scope_json"] != _json(scope):
            raise ValueError("source span is already registered in a different scope")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_source_spans(span_id,source_id,coordinate_json,text_digest,extracted_text,scope_json,actor) VALUES(?,?,?,?,?,?,?)",
                (
                    span_id,
                    source_id,
                    _json(coordinate),
                    text_digest,
                    extracted_text,
                    _json(scope),
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:source-register",
            target_type="source-span",
            target_id=span_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            idempotency_key=span_id,
        )
        result = dict(
            self.db.execute(
                "SELECT * FROM knowledge_source_spans WHERE span_id=?", (span_id,)
            ).fetchone()
        )
        result["coordinate"] = json.loads(result.pop("coordinate_json"))
        result["scope"] = json.loads(result.pop("scope_json"))
        return result

    def get_source_span(self, span_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM knowledge_source_spans WHERE span_id=?", (span_id,)
        ).fetchone()
        if row is None:
            raise ValueError("source span not found")
        return dict(row)

    def import_candidate(
        self,
        producer: str,
        title: str,
        body: str,
        source_ids: list[str],
        source_span_ids: list[str],
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:candidate-import", actor, scope)
        if authority != "knowledge:candidate-import":
            raise PermissionError("knowledge:candidate-import required")
        if not producer or not title or not body or not source_ids:
            raise ValueError("producer, title, body and source ids are required")
        scope_json = _json(scope)
        for source_id in source_ids:
            row = self.db.execute(
                "SELECT scope_json FROM knowledge_sources WHERE source_id=? AND tombstoned=0",
                (source_id,),
            ).fetchone()
            if row is None or row["scope_json"] != scope_json:
                raise ValueError(f"missing or cross-scope source: {source_id}")
        for span_id in source_span_ids:
            row = self.db.execute(
                "SELECT scope_json FROM knowledge_source_spans WHERE span_id=?", (span_id,)
            ).fetchone()
            if row is None or row["scope_json"] != scope_json:
                raise ValueError(f"missing or cross-scope source span: {span_id}")
        content = {
            "producer": producer,
            "title": title,
            "body": body,
            "source_ids": sorted(source_ids),
            "source_span_ids": sorted(source_span_ids),
            "scope": scope,
        }
        content_digest = _digest(content)
        candidate_id = _urn("candidate", content_digest)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_candidates(candidate_id,producer,title,body,source_ids_json,source_span_ids_json,scope_json,candidate_disposition,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    candidate_id,
                    producer,
                    title,
                    body,
                    _json(sorted(source_ids)),
                    _json(sorted(source_span_ids)),
                    scope_json,
                    "quarantined",
                    content_digest,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:candidate-import",
            target_type="candidate",
            target_id=candidate_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            idempotency_key=candidate_id,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        )

    def admit_candidate(
        self,
        candidate_id: str,
        actor: str,
        authority: str,
        mission_id: int,
        idempotency_key: str,
        reason: str = "deterministic admission gates passed",
    ) -> dict[str, Any]:
        candidate = self.db.execute(
            "SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        if candidate is None:
            raise ValueError("candidate not found")
        scope = json.loads(candidate["scope_json"])
        receipt = self._gate("knowledge:candidate-admit", actor, scope)
        if authority != "knowledge:candidate-admit" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:candidate-admit required")
        prior = self.db.execute(
            "SELECT candidate_id,to_disposition FROM knowledge_candidate_transitions WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if prior:
            if prior["candidate_id"] != candidate_id:
                raise ValueError("admission idempotency key already belongs to another candidate")
            return dict(
                self.db.execute(
                    "SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)
                ).fetchone()
            )
        if candidate["candidate_disposition"] != "quarantined":
            raise ValueError("only quarantined candidates can be admitted")
        source_ids = json.loads(candidate["source_ids_json"])
        span_ids = json.loads(candidate["source_span_ids_json"])
        for source_id in source_ids:
            source = self.db.execute(
                "SELECT scope_json,tombstoned FROM knowledge_sources WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if source is None or source["tombstoned"] or source["scope_json"] != candidate["scope_json"]:
                raise ValueError("candidate source is unavailable or scope-incompatible")
        for span_id in span_ids:
            span = self.db.execute(
                "SELECT scope_json FROM knowledge_source_spans WHERE span_id=?", (span_id,)
            ).fetchone()
            if span is None or span["scope_json"] != candidate["scope_json"]:
                raise ValueError("candidate source span is unavailable or scope-incompatible")
        transition_id = _urn(
            "candidate-transition",
            _digest(
                {
                    "candidate": candidate_id,
                    "from": "quarantined",
                    "to": "admissible",
                    "mission": mission_id,
                    "key": idempotency_key,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_candidate_transitions(transition_id,candidate_id,from_disposition,to_disposition,mission_id,idempotency_key,actor,authority,policy_receipt_id,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    transition_id,
                    candidate_id,
                    "quarantined",
                    "admissible",
                    mission_id,
                    idempotency_key,
                    actor,
                    authority,
                    receipt["receipt_id"],
                    reason,
                ),
            )
            self.db.execute(
                "UPDATE knowledge_candidates SET candidate_disposition='admissible' WHERE candidate_id=?",
                (candidate_id,),
            )
        self._audit(
            operation="knowledge:candidate-admit",
            target_type="candidate",
            target_id=candidate_id,
            actor=actor,
            authority=authority,
            mission_id=mission_id,
            idempotency_key=idempotency_key,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        )

    def add_candidate_claim(
        self,
        candidate_id: str,
        statement: str,
        source_span_ids: list[str],
        qualifiers: dict[str, Any],
        scope: dict[str, Any],
        risk_class: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:claim-decompose", actor, scope)
        if authority != "knowledge:claim-decompose":
            raise PermissionError("knowledge:claim-decompose required")
        if not statement.strip() or not source_span_ids:
            raise ValueError("candidate claims require a statement and source spans")
        if risk_class not in {"routine", "consequential", "protected"}:
            raise ValueError("invalid risk class")
        candidate = self.db.execute(
            "SELECT * FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        if candidate is None or candidate["scope_json"] != _json(scope):
            raise ValueError("candidate not found or scope mismatch")
        for span_id in source_span_ids:
            span = self.db.execute(
                "SELECT scope_json FROM knowledge_source_spans WHERE span_id=?", (span_id,)
            ).fetchone()
            if span is None or span["scope_json"] != candidate["scope_json"]:
                raise ValueError("source span not found or scope mismatch")
        content_digest = _digest(
            {
                "candidate_id": candidate_id,
                "statement": statement.strip(),
                "spans": sorted(source_span_ids),
                "qualifiers": qualifiers,
                "scope": scope,
                "risk": risk_class,
            }
        )
        claim_id = _urn("candidate-claim", content_digest)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_candidate_claims(candidate_claim_id,candidate_id,statement,source_span_ids_json,qualifiers_json,scope_json,risk_class,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    claim_id,
                    candidate_id,
                    statement.strip(),
                    _json(sorted(source_span_ids)),
                    _json(qualifiers),
                    _json(scope),
                    risk_class,
                    content_digest,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:claim-decompose",
            target_type="candidate-claim",
            target_id=claim_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            idempotency_key=claim_id,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?",
                (claim_id,),
            ).fetchone()
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def create_entity(
        self,
        entity_type: str,
        canonical_name: str,
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:identity-write", actor, scope)
        if authority != "knowledge:identity-write":
            raise PermissionError("knowledge:identity-write required")
        if not entity_type or not canonical_name.strip():
            raise ValueError("entity type and canonical name required")
        entity_id = _urn(
            "entity",
            _digest(
                {
                    "type": entity_type,
                    "name": canonical_name,
                    "scope": scope,
                    "ordinal": self.db.execute(
                        "SELECT COUNT(*) FROM knowledge_entities"
                    ).fetchone()[0],
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_entities(entity_id,entity_type,canonical_name,scope_json,actor) VALUES(?,?,?,?,?)",
                (entity_id, entity_type, canonical_name, _json(scope), actor),
            )
        self._audit(
            operation="knowledge:identity-write",
            target_type="entity",
            target_id=entity_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_entities WHERE entity_id=?", (entity_id,)
            ).fetchone()
        )

    def add_entity_alias(
        self,
        entity_id: str,
        alias: str,
        namespace: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        entity = self.db.execute(
            "SELECT * FROM knowledge_entities WHERE entity_id=?", (entity_id,)
        ).fetchone()
        if entity is None:
            raise ValueError("entity not found")
        scope = json.loads(entity["scope_json"])
        receipt = self._gate("knowledge:identity-write", actor, scope)
        if authority != "knowledge:identity-write":
            raise PermissionError("knowledge:identity-write required")
        alias_id = _urn(
            "entity-alias",
            _digest({"entity": entity_id, "alias": alias, "namespace": namespace}),
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_entity_aliases(alias_id,entity_id,alias,namespace,actor) VALUES(?,?,?,?,?)",
                (alias_id, entity_id, alias, namespace, actor),
            )
        self._audit(
            operation="knowledge:identity-write",
            target_type="entity-alias",
            target_id=alias_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_entity_aliases WHERE alias_id=?", (alias_id,)
            ).fetchone()
        )

    def resolve_entity_exact(
        self, value: str, scope: dict[str, Any]
    ) -> dict[str, Any]:
        scope_json = _json(scope)
        rows = self.db.execute(
            """
            SELECT entity_id FROM knowledge_entities
            WHERE canonical_name=? AND scope_json=? AND retired=0
            UNION
            SELECT a.entity_id FROM knowledge_entity_aliases a
            JOIN knowledge_entities e ON e.entity_id=a.entity_id
            WHERE a.alias=? AND e.scope_json=? AND e.retired=0
            """,
            (value, scope_json, value, scope_json),
        ).fetchall()
        ids = sorted({row[0] for row in rows})
        return {"query": value, "entity_ids": ids, "ambiguous": len(ids) != 1}

    def record_identity_decision(
        self,
        left_entity_id: str,
        right_entity_id: str,
        decision: str,
        actor: str,
        authority: str,
        rationale: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:identity-decide", actor)
        if authority != "knowledge:identity-decide" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:identity-decide required")
        if decision not in {
            "same_entity",
            "distinct_entity",
            "alias_of",
            "successor_of",
            "version_of",
            "part_of",
            "unresolved",
        }:
            raise ValueError("invalid identity decision")
        for entity_id in (left_entity_id, right_entity_id):
            if self.db.execute(
                "SELECT 1 FROM knowledge_entities WHERE entity_id=?", (entity_id,)
            ).fetchone() is None:
                raise ValueError("entity not found")
        decision_id = _urn(
            "identity-decision",
            _digest(
                {
                    "left": left_entity_id,
                    "right": right_entity_id,
                    "decision": decision,
                    "rationale": rationale,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_identity_decisions(decision_id,left_entity_id,right_entity_id,decision,rationale,actor) VALUES(?,?,?,?,?,?)",
                (
                    decision_id,
                    left_entity_id,
                    right_entity_id,
                    decision,
                    rationale,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:identity-decide",
            target_type="identity-decision",
            target_id=decision_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=self.DEFAULT_SCOPE,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_identity_decisions WHERE decision_id=?",
                (decision_id,),
            ).fetchone()
        )

    # ------------------------------------------------------------------
    # Comparison and reconciliation
    # ------------------------------------------------------------------
    def compare_claim(
        self, candidate_claim_id: str, limit: int = 10
    ) -> dict[str, Any]:
        claim = self.db.execute(
            "SELECT * FROM knowledge_candidate_claims WHERE candidate_claim_id=?",
            (candidate_claim_id,),
        ).fetchone()
        if claim is None:
            raise ValueError("candidate claim not found")
        rows = self.db.execute(
            """
            SELECT p.id,p.statement,COALESCE(t.new_status,p.status) status
            FROM propositions p
            LEFT JOIN proposition_transitions t ON t.id=(
                SELECT id FROM proposition_transitions
                WHERE proposition_id=p.id ORDER BY id DESC LIMIT 1
            )
            WHERE lower(p.statement)=lower(?) ORDER BY p.id LIMIT ?
            """,
            (claim["statement"], limit),
        ).fetchall()
        return {
            "candidate_claim_id": candidate_claim_id,
            "targets": [
                {
                    "proposition_id": row["id"],
                    "statement": row["statement"],
                    "status": row["status"],
                    "reason": "exact_statement",
                }
                for row in rows
            ],
            "budget": {"limit": limit, "used": len(rows)},
        }

    def _admissible_claim(self, candidate_claim_id: str) -> Any:
        claim = self.db.execute(
            """
            SELECT cc.*,c.candidate_disposition,c.scope_json AS candidate_scope_json
            FROM knowledge_candidate_claims cc
            JOIN knowledge_candidates c ON c.candidate_id=cc.candidate_id
            WHERE cc.candidate_claim_id=?
            """,
            (candidate_claim_id,),
        ).fetchone()
        if claim is None:
            raise ValueError("candidate claim not found")
        if claim["candidate_disposition"] != "admissible":
            raise ValueError("candidate must be admissible before reconciliation")
        return claim

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
        claim = self._admissible_claim(candidate_claim_id)
        scope = json.loads(claim["candidate_scope_json"])
        receipt = self._gate("knowledge:reconcile", actor, scope)
        if authority != "knowledge:reconcile" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:reconcile required")
        prior = self.db.execute(
            "SELECT result_json,decision_id FROM knowledge_reconciliation_decisions WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if prior:
            result = json.loads(prior["result_json"])
            return {"decision_id": prior["decision_id"], **result}
        targets = target_proposition_ids or []
        if action in {"amend", "supersede"}:
            raise ValueError(
                f"{action} requires the complete KnowledgeSystem replacement transaction"
            )
        if action not in {
            "create",
            "corroborate",
            "contradict",
            "duplicate",
            "reject",
            "insufficient_evidence",
        }:
            raise ValueError("invalid reconciliation action")
        proposition_id: int | None = None
        if action == "create":
            if self.compare_claim(candidate_claim_id)["targets"]:
                raise ValueError("exact duplicate cannot create proposition")
            evidence_id = self.ledger.add_evidence(
                "evidence",
                claim["statement"],
                "document",
                {
                    "candidate_claim_id": candidate_claim_id,
                    "source_span_ids": json.loads(claim["source_span_ids_json"]),
                },
                "contextual",
                date.today().isoformat(),
                "global",
                actor,
                "ledger:write",
            )
            proposition_id = self.ledger.propose(
                claim["statement"],
                evidence_id,
                actor,
                "ledger:write",
                scope="global",
                status="speculative",
                reason="Phase 3 governed reconciliation",
            )
        elif action in {"corroborate", "contradict"}:
            if len(targets) != 1:
                raise ValueError(f"{action} requires exactly one target proposition")
            target_id = targets[0]
            if action == "corroborate":
                evidence_id = self.ledger.add_evidence(
                    "evidence",
                    claim["statement"],
                    "document",
                    {"candidate_claim_id": candidate_claim_id},
                    "contextual",
                    date.today().isoformat(),
                    "global",
                    actor,
                    "ledger:write",
                )
                target = self.ledger.inspect(target_id)
                next_status = {
                    "speculative": "plausible",
                    "analogy": "plausible",
                    "leap": "plausible",
                    "unresolved": "plausible",
                    "plausible": "supported",
                    "contradicted": "supported",
                    "supported": "established",
                }.get(target["status"])
                if next_status is None:
                    raise ValueError("target cannot be corroborated further")
                self.ledger.transition(
                    target_id,
                    "support",
                    evidence_id,
                    actor,
                    "ledger:write",
                    "Phase 3 corroboration",
                    target_status=next_status,
                )
            else:
                evidence_id = self.ledger.add_evidence(
                    "contradiction",
                    claim["statement"],
                    "document",
                    {"candidate_claim_id": candidate_claim_id},
                    "contextual",
                    date.today().isoformat(),
                    "global",
                    actor,
                    "ledger:write",
                )
                self.ledger.transition(
                    target_id,
                    "contradict",
                    evidence_id,
                    actor,
                    "ledger:write",
                    "Phase 3 contradiction",
                )
            proposition_id = target_id
        result = {
            "action": action,
            "candidate_claim_id": candidate_claim_id,
            "proposition_id": proposition_id,
            "target_proposition_ids": targets,
        }
        decision_id = _urn(
            "reconciliation-decision",
            _digest(
                {
                    "claim": candidate_claim_id,
                    "action": action,
                    "mission": mission_id,
                    "key": idempotency_key,
                    "targets": targets,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_reconciliation_decisions(decision_id,candidate_claim_id,action,target_proposition_ids_json,mission_id,idempotency_key,actor,authority,result_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    decision_id,
                    candidate_claim_id,
                    action,
                    _json(targets),
                    mission_id,
                    idempotency_key,
                    actor,
                    authority,
                    _json(result),
                ),
            )
            if proposition_id is not None:
                binding_id = _urn(
                    "claim-binding",
                    _digest(
                        {
                            "claim": candidate_claim_id,
                            "proposition": proposition_id,
                            "decision": decision_id,
                        }
                    ),
                )
                self.db.execute(
                    "INSERT INTO knowledge_claim_bindings(binding_id,candidate_claim_id,proposition_id,relation,decision_id) VALUES(?,?,?,?,?)",
                    (
                        binding_id,
                        candidate_claim_id,
                        proposition_id,
                        action,
                        decision_id,
                    ),
                )
        self._audit(
            operation="knowledge:reconcile",
            target_type="reconciliation-decision",
            target_id=decision_id,
            actor=actor,
            authority=authority,
            mission_id=mission_id,
            idempotency_key=idempotency_key,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            detail=result,
        )
        return {"decision_id": decision_id, **result}

    # ------------------------------------------------------------------
    # Concepts, revisions, reviews, questions, synthesis
    # ------------------------------------------------------------------
    def create_concept(
        self,
        title: str,
        concept_type: str,
        claim_ids: list[int],
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:concept-write", actor, scope)
        if authority != "knowledge:concept-write":
            raise PermissionError("knowledge:concept-write required")
        for claim_id in claim_ids:
            self.ledger.inspect(claim_id)
        concept_id = _urn(
            "concept",
            _digest(
                {
                    "title": title,
                    "type": concept_type,
                    "scope": scope,
                    "ordinal": self.db.execute(
                        "SELECT COUNT(*) FROM knowledge_concepts"
                    ).fetchone()[0],
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_concepts(concept_id,concept_type,scope_json,actor) VALUES(?,?,?,?)",
                (concept_id, concept_type, _json(scope), actor),
            )
        self._audit(
            operation="knowledge:concept-write",
            target_type="concept",
            target_id=concept_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)
            ).fetchone()
        )

    def create_concept_revision(
        self,
        concept_id: str,
        title: str,
        description: str,
        claim_ids: list[int],
        relationship_ids: list[str],
        okf_path: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        concept = self.db.execute(
            "SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)
        ).fetchone()
        if concept is None:
            raise ValueError("concept not found")
        scope = json.loads(concept["scope_json"])
        receipt = self._gate("knowledge:concept-write", actor, scope)
        if authority != "knowledge:concept-write":
            raise PermissionError("knowledge:concept-write required")
        if not okf_path or okf_path.startswith("/") or ".." in Path(okf_path).parts:
            raise ValueError("invalid OKF path")
        for claim_id in claim_ids:
            self.ledger.inspect(claim_id)
        revision_number = self.db.execute(
            "SELECT COALESCE(MAX(revision_number),0)+1 FROM knowledge_concept_revisions WHERE concept_id=?",
            (concept_id,),
        ).fetchone()[0]
        content_digest = _digest(
            {
                "concept_id": concept_id,
                "revision": revision_number,
                "title": title,
                "description": description,
                "claims": claim_ids,
                "relationships": relationship_ids,
                "path": okf_path,
            }
        )
        revision_id = _urn("concept-revision", content_digest)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_concept_revisions(revision_id,concept_id,revision_number,title,description,claim_ids_json,relationship_ids_json,okf_path,content_digest,actor) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    revision_id,
                    concept_id,
                    revision_number,
                    title,
                    description,
                    _json(claim_ids),
                    _json(relationship_ids),
                    okf_path,
                    content_digest,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:concept-write",
            target_type="concept-revision",
            target_id=revision_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_concept_revisions WHERE revision_id=?",
                (revision_id,),
            ).fetchone()
        )

    def record_review(
        self,
        revision_id: str,
        review_type: str,
        verdict: str,
        reviewer: str,
        producer: str,
        authority: str,
    ) -> dict[str, Any]:
        revision = self.db.execute(
            "SELECT r.*,c.scope_json FROM knowledge_concept_revisions r JOIN knowledge_concepts c ON c.concept_id=r.concept_id WHERE revision_id=?",
            (revision_id,),
        ).fetchone()
        if revision is None:
            raise ValueError("revision not found")
        scope = json.loads(revision["scope_json"])
        receipt = self._gate("knowledge:review", reviewer, scope)
        if authority != "knowledge:review":
            raise PermissionError("knowledge:review required")
        if reviewer == producer:
            raise ValueError("producer/reviewer independence required")
        if verdict not in {
            "pass",
            "pass_with_conditions",
            "fail",
            "insufficient_evidence",
        }:
            raise ValueError("invalid review verdict")
        review_id = _urn(
            "review",
            _digest(
                {
                    "revision": revision_id,
                    "type": review_type,
                    "reviewer": reviewer,
                    "verdict": verdict,
                    "inputs": revision["content_digest"],
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_reviews(review_id,revision_id,review_type,verdict,reviewer,producer,inputs_digest,authority) VALUES(?,?,?,?,?,?,?,?)",
                (
                    review_id,
                    revision_id,
                    review_type,
                    verdict,
                    reviewer,
                    producer,
                    revision["content_digest"],
                    authority,
                ),
            )
        self._audit(
            operation="knowledge:review",
            target_type="review",
            target_id=review_id,
            actor=reviewer,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_reviews WHERE review_id=?", (review_id,)
            ).fetchone()
        )

    def transition_concept(
        self,
        concept_id: str,
        target: str,
        revision_id: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        concept = self.db.execute(
            "SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)
        ).fetchone()
        revision = self.db.execute(
            "SELECT * FROM knowledge_concept_revisions WHERE revision_id=? AND concept_id=?",
            (revision_id, concept_id),
        ).fetchone()
        if concept is None or revision is None:
            raise ValueError("concept/revision mismatch")
        scope = json.loads(concept["scope_json"])
        receipt = self._gate("knowledge:promote", actor, scope)
        if authority != "knowledge:promote":
            raise PermissionError("knowledge:promote required")
        current = concept["concept_lifecycle"]
        allowed = {
            "provisional": {"reviewed", "rejected"},
            "reviewed": {"validated", "contested", "rejected"},
            "validated": {"contested", "canonical", "deprecated"},
            "contested": {"reviewed", "rejected"},
            "canonical": {"superseded", "deprecated"},
        }
        if target not in allowed.get(current, set()):
            raise ValueError(f"illegal concept transition {current}->{target}")
        if target in {"reviewed", "validated", "canonical"}:
            passing = self.db.execute(
                "SELECT 1 FROM knowledge_reviews WHERE revision_id=? AND inputs_digest=? AND verdict IN ('pass','pass_with_conditions') LIMIT 1",
                (revision_id, revision["content_digest"]),
            ).fetchone()
            if passing is None:
                raise ValueError("passing exact-revision review required")
        transition_ordinal = self.db.execute(
            "SELECT COUNT(*) FROM knowledge_concept_transitions WHERE concept_id=?",
            (concept_id,),
        ).fetchone()[0]
        transition_id = _urn(
            "concept-transition",
            f"{transition_ordinal:06d}:{_digest({'concept': concept_id, 'revision': revision_id, 'from': current, 'to': target})}",
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_concept_transitions(transition_id,concept_id,revision_id,from_state,to_state,actor,authority,reason) VALUES(?,?,?,?,?,?,?,?)",
                (
                    transition_id,
                    concept_id,
                    revision_id,
                    current,
                    target,
                    actor,
                    authority,
                    "governed lifecycle transition",
                ),
            )
            self.db.execute(
                "UPDATE knowledge_concepts SET concept_lifecycle=? WHERE concept_id=?",
                (target, concept_id),
            )
        self._audit(
            operation="knowledge:promote",
            target_type="concept",
            target_id=concept_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            detail={"revision_id": revision_id, "from": current, "to": target},
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_concepts WHERE concept_id=?", (concept_id,)
            ).fetchone()
        )

    def create_question(
        self,
        text: str,
        related_claim_ids: list[int],
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:question-write", actor, scope)
        if authority != "knowledge:question-write":
            raise PermissionError("knowledge:question-write required")
        for claim_id in related_claim_ids:
            self.ledger.inspect(claim_id)
        question_id = _urn(
            "question",
            _digest(
                {
                    "text": text,
                    "claims": related_claim_ids,
                    "scope": scope,
                    "ordinal": self.db.execute(
                        "SELECT COUNT(*) FROM knowledge_questions"
                    ).fetchone()[0],
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_questions(question_id,text,related_claim_ids_json,scope_json,actor) VALUES(?,?,?,?,?)",
                (question_id, text, _json(related_claim_ids), _json(scope), actor),
            )
        self._audit(
            operation="knowledge:question-write",
            target_type="question",
            target_id=question_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_questions WHERE question_id=?", (question_id,)
            ).fetchone()
        )

    def answer_question(
        self,
        question_id: str,
        answer_claim_ids: list[int],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        question = self.db.execute(
            "SELECT * FROM knowledge_questions WHERE question_id=?", (question_id,)
        ).fetchone()
        if question is None:
            raise ValueError("question not found")
        scope = json.loads(question["scope_json"])
        receipt = self._gate("knowledge:question-write", actor, scope)
        if authority != "knowledge:question-write":
            raise PermissionError("knowledge:question-write required")
        if not answer_claim_ids:
            raise ValueError("grounded answer claims required")
        for claim_id in answer_claim_ids:
            state = self.ledger.inspect(claim_id)["status"]
            if state in {"unresolved", "falsified", "contradicted"}:
                raise ValueError("answer claim is not suitable for closure")
        with self.db:
            self.db.execute(
                "UPDATE knowledge_questions SET question_state='answered',answer_claim_ids_json=? WHERE question_id=?",
                (_json(answer_claim_ids), question_id),
            )
        self._audit(
            operation="knowledge:question-write",
            target_type="question",
            target_id=question_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            detail={"answer_claim_ids": answer_claim_ids},
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_questions WHERE question_id=?", (question_id,)
            ).fetchone()
        )

    def create_synthesis(
        self,
        text: str,
        input_claim_ids: list[int],
        interpretations: list[str],
        scope: dict[str, Any],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:synthesis-write", actor, scope)
        if authority != "knowledge:synthesis-write":
            raise PermissionError("knowledge:synthesis-write required")
        states = {
            str(claim_id): self.ledger.inspect(claim_id)["status"]
            for claim_id in input_claim_ids
        }
        inputs_digest = _digest({"claims": input_claim_ids, "states": states})
        synthesis_id = _urn(
            "synthesis",
            _digest(
                {
                    "text": text,
                    "inputs": inputs_digest,
                    "interpretations": interpretations,
                    "scope": scope,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_syntheses(synthesis_id,text,input_claim_ids_json,interpretations_json,claim_states_json,scope_json,inputs_digest,actor) VALUES(?,?,?,?,?,?,?,?)",
                (
                    synthesis_id,
                    text,
                    _json(input_claim_ids),
                    _json(interpretations),
                    _json(states),
                    _json(scope),
                    inputs_digest,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:synthesis-write",
            target_type="synthesis",
            target_id=synthesis_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
        )
        result = dict(
            self.db.execute(
                "SELECT * FROM knowledge_syntheses WHERE synthesis_id=?",
                (synthesis_id,),
            ).fetchone()
        )
        result["claim_states"] = json.loads(result["claim_states_json"])
        return result

    # ------------------------------------------------------------------
    # Publication validation and snapshot-frozen claim state
    # ------------------------------------------------------------------
    def _revision_payload(self, revision_id: str) -> dict[str, Any]:
        revision = self.db.execute(
            """
            SELECT r.*,c.concept_type,c.concept_lifecycle,c.scope_json
            FROM knowledge_concept_revisions r
            JOIN knowledge_concepts c ON c.concept_id=r.concept_id
            WHERE r.revision_id=?
            """,
            (revision_id,),
        ).fetchone()
        if revision is None:
            raise ValueError("revision not found")
        payload = dict(revision)
        payload["claim_ids"] = json.loads(payload.pop("claim_ids_json"))
        payload["relationship_ids"] = json.loads(payload.pop("relationship_ids_json"))
        payload["scope"] = json.loads(payload.pop("scope_json"))
        return payload

    @staticmethod
    def _scope_compatible(
        revision_scope: dict[str, Any], channel_scope: dict[str, Any]
    ) -> bool:
        if revision_scope.get("tenant") != channel_scope.get("tenant"):
            return False
        if revision_scope.get("visibility") != channel_scope.get("visibility"):
            return False
        for field in ("project", "domain"):
            required = channel_scope.get(field)
            if required is not None and revision_scope.get(field) != required:
                return False
        return True

    def _validate_revision_for_publication(
        self, revision_id: str, channel_id: str
    ) -> dict[str, Any]:
        revision = self._revision_payload(revision_id)
        channel = self.db.execute(
            "SELECT * FROM knowledge_publication_channels WHERE channel_id=? AND state='active'",
            (channel_id,),
        ).fetchone()
        if channel is None:
            raise ValueError("active publication channel not found")
        passing = self.db.execute(
            "SELECT 1 FROM knowledge_reviews WHERE revision_id=? AND inputs_digest=? AND verdict IN ('pass','pass_with_conditions') LIMIT 1",
            (revision_id, revision["content_digest"]),
        ).fetchone()
        promoted = self.db.execute(
            "SELECT 1 FROM knowledge_concept_transitions WHERE revision_id=? AND to_state IN ('validated','canonical') LIMIT 1",
            (revision_id,),
        ).fetchone()
        if passing is None or promoted is None:
            raise ValueError("exact revision must be reviewed and promoted before publication")
        if not self._scope_compatible(revision["scope"], json.loads(channel["scope_json"])):
            raise ValueError("revision scope is incompatible with publication channel scope")
        return revision

    @staticmethod
    def _evidence_source_refs(evidence_rows: list[dict[str, Any]]) -> list[str]:
        refs: set[str] = set()
        for evidence in evidence_rows:
            source_id = evidence.get("id")
            if source_id is not None:
                refs.add(str(source_id))
        return sorted(refs)

    def _capture_snapshot_claims(
        self, snapshot_id: str, revision_ids: list[str]
    ) -> None:
        with self.db:
            for revision_id in sorted(revision_ids):
                revision = self._revision_payload(revision_id)
                for claim_id in revision["claim_ids"]:
                    inspected = self.ledger.inspect(int(claim_id))
                    transition_id = inspected.get("transition_id")
                    evidence_rows = list(inspected.get("evidence", []))
                    self.db.execute(
                        "INSERT OR IGNORE INTO knowledge_snapshot_claims(snapshot_id,revision_id,concept_id,claim_id,statement,epistemic_status,confidence,evidence_json,source_refs_json,captured_transition_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            snapshot_id,
                            revision_id,
                            revision["concept_id"],
                            str(claim_id),
                            inspected["statement"],
                            inspected["status"],
                            float(inspected["confidence"]),
                            _json(evidence_rows),
                            _json(self._evidence_source_refs(evidence_rows)),
                            transition_id,
                        ),
                    )

    def render_snapshot_bytes(self, revision_ids: list[str]) -> bytes:
        records: list[dict[str, Any]] = []
        for revision_id in sorted(revision_ids):
            revision = self._revision_payload(revision_id)
            claims = []
            for claim_id in revision["claim_ids"]:
                inspected = self.ledger.inspect(int(claim_id))
                claims.append(
                    {
                        "id": claim_id,
                        "statement": inspected["statement"],
                        "status": inspected["status"],
                    }
                )
            records.append(
                {
                    "revision_id": revision_id,
                    "concept_id": revision["concept_id"],
                    "title": revision["title"],
                    "description": revision["description"],
                    "concept_type": revision["concept_type"],
                    "okf_path": revision["okf_path"],
                    "claims": claims,
                }
            )
        return (
            _json({"contract": "erasmus.okf-snapshot-render/v1", "revisions": records})
            + "\n"
        ).encode("utf-8")

    def publish_snapshot(
        self,
        channel_id: str,
        revision_ids: list[str],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        channel = self.db.execute(
            "SELECT * FROM knowledge_publication_channels WHERE channel_id=? AND state='active'",
            (channel_id,),
        ).fetchone()
        if channel is None:
            raise ValueError("active publication channel not found")
        scope = json.loads(channel["scope_json"])
        receipt = self._gate("knowledge:publish", actor, scope)
        if authority != "knowledge:publish" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:publish required")
        for revision_id in revision_ids:
            self._validate_revision_for_publication(revision_id, channel_id)
        rendered = self.render_snapshot_bytes(revision_ids)
        manifest_digest = hashlib.sha256(rendered).hexdigest()
        existing = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE channel_id=? AND manifest_digest=? AND snapshot_state='published'",
            (channel_id, manifest_digest),
        ).fetchone()
        if existing:
            return dict(existing)
        sequence = self.db.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM knowledge_snapshots WHERE channel_id=?",
            (channel_id,),
        ).fetchone()[0]
        snapshot_id = _urn("snapshot", f"{channel_id}:{sequence}:{manifest_digest}")
        target = (
            self.snapshots_root / channel_id / f"{sequence:08d}-{manifest_digest[:12]}"
        ).resolve()
        if not target.is_relative_to(self.snapshots_root):
            raise ValueError("snapshot path escaped root")
        staging = target.with_name(target.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            (staging / "snapshot.json").write_bytes(rendered)
            manifest = {
                "snapshot_id": snapshot_id,
                "channel_id": channel_id,
                "sequence": sequence,
                "revision_ids": sorted(revision_ids),
                "manifest_digest": manifest_digest,
            }
            (staging / "manifest.json").write_text(
                _json(manifest) + "\n", encoding="utf-8"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(target)
            with self.db:
                self.db.execute(
                    "INSERT INTO knowledge_snapshots(snapshot_id,channel_id,sequence,revision_ids_json,root_path,manifest_digest,snapshot_state,actor) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        snapshot_id,
                        channel_id,
                        sequence,
                        _json(sorted(revision_ids)),
                        str(target),
                        manifest_digest,
                        "published",
                        actor,
                    ),
                )
                self.db.execute(
                    "UPDATE knowledge_publication_channels SET current_snapshot_id=? WHERE channel_id=?",
                    (snapshot_id, channel_id),
                )
            self._capture_snapshot_claims(snapshot_id, revision_ids)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if target.exists() and self.db.execute(
                "SELECT 1 FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone() is None:
                shutil.rmtree(target, ignore_errors=True)
            raise
        self._audit(
            operation="knowledge:publish",
            target_type="snapshot",
            target_id=snapshot_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=scope,
            detail={"revision_ids": sorted(revision_ids)},
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
        )

    def current_snapshot(self, channel_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT s.* FROM knowledge_publication_channels c
            JOIN knowledge_snapshots s ON s.snapshot_id=c.current_snapshot_id
            WHERE c.channel_id=?
            """,
            (channel_id,),
        ).fetchone()
        return _row(row)

    # ------------------------------------------------------------------
    # FTS and snapshot-consistent retrieval
    # ------------------------------------------------------------------
    def build_fts_projection(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        frozen = self.db.execute(
            "SELECT * FROM knowledge_snapshot_claims WHERE snapshot_id=? ORDER BY revision_id,claim_id",
            (snapshot_id,),
        ).fetchall()
        if not frozen:
            raise ValueError("snapshot claim state is missing")
        with self.db:
            self.db.execute("DELETE FROM knowledge_fts WHERE snapshot_id=?", (snapshot_id,))
            self.db.execute(
                "DELETE FROM knowledge_fts_documents WHERE snapshot_id=?", (snapshot_id,)
            )
            for claim in frozen:
                revision = self._revision_payload(claim["revision_id"])
                row = (
                    snapshot_id,
                    claim["revision_id"],
                    claim["concept_id"],
                    claim["claim_id"],
                    revision["title"],
                    f"{revision['description']}\n{claim['statement']}",
                )
                self.db.execute(
                    "INSERT INTO knowledge_fts_documents(snapshot_id,revision_id,concept_id,claim_id,title,body) VALUES(?,?,?,?,?,?)",
                    row,
                )
                self.db.execute(
                    "INSERT INTO knowledge_fts(snapshot_id,revision_id,concept_id,claim_id,title,body) VALUES(?,?,?,?,?,?)",
                    row,
                )
        artifact_digest = _digest(
            [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM knowledge_fts_documents WHERE snapshot_id=? ORDER BY revision_id,claim_id",
                    (snapshot_id,),
                ).fetchall()
            ]
        )
        projection_id = _urn(
            "projection",
            _digest(
                {
                    "kind": "fts",
                    "snapshot": snapshot_id,
                    "artifact": artifact_digest,
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)",
                (
                    projection_id,
                    "fts",
                    snapshot_id,
                    "ready",
                    _json({"engine": "sqlite-fts5"}),
                    artifact_digest,
                ),
            )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_projection_manifests WHERE projection_id=?",
                (projection_id,),
            ).fetchone()
        )

    def add_serving_directive(
        self,
        action: str,
        target_type: str,
        target_id: str,
        channel_id: str | None,
        reason: str,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        receipt = self._gate("knowledge:serve-control", actor)
        if authority != "knowledge:serve-control":
            raise PermissionError("knowledge:serve-control required")
        directive_id = _urn(
            "serving-directive",
            _digest(
                {
                    "action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                    "channel": channel_id,
                    "reason": reason,
                    "ordinal": self.db.execute(
                        "SELECT COUNT(*) FROM knowledge_serving_directives"
                    ).fetchone()[0],
                }
            ),
        )
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_serving_directives(directive_id,action,target_type,target_id,channel_id,reason,actor) VALUES(?,?,?,?,?,?,?)",
                (
                    directive_id,
                    action,
                    target_type,
                    target_id,
                    channel_id,
                    reason,
                    actor,
                ),
            )
        self._audit(
            operation="knowledge:serve-control",
            target_type="serving-directive",
            target_id=directive_id,
            actor=actor,
            authority=authority,
            policy_receipt_id=receipt["receipt_id"],
            scope=self.DEFAULT_SCOPE,
        )
        return dict(
            self.db.execute(
                "SELECT * FROM knowledge_serving_directives WHERE directive_id=?",
                (directive_id,),
            ).fetchone()
        )

    def _blocked_claim(
        self, claim_id: str, channel_id: str
    ) -> str | None:
        row = self.db.execute(
            """
            SELECT reason FROM knowledge_serving_directives
            WHERE active=1 AND action IN ('exclude','block')
              AND target_type='claim' AND target_id=?
              AND (channel_id IS NULL OR channel_id=?)
            ORDER BY created_at DESC LIMIT 1
            """,
            (claim_id, channel_id),
        ).fetchone()
        return row["reason"] if row else None

    def retrieve(
        self,
        query: str,
        channel_id: str,
        limit: int,
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        channel = self.db.execute(
            "SELECT * FROM knowledge_publication_channels WHERE channel_id=?",
            (channel_id,),
        ).fetchone()
        if channel is None:
            raise ValueError("publication channel not found")
        self._gate("knowledge:read", actor, json.loads(channel["scope_json"]))
        if authority != "knowledge:read":
            raise PermissionError("knowledge:read required")
        snapshot = self.current_snapshot(channel_id)
        if snapshot is None:
            raise ValueError("channel has no current snapshot")
        projection = self.db.execute(
            "SELECT 1 FROM knowledge_projection_manifests WHERE source_snapshot_id=? AND kind='fts' AND projection_state='ready'",
            (snapshot["snapshot_id"],),
        ).fetchone()
        if projection is None:
            raise ValueError("ready FTS projection required")
        terms = " ".join(part for part in query.split() if part.strip())
        rows = self.db.execute(
            "SELECT snapshot_id,revision_id,concept_id,claim_id,title,body,bm25(knowledge_fts) rank FROM knowledge_fts WHERE knowledge_fts MATCH ? AND snapshot_id=? ORDER BY rank LIMIT ?",
            (terms, snapshot["snapshot_id"], max(limit * 4, limit)),
        ).fetchall()
        items: list[dict[str, Any]] = []
        omitted_reasons: list[str] = []
        for result in rows:
            blocked = self._blocked_claim(result["claim_id"], channel_id)
            if blocked:
                omitted_reasons.append(blocked)
                continue
            frozen = self.db.execute(
                "SELECT * FROM knowledge_snapshot_claims WHERE snapshot_id=? AND claim_id=?",
                (snapshot["snapshot_id"], result["claim_id"]),
            ).fetchone()
            if frozen is None:
                raise ValueError("snapshot claim state missing")
            operational = self.ledger.inspect(int(result["claim_id"]))
            revision = self._revision_payload(result["revision_id"])
            items.append(
                {
                    "claim_id": result["claim_id"],
                    "proposition_id": int(result["claim_id"]),
                    "concept_id": result["concept_id"],
                    "concept_path": revision["okf_path"],
                    "selected_text": frozen["statement"],
                    "epistemic_status": frozen["epistemic_status"],
                    "operational_epistemic_status": operational["status"],
                    "source_refs": json.loads(frozen["source_refs_json"]),
                    "retrieval_features": {"lexical": True, "rank": result["rank"]},
                }
            )
            if len(items) >= limit:
                break
        core = {
            "snapshot_id": snapshot["snapshot_id"],
            "channel_id": channel_id,
            "query": query,
            "items": items,
            "budget": {"used": len(items), "limit": limit},
            "omitted": {
                "count": len(omitted_reasons),
                "reasons": sorted(set(omitted_reasons)),
            },
        }
        packet_id = _urn("evidence-packet", _digest(core))
        receipt_id = _urn("use-receipt", _digest({"packet": packet_id, "actor": actor}))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_use_receipts(receipt_id,packet_id,channel_id,snapshot_id,item_ids_json,actor) VALUES(?,?,?,?,?,?)",
                (
                    receipt_id,
                    packet_id,
                    channel_id,
                    snapshot["snapshot_id"],
                    _json([item["claim_id"] for item in items]),
                    actor,
                ),
            )
        return {"contract": "erasmus.evidence-packet/v1", "packet_id": packet_id, **core}

    def get_use_receipt(self, packet_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM knowledge_use_receipts WHERE packet_id=?", (packet_id,)
        ).fetchone()
        if row is None:
            raise ValueError("use receipt not found")
        result = dict(row)
        result["packet_id"] = packet_id
        return result

    # ------------------------------------------------------------------
    # Maintenance and diagnostics
    # ------------------------------------------------------------------
    def authoritative_digest(self) -> str:
        tables = [
            "knowledge_policy_sets",
            "knowledge_semantic_registry",
            "knowledge_sources",
            "knowledge_source_spans",
            "knowledge_candidates",
            "knowledge_candidate_claims",
            "knowledge_candidate_transitions",
            "knowledge_entities",
            "knowledge_entity_aliases",
            "knowledge_identity_decisions",
            "knowledge_reconciliation_decisions",
            "knowledge_claim_bindings",
            "knowledge_concepts",
            "knowledge_concept_revisions",
            "knowledge_concept_transitions",
            "knowledge_relationships",
            "knowledge_reviews",
            "knowledge_questions",
            "knowledge_syntheses",
            "knowledge_snapshots",
            "knowledge_snapshot_claims",
            "knowledge_serving_directives",
            "knowledge_invalidation_events",
        ]
        payload: dict[str, Any] = {}
        for table in tables:
            payload[table] = [
                dict(row)
                for row in self.db.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
            ]
        return _digest(payload)

    def run_maintenance(self, actor: str, authority: str) -> dict[str, Any]:
        self._gate("knowledge:maintain", actor)
        if authority != "knowledge:maintain":
            raise PermissionError("knowledge:maintain required")
        stale = [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM knowledge_projection_manifests WHERE projection_state='stale'"
            ).fetchall()
        ]
        return {
            "contract": "erasmus.knowledge-maintenance/v1",
            "status": "completed",
            "actor": actor,
            "stale_projections": stale,
            "authoritative_mutations": 0,
        }

    def status(self) -> dict[str, Any]:
        version = self.db.execute(
            "SELECT COALESCE(MAX(version),0) FROM schema_version"
        ).fetchone()[0]
        return {
            "contract": "erasmus.knowledge-status/v1",
            "schema_version": version,
            "active_policy": _row(
                self.db.execute(
                    "SELECT policy_set_id,digest,state FROM knowledge_policy_sets WHERE state='active' LIMIT 1"
                ).fetchone()
            ),
            "sources": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_sources WHERE tombstoned=0"
            ).fetchone()[0],
            "candidates": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_candidates"
            ).fetchone()[0],
            "concepts": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_concepts"
            ).fetchone()[0],
            "snapshots": self.db.execute(
                "SELECT COUNT(*) FROM knowledge_snapshots"
            ).fetchone()[0],
        }
