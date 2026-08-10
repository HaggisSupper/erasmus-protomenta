from __future__ import annotations

import json
from pathlib import Path

import pytest

from erasmus.ledger import EpistemicLedger
from erasmus.knowledge_system import KnowledgeSystem
from erasmus.store import Store


def _scope() -> dict:
    return {"visibility": "private", "tenant": "local", "project": "phase3", "domain": None, "labels": []}


def _system(tmp_path: Path) -> tuple[Store, KnowledgeSystem]:
    store = Store(str(tmp_path / "system.db"))
    store.init()
    store.init_phase3()
    system = KnowledgeSystem(store, tmp_path / "knowledge")
    rules = [
        {"effect": "permit", "operation": "knowledge:*", "actor": "human:*"},
        {"effect": "permit", "operation": "knowledge:*", "actor": "process:*"},
    ]
    digest = system.register_policy_set("test-policy", rules, "human:admin", "knowledge:policy-admin")
    system.activate_policy_set("test-policy", digest, "human:admin", "knowledge:policy-admin")
    return store, system


def _source_claim(system: KnowledgeSystem, statement: str = "Cavitation damages impellers.") -> tuple[dict, dict, dict]:
    source = system.register_source_bytes(
        statement.encode(), "fixture.txt", "text/plain", _scope(),
        "human:scott", "knowledge:source-register",
    )
    span = system.register_source_span(
        source["source_id"], {"kind": "text-lines", "data": {"start": 1, "end": 1}},
        statement, _scope(), "human:scott", "knowledge:source-register",
    )
    candidate = system.import_candidate(
        "foundry/v1", "Fixture", statement, [source["source_id"]], [span["span_id"]],
        _scope(), "human:scott", "knowledge:candidate-import",
    )
    claim = system.add_candidate_claim(
        candidate["candidate_id"], statement, [span["span_id"]], {}, _scope(),
        "routine", "human:scott", "knowledge:claim-decompose",
    )
    return source, candidate, claim


def _validated_revision(system: KnowledgeSystem, statement: str = "Cavitation damages impellers.") -> tuple[int, dict, dict]:
    _, _, claim = _source_claim(system, statement)
    system.admit_candidate(
        claim["candidate_id"], "human:scott", "knowledge:candidate-admit",
        mission_id=1, idempotency_key=f"admit:{claim['candidate_claim_id']}",
    )
    decision = system.reconcile_claim(
        claim["candidate_claim_id"], "create", "human:scott", "knowledge:reconcile",
        mission_id=1, idempotency_key=f"create:{claim['candidate_claim_id']}",
    )
    proposition = decision["proposition_id"]
    concept = system.create_concept("Cavitation", "phenomenon", [proposition], _scope(), "human:scott", "knowledge:concept-write")
    revision = system.create_concept_revision(
        concept["concept_id"], "Cavitation", statement, [proposition], [], "phenomena/cavitation",
        "human:scott", "knowledge:concept-write",
    )
    system.record_review(revision["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    system.transition_concept(concept["concept_id"], "reviewed", revision["revision_id"], "human:reviewer", "knowledge:promote")
    system.transition_concept(concept["concept_id"], "validated", revision["revision_id"], "human:reviewer", "knowledge:promote")
    return proposition, concept, revision


def test_store_does_not_activate_phase3_until_explicitly_requested(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "legacy.db"))
    store.init()
    versions = {row[0] for row in store.db.execute("SELECT version FROM schema_version")}
    assert max(versions) == 16
    assert store.db.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_sources'").fetchone() is None
    store.init_phase3()
    assert store.db.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_sources'").fetchone() is not None
    assert max(row[0] for row in store.db.execute("SELECT version FROM schema_version")) >= 22


def test_active_policy_is_mandatory_for_complete_system_mutations(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "policy.db"))
    store.init(); store.init_phase3()
    system = KnowledgeSystem(store, tmp_path / "knowledge")
    with pytest.raises(PermissionError, match="policy"):
        system.register_source_bytes(b"x", "x.txt", "text/plain", _scope(), "human:scott", "knowledge:source-register")


