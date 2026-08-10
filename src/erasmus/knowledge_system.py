from __future__ import annotations

import json
import math
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from .knowledge_runtime import KnowledgeRuntime, _digest, _json, _row, _urn
from .runtime import OpenAICompatibleRuntime
from .store import Store


class EmbeddingAdapter(Protocol):
    identity: dict[str, Any]

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingAdapter:
    """Replaceable vector adapter backed by the existing local runtime boundary.

    With ``LocalRuntimeConfig.runtime_kind='mistral_rs'`` this uses Mistral.rs;
    the same transport supports llama.cpp fallback without changing knowledge
    contracts or projection identity semantics.
    """

    def __init__(self, runtime: OpenAICompatibleRuntime):
        self.runtime = runtime
        config = runtime.config
        self.identity = {
            "runtime": config.runtime_kind,
            "model": config.model,
            "adapter": config.adapter,
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.runtime.embeddings(texts)


class KnowledgeSystem(KnowledgeRuntime):
    """Complete governed Phase 3 facade over the bounded knowledge runtime.

    Lower-level :class:`KnowledgeRuntime` implements the deterministic core.
    This facade is the production entry point: active policy is mandatory for
    knowledge mutation/read operations and P3.11-P3.14 services live here.
    """

    def __init__(self, store: Store, artifact_root: str | Path = "state/knowledge") -> None:
        super().__init__(store, artifact_root)
        self.okf_root = self.root / "okf-snapshots"
        self.okf_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Policy gate. Policy administration itself remains bootstrap-gated by
    # the exact hard-coded human authority in the base implementation.
    # ------------------------------------------------------------------
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
        entity = self.db.execute("SELECT scope_json FROM knowledge_entities WHERE entity_id=?", (entity_id,)).fetchone()
        self._gate("knowledge:identity-write", actor, json.loads(entity["scope_json"]) if entity else None)
        return super().add_entity_alias(entity_id, alias, namespace, actor, authority)

    def record_identity_decision(self, left_entity_id, right_entity_id, decision, actor, authority, rationale):
        self._gate("knowledge:identity-decide", actor)
        return super().record_identity_decision(left_entity_id, right_entity_id, decision, actor, authority, rationale)

    def create_concept(self, title, concept_type, claim_ids, scope, actor, authority):
        self._gate("knowledge:concept-write", actor, scope)
        return super().create_concept(title, concept_type, claim_ids, scope, actor, authority)

    def create_concept_revision(self, concept_id, title, description, claim_ids, relationship_ids, okf_path, actor, authority):
        concept = self.db.execute("SELECT scope_json FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone()
        self._gate("knowledge:concept-write", actor, json.loads(concept["scope_json"]) if concept else None)
        return super().create_concept_revision(concept_id, title, description, claim_ids, relationship_ids, okf_path, actor, authority)

    def record_review(self, revision_id, review_type, verdict, reviewer, producer, authority):
        self._gate("knowledge:review", reviewer)
        return super().record_review(revision_id, review_type, verdict, reviewer, producer, authority)

    def transition_concept(self, concept_id, target, revision_id, actor, authority):
        self._gate("knowledge:promote", actor)
        before = self.db.execute("SELECT concept_lifecycle FROM knowledge_concepts WHERE concept_id=?", (concept_id,)).fetchone()
        result = super().transition_concept(concept_id, target, revision_id, actor, authority)
        transition_id = _urn("concept-transition", _digest({
            "concept": concept_id,
            "revision": revision_id,
            "from": before["concept_lifecycle"] if before else None,
            "to": target,
            "actor": actor,
            "ordinal": self.db.execute("SELECT COUNT(*) FROM knowledge_concept_transitions WHERE concept_id=?", (concept_id,)).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_concept_transitions(transition_id,concept_id,revision_id,from_state,to_state,actor,authority,reason) VALUES(?,?,?,?,?,?,?,?)",
                (transition_id, concept_id, revision_id, before["concept_lifecycle"], target, actor, authority, "governed lifecycle transition"),
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
        return super().create_synthesis(text, input_claim_ids, interpretations, scope, actor, authority)

    # ------------------------------------------------------------------
    # P3.6 reconciliation completion. The base handles create/corroborate/
    # contradict and non-mutating dispositions. This facade implements the
    # replacement semantics required by amend/supersede.
    # ------------------------------------------------------------------
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
            "evidence",
            claim["statement"],
            "document",
            {"candidate_claim_id": candidate_claim_id, "action": action},
            "contextual",
            date.today().isoformat(),
            old["scope"],
            actor,
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
                (decision_id, candidate_claim_id, action, _json(targets), mission_id,
                 idempotency_key, actor, authority, _json(result)),
            )
            self.db.execute(
                "INSERT INTO knowledge_claim_bindings(binding_id,candidate_claim_id,proposition_id,relation,decision_id) VALUES(?,?,?,?,?)",
                (binding_id, candidate_claim_id, new_id, action, decision_id),
            )
        return {"decision_id": decision_id, **result}

    # ------------------------------------------------------------------
    # P3.9 real deterministic OKF publication.
    # ------------------------------------------------------------------
    @staticmethod
    def _yaml_scalar(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _okf_document(self, revision_id: str) -> bytes:
        revision = self._revision_payload(revision_id)
        if revision["concept_lifecycle"] not in {"validated", "canonical"}:
            raise ValueError("only validated/canonical revisions can publish")
        source_refs: set[str] = set()
        claims: list[dict[str, Any]] = []
        for claim_id in revision["claim_ids"]:
            inspected = self.ledger.inspect(int(claim_id))
            for evidence in inspected["evidence"]:
                provenance = evidence.get("provenance_json")
                if isinstance(provenance, str):
                    try:
                        provenance = json.loads(provenance)
                    except json.JSONDecodeError:
                        provenance = {}
                if isinstance(provenance, dict):
                    for span_id in provenance.get("source_span_ids", []):
                        span = self.db.execute(
                            "SELECT source_id FROM knowledge_source_spans WHERE span_id=?",
                            (span_id,),
                        ).fetchone()
                        if span:
                            source_refs.add(span["source_id"])
            claims.append({"id": str(claim_id), "statement": inspected["statement"], "status": inspected["status"]})
        lines = [
            "---",
            f"title: {self._yaml_scalar(revision['title'])}",
            f"description: {self._yaml_scalar(revision['description'])}",
            "status: canonical",
            "tags: []",
            "sources:",
        ]
        if source_refs:
            lines.extend(f"  - {self._yaml_scalar(source)}" for source in sorted(source_refs))
        else:
            lines.append("  []")
        lines.extend([
            "erasmus:",
            f"  concept_id: {self._yaml_scalar(revision['concept_id'])}",
            f"  revision_id: {self._yaml_scalar(revision_id)}",
            "---",
            "",
            f"# {revision['title']}",
            "",
            revision["description"],
            "",
            "## Claims",
            "",
        ])
        for claim in claims:
            lines.append(f"- {claim['statement']} (`{claim['status']}`, claim `{claim['id']}`)")
        lines.append("")
        return "\n".join(lines).encode("utf-8")

    def _verify_publication_receipt(self, snapshot: dict[str, Any]) -> None:
        receipt = self.db.execute(
            "SELECT * FROM knowledge_publication_receipts WHERE snapshot_id=?",
            (snapshot["snapshot_id"],),
        ).fetchone()
        if receipt is None:
            raise ValueError("published OKF snapshot is missing its receipt")
        root = Path(snapshot["root_path"])
        expected = json.loads(receipt["file_digests_json"])
        actual: dict[str, str] = {}
        for relative, digest in expected.items():
            path = root / relative
            if not path.is_file():
                raise ValueError(f"published snapshot file missing: {relative}")
            actual[relative] = _digest(path.read_bytes())
            if actual[relative] != digest:
                raise ValueError(f"published snapshot was modified: {relative}")

    def publish_okf_snapshot(self, channel_id: str, revision_ids: list[str], actor: str, authority: str) -> dict[str, Any]:
        self._gate("knowledge:publish", actor)
        if authority != "knowledge:publish" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:publish required")
        channel = self.db.execute(
            "SELECT * FROM knowledge_publication_channels WHERE channel_id=? AND state='active'",
            (channel_id,),
        ).fetchone()
        if channel is None:
            raise ValueError("active publication channel not found")
        files: dict[str, bytes] = {}
        for revision_id in sorted(revision_ids):
            revision = self._revision_payload(revision_id)
            relative = f"{revision['okf_path'].rstrip('/')}.md"
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise ValueError("publication path escaped snapshot root")
            if relative in files:
                raise ValueError("duplicate OKF path")
            files[relative] = self._okf_document(revision_id)
        file_digests = {path: _digest(content) for path, content in sorted(files.items())}
        manifest_digest = _digest({"contract": "erasmus.okf-publication/v1", "files": file_digests})
        existing = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE channel_id=? AND manifest_digest=? AND snapshot_state='published'",
            (channel_id, manifest_digest),
        ).fetchone()
        if existing:
            result = dict(existing)
            self._verify_publication_receipt(result)
            return result
        sequence = self.db.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM knowledge_snapshots WHERE channel_id=?",
            (channel_id,),
        ).fetchone()[0]
        snapshot_id = _urn("snapshot", f"{channel_id}:{sequence}:{manifest_digest}")
        target = (self.okf_root / channel_id / f"{sequence:08d}-{manifest_digest[:12]}").resolve()
        if not target.is_relative_to(self.okf_root):
            raise ValueError("snapshot path escaped OKF root")
        staging = target.with_name(target.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for relative, content in sorted(files.items()):
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            manifest = {
                "contract": "erasmus.okf-publication/v1",
                "snapshot_id": snapshot_id,
                "channel_id": channel_id,
                "sequence": sequence,
                "revision_ids": sorted(revision_ids),
                "file_digests": file_digests,
                "manifest_digest": manifest_digest,
            }
            (staging / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(target)
            receipt_id = _urn("publication-receipt", _digest(manifest))
            with self.db:
                self.db.execute(
                    "INSERT INTO knowledge_snapshots(snapshot_id,channel_id,sequence,revision_ids_json,root_path,manifest_digest,snapshot_state,actor) VALUES(?,?,?,?,?,?,?,?)",
                    (snapshot_id, channel_id, sequence, _json(sorted(revision_ids)), str(target), manifest_digest, "published", actor),
                )
                self.db.execute(
                    "INSERT INTO knowledge_publication_receipts(receipt_id,snapshot_id,channel_id,manifest_digest,file_digests_json,actor,authority) VALUES(?,?,?,?,?,?,?)",
                    (receipt_id, snapshot_id, channel_id, manifest_digest, _json(file_digests), actor, authority),
                )
                self.db.execute(
                    "UPDATE knowledge_publication_channels SET current_snapshot_id=? WHERE channel_id=?",
                    (snapshot_id, channel_id),
                )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if target.exists() and self.db.execute(
                "SELECT 1 FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone() is None:
                shutil.rmtree(target, ignore_errors=True)
            raise
        return dict(self.db.execute("SELECT * FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone())

    # ------------------------------------------------------------------
    # P3.11 disposable vector and graph projections.
    # ------------------------------------------------------------------
    @staticmethod
    def _norm(vector: list[float]) -> float:
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("embedding vector must have finite non-zero norm")
        return norm

    @staticmethod
    def _cosine(left: list[float], left_norm: float, right: list[float], right_norm: float) -> float:
        if len(left) != len(right):
            raise ValueError("embedding dimension mismatch")
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)

    def build_vector_projection(self, snapshot_id: str, adapter: EmbeddingAdapter) -> dict[str, Any]:
        snapshot = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        rows: list[tuple[str, str, str, str]] = []
        texts: list[str] = []
        for revision_id in json.loads(snapshot["revision_ids_json"]):
            revision = self._revision_payload(revision_id)
            for claim_id in revision["claim_ids"]:
                claim = self.ledger.inspect(int(claim_id))
                rows.append((revision_id, revision["concept_id"], str(claim_id), claim["statement"]))
                texts.append(f"{revision['title']}\n{revision['description']}\n{claim['statement']}")
        vectors = adapter.embed(texts)
        if len(vectors) != len(rows):
            raise ValueError("embedding adapter returned wrong vector count")
        normalized = []
        for row, vector in zip(rows, vectors):
            numeric = [float(value) for value in vector]
            normalized.append((*row, numeric, self._norm(numeric)))
        artifact_digest = _digest([
            {"revision_id": r, "concept_id": c, "claim_id": q, "vector": v}
            for r, c, q, _, v, _ in normalized
        ])
        config = {"model_identity": dict(adapter.identity), "distance": "cosine", "builder": "knowledge-system/vector-v1"}
        projection_id = _urn("projection", _digest({"kind": "vector", "snapshot": snapshot_id, "config": config, "artifact": artifact_digest}))
        existing = self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,)).fetchone()
        if existing:
            return dict(existing)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)",
                (projection_id, "vector", snapshot_id, "ready", _json(config), artifact_digest),
            )
            for revision_id, concept_id, claim_id, _, vector, norm in normalized:
                self.db.execute(
                    "INSERT INTO knowledge_vector_rows(projection_id,snapshot_id,revision_id,concept_id,claim_id,vector_json,norm) VALUES(?,?,?,?,?,?,?)",
                    (projection_id, snapshot_id, revision_id, concept_id, claim_id, _json(vector), norm),
                )
        return dict(self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,)).fetchone())

    def build_graph_projection(self, snapshot_id: str, max_edges: int = 10000, max_fanout: int = 256) -> dict[str, Any]:
        snapshot = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        revision_ids = json.loads(snapshot["revision_ids_json"])
        edges: set[tuple[str, str, str, str, str, int]] = set()
        published_concepts: set[str] = set()
        for revision_id in revision_ids:
            revision = self._revision_payload(revision_id)
            published_concepts.add(revision["concept_id"])
            for claim_id in revision["claim_ids"]:
                edges.add(("concept", revision["concept_id"], "contains_claim", "claim", str(claim_id), 1))
        for relationship in self.db.execute("SELECT * FROM knowledge_relationships").fetchall():
            if relationship["source_concept_id"] in published_concepts and relationship["target_concept_id"] in published_concepts:
                edges.add(("concept", relationship["source_concept_id"], relationship["predicate"], "concept", relationship["target_concept_id"], 0))
        if len(edges) > max_edges:
            raise ValueError("graph edge budget exceeded")
        fanout: dict[tuple[str, str], int] = {}
        for source_type, source_id, *_ in edges:
            key = (source_type, source_id)
            fanout[key] = fanout.get(key, 0) + 1
            if fanout[key] > max_fanout:
                raise ValueError("graph fan-out budget exceeded")
        artifact_digest = _digest(sorted(edges))
        config = {"builder": "knowledge-system/graph-v1", "max_edges": max_edges, "max_fanout": max_fanout}
        projection_id = _urn("projection", _digest({"kind": "graph", "snapshot": snapshot_id, "config": config, "artifact": artifact_digest}))
        existing = self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,)).fetchone()
        if existing:
            return dict(existing)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)",
                (projection_id, "graph", snapshot_id, "ready", _json(config), artifact_digest),
            )
            for source_type, source_id, predicate, target_type, target_id, derived in sorted(edges):
                self.db.execute(
                    "INSERT INTO knowledge_graph_edges(projection_id,snapshot_id,source_type,source_id,predicate,target_type,target_id,derived) VALUES(?,?,?,?,?,?,?,?)",
                    (projection_id, snapshot_id, source_type, source_id, predicate, target_type, target_id, derived),
                )
        return dict(self.db.execute("SELECT * FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,)).fetchone())

    def drop_projection(self, projection_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM knowledge_projection_manifests WHERE projection_id=?", (projection_id,))

    def _vector_items(self, query: str, snapshot_id: str, limit: int, adapter: EmbeddingAdapter) -> list[dict[str, Any]]:
        query_vector = [float(value) for value in adapter.embed([query])[0]]
        query_norm = self._norm(query_vector)
        manifests = self.db.execute(
            "SELECT * FROM knowledge_projection_manifests WHERE source_snapshot_id=? AND kind='vector' AND projection_state='ready' ORDER BY created_at DESC",
            (snapshot_id,),
        ).fetchall()
        compatible = None
        for manifest in manifests:
            config = json.loads(manifest["configuration_json"])
            if config.get("model_identity") == dict(adapter.identity):
                compatible = manifest
                break
        if compatible is None:
            raise ValueError("compatible ready vector projection required")
        scored = []
        for row in self.db.execute("SELECT * FROM knowledge_vector_rows WHERE projection_id=?", (compatible["projection_id"],)).fetchall():
            vector = [float(value) for value in json.loads(row["vector_json"])]
            scored.append((self._cosine(query_vector, query_norm, vector, row["norm"]), row))
        scored.sort(key=lambda item: (-item[0], item[1]["claim_id"]))
        items: list[dict[str, Any]] = []
        for score, row in scored[: max(limit * 4, limit)]:
            directive = self.db.execute(
                "SELECT reason FROM knowledge_serving_directives WHERE active=1 AND action IN ('exclude','block') AND target_type='claim' AND target_id=? LIMIT 1",
                (row["claim_id"],),
            ).fetchone()
            if directive:
                continue
            claim = self.ledger.inspect(int(row["claim_id"]))
            revision = self._revision_payload(row["revision_id"])
            items.append({
                "claim_id": row["claim_id"],
                "proposition_id": int(row["claim_id"]),
                "concept_id": row["concept_id"],
                "concept_path": revision["okf_path"],
                "selected_text": claim["statement"],
                "epistemic_status": claim["status"],
                "source_refs": [e["id"] for e in claim["evidence"]],
                "retrieval_features": {"vector": True, "cosine": score},
            })
            if len(items) >= limit:
                break
        return items

    def hybrid_retrieve(self, query: str, channel_id: str, limit: int, actor: str, authority: str, adapter: EmbeddingAdapter | None = None) -> dict[str, Any]:
        self._gate("knowledge:read", actor)
        if authority != "knowledge:read":
            raise PermissionError("knowledge:read required")
        lexical = super().retrieve(query, channel_id, limit, actor, authority)
        items = list(lexical["items"])
        omitted = dict(lexical["omitted"])
        snapshot_id = lexical["snapshot_id"]
        if adapter is not None:
            seen = {item["claim_id"] for item in items}
            for item in self._vector_items(query, snapshot_id, limit, adapter):
                if item["claim_id"] not in seen:
                    items.append(item)
                    seen.add(item["claim_id"])
                if len(items) >= limit:
                    break
        core = {
            "snapshot_id": snapshot_id,
            "channel_id": channel_id,
            "query": query,
            "items": items[:limit],
            "budget": {"used": min(len(items), limit), "limit": limit},
            "omitted": omitted,
            "modes": ["lexical"] + (["vector"] if adapter is not None else []),
        }
        packet_id = _urn("evidence-packet", _digest(core))
        receipt_id = _urn("use-receipt", _digest({"packet": packet_id, "actor": actor}))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_use_receipts(receipt_id,packet_id,channel_id,snapshot_id,item_ids_json,actor) VALUES(?,?,?,?,?,?)",
                (receipt_id, packet_id, channel_id, snapshot_id, _json([item["claim_id"] for item in core["items"]]), actor),
            )
        return {"contract": "erasmus.evidence-packet/v1", "packet_id": packet_id, **core}

    # ------------------------------------------------------------------
    # P3.12 freshness / invalidation / impact.
    # ------------------------------------------------------------------
    def assess_freshness(self, source_id: str, freshness_state: str, materiality: str, actor: str, authority: str, stale_after: str | None = None) -> dict[str, Any]:
        self._gate("knowledge:revalidate", actor)
        if authority != "knowledge:revalidate":
            raise PermissionError("knowledge:revalidate required")
        if freshness_state not in {"current", "approaching_stale", "stale", "unknown", "source_unavailable"}:
            raise ValueError("invalid freshness state")
        if materiality not in {"routine", "consequential", "protected"}:
            raise ValueError("invalid materiality")
        if self.db.execute("SELECT 1 FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone() is None:
            raise ValueError("source not found")
        assessment_id = _urn("freshness", _digest({
            "source": source_id, "state": freshness_state, "materiality": materiality,
            "stale_after": stale_after, "ordinal": self.db.execute("SELECT COUNT(*) FROM knowledge_freshness_assessments WHERE source_id=?", (source_id,)).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_freshness_assessments(assessment_id,source_id,freshness_state,materiality,stale_after,actor,authority) VALUES(?,?,?,?,?,?,?)",
                (assessment_id, source_id, freshness_state, materiality, stale_after, actor, authority),
            )
        return dict(self.db.execute("SELECT * FROM knowledge_freshness_assessments WHERE assessment_id=?", (assessment_id,)).fetchone())

    def _claims_for_source(self, source_id: str) -> set[int]:
        spans = {row[0] for row in self.db.execute("SELECT span_id FROM knowledge_source_spans WHERE source_id=?", (source_id,)).fetchall()}
        candidate_claim_ids: set[str] = set()
        for row in self.db.execute("SELECT candidate_claim_id,source_span_ids_json FROM knowledge_candidate_claims").fetchall():
            if spans.intersection(json.loads(row["source_span_ids_json"])):
                candidate_claim_ids.add(row["candidate_claim_id"])
        if not candidate_claim_ids:
            return set()
        placeholders = ",".join("?" for _ in candidate_claim_ids)
        return {int(row[0]) for row in self.db.execute(
            f"SELECT proposition_id FROM knowledge_claim_bindings WHERE candidate_claim_id IN ({placeholders})",
            tuple(sorted(candidate_claim_ids)),
        ).fetchall()}

    def invalidate_source(self, source_id: str, reason: str, actor: str, authority: str) -> dict[str, Any]:
        self._gate("knowledge:serve-control", actor)
        if authority != "knowledge:serve-control":
            raise PermissionError("knowledge:serve-control required")
        if not reason.strip():
            raise ValueError("invalidation reason required")
        assessment = self.db.execute(
            "SELECT * FROM knowledge_freshness_assessments WHERE source_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        materiality = assessment["materiality"] if assessment else "consequential"
        proposition_ids = self._claims_for_source(source_id)
        revision_ids: set[str] = set()
        for row in self.db.execute("SELECT revision_id,claim_ids_json FROM knowledge_concept_revisions").fetchall():
            if proposition_ids.intersection(int(value) for value in json.loads(row["claim_ids_json"])):
                revision_ids.add(row["revision_id"])
        snapshot_ids: set[str] = set()
        for row in self.db.execute("SELECT snapshot_id,revision_ids_json FROM knowledge_snapshots WHERE snapshot_state='published'").fetchall():
            if revision_ids.intersection(json.loads(row["revision_ids_json"])):
                snapshot_ids.add(row["snapshot_id"])
        invalidation_id = _urn("invalidation", _digest({
            "source": source_id, "reason": reason,
            "ordinal": self.db.execute("SELECT COUNT(*) FROM knowledge_invalidation_events WHERE target_type='source' AND target_id=?", (source_id,)).fetchone()[0],
        }))
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_invalidation_events(invalidation_id,target_type,target_id,reason,actor) VALUES(?,?,?,?,?)",
                (invalidation_id, "source", source_id, reason, actor),
            )
            for proposition_id in sorted(proposition_ids):
                action = "exclude" if materiality in {"consequential", "protected"} else "qualify"
                for channel in self.db.execute("SELECT channel_id FROM knowledge_publication_channels WHERE state='active'").fetchall():
                    directive_id = _urn("serving-directive", _digest({
                        "action": action, "target": proposition_id, "channel": channel["channel_id"], "invalidation": invalidation_id,
                    }))
                    self.db.execute(
                        "INSERT OR IGNORE INTO knowledge_serving_directives(directive_id,action,target_type,target_id,channel_id,reason,actor) VALUES(?,?,?,?,?,?,?)",
                        (directive_id, action, "claim", str(proposition_id), channel["channel_id"], reason, actor),
                    )
            for snapshot_id in snapshot_ids:
                self.db.execute(
                    "UPDATE knowledge_projection_manifests SET projection_state='stale' WHERE source_snapshot_id=? AND projection_state='ready'",
                    (snapshot_id,),
                )
        synthesis_ids: list[str] = []
        question_ids: list[str] = []
        for row in self.db.execute("SELECT synthesis_id,input_claim_ids_json FROM knowledge_syntheses").fetchall():
            if proposition_ids.intersection(int(v) for v in json.loads(row["input_claim_ids_json"])):
                synthesis_ids.append(row["synthesis_id"])
        for row in self.db.execute("SELECT question_id,related_claim_ids_json FROM knowledge_questions").fetchall():
            if proposition_ids.intersection(int(v) for v in json.loads(row["related_claim_ids_json"])):
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

    # ------------------------------------------------------------------
    # P3.13 durable bounded intake.
    # ------------------------------------------------------------------
    def set_intake_state(self, enabled: bool, actor: str, authority: str) -> None:
        self._gate("knowledge:intake-admin", actor)
        if authority != "knowledge:intake-admin" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:intake-admin required")
        with self.db:
            self.db.execute(
                "UPDATE knowledge_intake_control SET enabled=?,actor=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (int(bool(enabled)), actor),
            )

    def enqueue_intake(self, producer: str, payload: dict[str, Any], actor: str, authority: str, max_pending: int = 1000) -> dict[str, Any]:
        self._gate("knowledge:intake", actor)
        if authority != "knowledge:intake":
            raise PermissionError("knowledge:intake required")
        if producer not in {"foundry", "sleep", "mission", "deterministic", "repository", "reconnaissance", "model", "route"}:
            raise ValueError("unsupported intake producer")
        control = self.db.execute("SELECT enabled FROM knowledge_intake_control WHERE id=1").fetchone()
        if control is None or not control["enabled"]:
            raise RuntimeError("knowledge intake is stopped")
        pending = self.db.execute("SELECT COUNT(*) FROM knowledge_intake_queue WHERE state IN ('queued','processing')").fetchone()[0]
        if pending >= max_pending:
            raise RuntimeError("knowledge intake backpressure budget exceeded")
        payload_digest = _digest(payload)
        existing = self.db.execute(
            "SELECT * FROM knowledge_intake_queue WHERE producer=? AND payload_digest=?",
            (producer, payload_digest),
        ).fetchone()
        if existing:
            return dict(existing)
        intake_id = _urn("intake", _digest({"producer": producer, "payload": payload_digest}))
        disposition = "quarantined"
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_intake_queue(intake_id,producer,payload_json,payload_digest,disposition,state,actor,authority) VALUES(?,?,?,?,?,'queued',?,?)",
                (intake_id, producer, _json(payload), payload_digest, disposition, actor, authority),
            )
        return dict(self.db.execute("SELECT * FROM knowledge_intake_queue WHERE intake_id=?", (intake_id,)).fetchone())

    def list_intake(self, state: str | None = None) -> list[dict[str, Any]]:
        if state is None:
            rows = self.db.execute("SELECT * FROM knowledge_intake_queue ORDER BY created_at,intake_id").fetchall()
        else:
            rows = self.db.execute("SELECT * FROM knowledge_intake_queue WHERE state=? ORDER BY created_at,intake_id", (state,)).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # P3.14 read-only routing integration. Routing authority is deliberately
    # separate from knowledge authority; feedback is quarantined intake only.
    # ------------------------------------------------------------------
    def routing_context(self, query: str, channel_id: str, limit: int, actor: str, authority: str) -> dict[str, Any]:
        return self.hybrid_retrieve(query, channel_id, limit, actor, authority, adapter=None)

    def _packet_source_ids(self, packet: dict[str, Any]) -> list[str]:
        source_ids: set[str] = set()
        for item in packet.get("items", []):
            try:
                inspected = self.ledger.inspect(int(item["claim_id"]))
            except (ValueError, KeyError):
                continue
            for evidence in inspected["evidence"]:
                provenance = evidence.get("provenance_json")
                if isinstance(provenance, str):
                    try:
                        provenance = json.loads(provenance)
                    except json.JSONDecodeError:
                        continue
                if not isinstance(provenance, dict):
                    continue
                for span_id in provenance.get("source_span_ids", []):
                    row = self.db.execute("SELECT source_id FROM knowledge_source_spans WHERE span_id=?", (span_id,)).fetchone()
                    if row:
                        source_ids.add(row["source_id"])
        return sorted(source_ids)

    def record_route_decision(self, route_id: str, selected_route: str, packet: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "routing:decide":
            raise PermissionError("routing:decide required")
        if packet.get("contract") != "erasmus.evidence-packet/v1":
            raise ValueError("routing requires a governed evidence packet")
        claim_ids = [item["claim_id"] for item in packet.get("items", [])]
        source_ids = self._packet_source_ids(packet)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_route_decisions(route_id,selected_route,packet_id,claim_ids_json,source_ids_json,actor,authority) VALUES(?,?,?,?,?,?,?)",
                (route_id, selected_route, packet["packet_id"], _json(claim_ids), _json(source_ids), actor, authority),
            )
        row = dict(self.db.execute("SELECT * FROM knowledge_route_decisions WHERE route_id=?", (route_id,)).fetchone())
        row["claim_ids"] = json.loads(row["claim_ids_json"])
        row["source_ids"] = json.loads(row["source_ids_json"])
        return row

    def record_route_outcome(self, route_id: str, outcome: str, detail: dict[str, Any], actor: str, authority: str) -> dict[str, Any]:
        if authority != "routing:feedback":
            raise PermissionError("routing:feedback required")
        if outcome not in {"success", "failure", "cancelled"}:
            raise ValueError("invalid route outcome")
        if self.db.execute("SELECT 1 FROM knowledge_route_decisions WHERE route_id=?", (route_id,)).fetchone() is None:
            raise ValueError("route decision not found")
        outcome_id = _urn("route-outcome", _digest({"route": route_id, "outcome": outcome, "detail": detail}))
        payload = {"route_id": route_id, "outcome": outcome, "detail": detail}
        payload_digest = _digest(payload)
        intake_id = _urn("intake", _digest({"producer": "route", "payload": payload_digest}))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_route_outcomes(outcome_id,route_id,outcome,detail_json,actor,authority) VALUES(?,?,?,?,?,?)",
                (outcome_id, route_id, outcome, _json(detail), actor, authority),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_intake_queue(intake_id,producer,payload_json,payload_digest,disposition,state,actor,authority) VALUES(?,?,?,?,?,'queued',?,?)",
                (intake_id, "route", _json(payload), payload_digest, "quarantined", actor, authority),
            )
        return dict(self.db.execute("SELECT * FROM knowledge_intake_queue WHERE intake_id=?", (intake_id,)).fetchone())
