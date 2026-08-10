from __future__ import annotations

import json
import math
from typing import Any, Protocol

from .knowledge_runtime import _digest, _json, _urn
from .runtime import OpenAICompatibleRuntime


class EmbeddingAdapter(Protocol):
    identity: dict[str, Any]

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingAdapter:
    """Embedding adapter for Mistral.rs, llama.cpp, or compatible endpoints."""

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


class ProjectionFacadeMixin:
    """P3.10/P3.11 projection builders and resilient evidence retrieval."""

    @staticmethod
    def _norm(vector: list[float]) -> float:
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("embedding vector must have finite non-zero norm")
        return norm

    @staticmethod
    def _cosine(
        left: list[float], left_norm: float, right: list[float], right_norm: float
    ) -> float:
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
                rows.append((
                    revision_id, revision["concept_id"], str(claim_id), claim["statement"]
                ))
                texts.append(
                    f"{revision['title']}\n{revision['description']}\n{claim['statement']}"
                )
        vectors = adapter.embed(texts)
        if len(vectors) != len(rows):
            raise ValueError("embedding adapter returned wrong vector count")
        normalized = []
        for row, vector in zip(rows, vectors):
            numeric = [float(value) for value in vector]
            normalized.append((*row, numeric, self._norm(numeric)))
        artifact_digest = _digest([
            {
                "revision_id": revision_id,
                "concept_id": concept_id,
                "claim_id": claim_id,
                "vector": vector,
            }
            for revision_id, concept_id, claim_id, _, vector, _ in normalized
        ])
        config = {
            "model_identity": dict(adapter.identity),
            "distance": "cosine",
            "builder": "knowledge-system/vector-v1",
        }
        projection_id = _urn("projection", _digest({
            "kind": "vector",
            "snapshot": snapshot_id,
            "config": config,
            "artifact": artifact_digest,
        }))
        existing = self.db.execute(
            "SELECT * FROM knowledge_projection_manifests WHERE projection_id=?",
            (projection_id,),
        ).fetchone()
        if existing:
            return dict(existing)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)",
                (
                    projection_id, "vector", snapshot_id, "ready",
                    _json(config), artifact_digest,
                ),
            )
            for revision_id, concept_id, claim_id, _, vector, norm in normalized:
                self.db.execute(
                    "INSERT INTO knowledge_vector_rows(projection_id,snapshot_id,revision_id,concept_id,claim_id,vector_json,norm) VALUES(?,?,?,?,?,?,?)",
                    (
                        projection_id, snapshot_id, revision_id, concept_id,
                        claim_id, _json(vector), norm,
                    ),
                )
        return dict(self.db.execute(
            "SELECT * FROM knowledge_projection_manifests WHERE projection_id=?",
            (projection_id,),
        ).fetchone())

    def build_graph_projection(
        self, snapshot_id: str, max_edges: int = 10000, max_fanout: int = 256
    ) -> dict[str, Any]:
        snapshot = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        revision_ids = json.loads(snapshot["revision_ids_json"])
        edges: set[tuple[str, str, str, str, str, int]] = set()
        concepts: set[str] = set()
        for revision_id in revision_ids:
            revision = self._revision_payload(revision_id)
            concepts.add(revision["concept_id"])
            for claim_id in revision["claim_ids"]:
                edges.add((
                    "concept", revision["concept_id"], "contains_claim",
                    "claim", str(claim_id), 1,
                ))
        for relation in self.db.execute("SELECT * FROM knowledge_relationships").fetchall():
            if (
                relation["source_concept_id"] in concepts
                and relation["target_concept_id"] in concepts
            ):
                edges.add((
                    "concept", relation["source_concept_id"], relation["predicate"],
                    "concept", relation["target_concept_id"], 0,
                ))
        if len(edges) > max_edges:
            raise ValueError("graph edge budget exceeded")
        fanout: dict[tuple[str, str], int] = {}
        for source_type, source_id, *_ in edges:
            key = (source_type, source_id)
            fanout[key] = fanout.get(key, 0) + 1
            if fanout[key] > max_fanout:
                raise ValueError("graph fan-out budget exceeded")
        artifact_digest = _digest(sorted(edges))
        config = {
            "builder": "knowledge-system/graph-v1",
            "max_edges": max_edges,
            "max_fanout": max_fanout,
        }
        projection_id = _urn("projection", _digest({
            "kind": "graph", "snapshot": snapshot_id,
            "config": config, "artifact": artifact_digest,
        }))
        existing = self.db.execute(
            "SELECT * FROM knowledge_projection_manifests WHERE projection_id=?",
            (projection_id,),
        ).fetchone()
        if existing:
            return dict(existing)
        with self.db:
            self.db.execute(
                "INSERT INTO knowledge_projection_manifests(projection_id,kind,source_snapshot_id,projection_state,configuration_json,artifact_digest) VALUES(?,?,?,?,?,?)",
                (
                    projection_id, "graph", snapshot_id, "ready",
                    _json(config), artifact_digest,
                ),
            )
            for edge in sorted(edges):
                source_type, source_id, predicate, target_type, target_id, derived = edge
                self.db.execute(
                    "INSERT INTO knowledge_graph_edges(projection_id,snapshot_id,source_type,source_id,predicate,target_type,target_id,derived) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        projection_id, snapshot_id, source_type, source_id,
                        predicate, target_type, target_id, derived,
                    ),
                )
        return dict(self.db.execute(
            "SELECT * FROM knowledge_projection_manifests WHERE projection_id=?",
            (projection_id,),
        ).fetchone())

    def drop_projection(self, projection_id: str) -> None:
        with self.db:
            self.db.execute(
                "DELETE FROM knowledge_projection_manifests WHERE projection_id=?",
                (projection_id,),
            )

    def _claim_is_blocked(self, claim_id: str, channel_id: str) -> tuple[bool, str | None]:
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
        return (row is not None, row["reason"] if row else None)

    def _snapshot_scan(
        self, query: str, snapshot_id: str, channel_id: str, limit: int
    ) -> dict[str, Any]:
        """Deterministic bounded retrieval fallback independent of projections."""
        snapshot = self.db.execute(
            "SELECT revision_ids_json FROM knowledge_snapshots WHERE snapshot_id=? AND snapshot_state='published'",
            (snapshot_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("published snapshot not found")
        terms = [term.casefold() for term in query.split() if term.strip()]
        items: list[dict[str, Any]] = []
        omitted_reasons: list[str] = []
        scanned = 0
        scan_budget = max(limit * 32, 64)
        for revision_id in sorted(json.loads(snapshot["revision_ids_json"])):
            revision = self._revision_payload(revision_id)
            for claim_id in revision["claim_ids"]:
                if scanned >= scan_budget:
                    break
                scanned += 1
                claim = self.ledger.inspect(int(claim_id))
                haystack = (
                    f"{revision['title']} {revision['description']} {claim['statement']}"
                ).casefold()
                if terms and not all(term in haystack for term in terms):
                    continue
                blocked, reason = self._claim_is_blocked(str(claim_id), channel_id)
                if blocked:
                    omitted_reasons.append(reason or "serving directive")
                    continue
                items.append({
                    "claim_id": str(claim_id),
                    "proposition_id": int(claim_id),
                    "concept_id": revision["concept_id"],
                    "concept_path": revision["okf_path"],
                    "selected_text": claim["statement"],
                    "epistemic_status": claim["status"],
                    "source_refs": [e["id"] for e in claim["evidence"]],
                    "retrieval_features": {
                        "direct_snapshot_scan": True,
                        "scan_ordinal": scanned,
                    },
                })
                if len(items) >= limit:
                    break
            if len(items) >= limit or scanned >= scan_budget:
                break
        return {
            "items": items,
            "omitted": {
                "count": len(omitted_reasons),
                "reasons": sorted(set(omitted_reasons)),
            },
            "scan_budget": scan_budget,
            "scanned": scanned,
        }

    def _vector_items(
        self,
        query: str,
        snapshot_id: str,
        channel_id: str,
        limit: int,
        adapter: EmbeddingAdapter,
    ) -> list[dict[str, Any]]:
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
            return []
        scored = []
        for row in self.db.execute(
            "SELECT * FROM knowledge_vector_rows WHERE projection_id=?",
            (compatible["projection_id"],),
        ).fetchall():
            vector = [float(value) for value in json.loads(row["vector_json"])]
            scored.append((
                self._cosine(query_vector, query_norm, vector, row["norm"]), row
            ))
        scored.sort(key=lambda item: (-item[0], item[1]["claim_id"]))
        items: list[dict[str, Any]] = []
        for score, row in scored[: max(limit * 4, limit)]:
            blocked, _ = self._claim_is_blocked(row["claim_id"], channel_id)
            if blocked:
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

    def hybrid_retrieve(
        self,
        query: str,
        channel_id: str,
        limit: int,
        actor: str,
        authority: str,
        adapter: EmbeddingAdapter | None = None,
    ) -> dict[str, Any]:
        self._gate("knowledge:read", actor)
        if authority != "knowledge:read":
            raise PermissionError("knowledge:read required")
        snapshot = self.current_snapshot(channel_id)
        if snapshot is None:
            raise ValueError("channel has no current snapshot")
        modes: list[str] = []
        try:
            lexical = super().retrieve(query, channel_id, limit, actor, authority)
            items = list(lexical["items"])
            omitted = dict(lexical["omitted"])
            modes.append("lexical")
        except ValueError as error:
            if "ready FTS projection required" not in str(error):
                raise
            fallback = self._snapshot_scan(
                query, snapshot["snapshot_id"], channel_id, limit
            )
            items = list(fallback["items"])
            omitted = dict(fallback["omitted"])
            modes.append("direct_snapshot_scan")
        if adapter is not None:
            seen = {item["claim_id"] for item in items}
            vector_items = self._vector_items(
                query, snapshot["snapshot_id"], channel_id, limit, adapter
            )
            if vector_items:
                modes.append("vector")
            for item in vector_items:
                if item["claim_id"] not in seen:
                    items.append(item)
                    seen.add(item["claim_id"])
                if len(items) >= limit:
                    break
        core = {
            "snapshot_id": snapshot["snapshot_id"],
            "channel_id": channel_id,
            "query": query,
            "items": items[:limit],
            "budget": {"used": min(len(items), limit), "limit": limit},
            "omitted": omitted,
            "modes": modes,
        }
        packet_id = _urn("evidence-packet", _digest(core))
        receipt_id = _urn("use-receipt", _digest({"packet": packet_id, "actor": actor}))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO knowledge_use_receipts(receipt_id,packet_id,channel_id,snapshot_id,item_ids_json,actor) VALUES(?,?,?,?,?,?)",
                (
                    receipt_id, packet_id, channel_id, snapshot["snapshot_id"],
                    _json([item["claim_id"] for item in core["items"]]), actor,
                ),
            )
        return {
            "contract": "erasmus.evidence-packet/v1",
            "packet_id": packet_id,
            **core,
        }