def test_supersede_creates_replacement_and_closes_old_ledger_path(tmp_path: Path) -> None:
    store, system = _system(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "old", "human", {"source": "old"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    old_id = ledger.propose("Old specification.", evidence, "human:scott", "ledger:write")
    _, _, claim = _source_claim(system, "New specification.")
    decision = system.reconcile_claim(
        claim["candidate_claim_id"], "supersede", "human:scott", "knowledge:reconcile",
        mission_id=2, idempotency_key="supersede-old", target_proposition_ids=[old_id],
    )
    new_id = decision["proposition_id"]
    assert new_id != old_id
    assert ledger.inspect(old_id)["superseded_by"] == new_id


def test_okf_publication_emits_deterministic_markdown_and_immutable_manifest(tmp_path: Path) -> None:
    _, system = _system(tmp_path)
    _, _, revision = _validated_revision(system)
    first = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    root = Path(first["root_path"])
    concept = root / "phenomena" / "cavitation.md"
    assert concept.is_file()
    text = concept.read_text(encoding="utf-8")
    assert "status: canonical" in text
    assert "sources:" in text and "## Claims" in text
    before = concept.read_bytes()
    second = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    assert second["manifest_digest"] == first["manifest_digest"]
    assert concept.read_bytes() == before


class FakeEmbeddingAdapter:
    identity = {"runtime": "fixture", "model": "semantic-v1", "dimensions": 3}

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            if any(term in lowered for term in ("cavitation", "impeller", "rotating component", "vapor bubble")):
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        return vectors


def test_vector_and_graph_projections_are_snapshot_bound_rebuildable_and_non_authoritative(tmp_path: Path) -> None:
    _, system = _system(tmp_path)
    _, _, revision = _validated_revision(system)
    snapshot = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    before = system.authoritative_digest()
    vector = system.build_vector_projection(snapshot["snapshot_id"], FakeEmbeddingAdapter())
    graph = system.build_graph_projection(snapshot["snapshot_id"])
    assert vector["projection_state"] == graph["projection_state"] == "ready"
    assert vector["source_snapshot_id"] == snapshot["snapshot_id"]
    assert json.loads(vector["configuration_json"])["model_identity"]["model"] == "semantic-v1"
    assert system.authoritative_digest() == before
    system.drop_projection(vector["projection_id"])
    rebuilt = system.build_vector_projection(snapshot["snapshot_id"], FakeEmbeddingAdapter())
    assert rebuilt["artifact_digest"] == vector["artifact_digest"]


def test_hybrid_retrieval_improves_paraphrase_recall_and_can_disable_semantic_paths(tmp_path: Path) -> None:
    _, system = _system(tmp_path)
    _, _, revision = _validated_revision(system)
    snapshot = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    system.build_fts_projection(snapshot["snapshot_id"])
    system.build_vector_projection(snapshot["snapshot_id"], FakeEmbeddingAdapter())
    lexical = system.hybrid_retrieve("rotating component damage", "private", 5, "human:scott", "knowledge:read", adapter=None)
    hybrid = system.hybrid_retrieve("rotating component damage", "private", 5, "human:scott", "knowledge:read", adapter=FakeEmbeddingAdapter())
    assert lexical["items"] == []
    assert hybrid["items"]
    fallback = system.hybrid_retrieve("cavitation", "private", 5, "human:scott", "knowledge:read", adapter=None)
    assert fallback["items"]


def test_freshness_invalidation_blocks_serving_without_changing_truth_state(tmp_path: Path) -> None:
    store, system = _system(tmp_path)
    proposition, _, revision = _validated_revision(system)
    snapshot = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    system.build_fts_projection(snapshot["snapshot_id"])
    source_id = store.db.execute("SELECT source_id FROM knowledge_sources LIMIT 1").fetchone()[0]
    prior_state = EpistemicLedger(store).inspect(proposition)["status"]
    assessment = system.assess_freshness(source_id, "stale", "consequential", "human:scott", "knowledge:revalidate")
    assert assessment["freshness_state"] == "stale"
    impact = system.invalidate_source(source_id, "source changed", "human:scott", "knowledge:serve-control")
    assert str(proposition) in impact["proposition_ids"]
    assert snapshot["snapshot_id"] in impact["snapshot_ids"]
    assert EpistemicLedger(store).inspect(proposition)["status"] == prior_state
    packet = system.hybrid_retrieve("cavitation", "private", 5, "human:scott", "knowledge:read", adapter=None)
    assert packet["items"] == []


def test_intake_queue_is_durable_bounded_stoppable_and_never_auto_promotes_model_output(tmp_path: Path) -> None:
    store, system = _system(tmp_path)
    first = system.enqueue_intake("model", {"text": "candidate one"}, "human:scott", "knowledge:intake", max_pending=2)
    second = system.enqueue_intake("mission", {"text": "candidate two"}, "human:scott", "knowledge:intake", max_pending=2)
    assert first["disposition"] == "quarantined"
    assert second["state"] == "queued"
    with pytest.raises(RuntimeError, match="backpressure"):
        system.enqueue_intake("model", {"text": "candidate three"}, "human:scott", "knowledge:intake", max_pending=2)
    system.set_intake_state(False, "human:scott", "knowledge:intake-admin")
    with pytest.raises(RuntimeError, match="stopped"):
        system.enqueue_intake("foundry", {"text": "blocked"}, "human:scott", "knowledge:intake")
    system2 = KnowledgeSystem(store, tmp_path / "knowledge")
    assert len(system2.list_intake("queued")) == 2


def test_routing_adapter_is_read_only_and_records_evidence_selection(tmp_path: Path) -> None:
    store, system = _system(tmp_path)
    _, _, revision = _validated_revision(system)
    snapshot = system.publish_okf_snapshot("private", [revision["revision_id"]], "human:scott", "knowledge:publish")
    system.build_fts_projection(snapshot["snapshot_id"])
    before = system.authoritative_digest()
    packet = system.routing_context("cavitation", "private", 4, "process:router", "knowledge:read")
    decision = system.record_route_decision("route-1", "deterministic-tool", packet, "process:router", "routing:decide")
    assert decision["claim_ids"] == [item["claim_id"] for item in packet["items"]]
    assert system.authoritative_digest() == before
    feedback = system.record_route_outcome("route-1", "success", {"lesson": "worked"}, "process:router", "routing:feedback")
    assert feedback["disposition"] == "quarantined"
    assert store.db.execute("SELECT COUNT(*) FROM skill_artifacts").fetchone()[0] == 0
