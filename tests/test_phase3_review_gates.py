from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from erasmus.knowledge_runtime import KnowledgeRuntime
from erasmus.knowledge_system import KnowledgeSystem
from erasmus.ledger import EpistemicLedger
from erasmus.store import Store


def _scope(visibility: str = "private", tenant: str = "local", project: str | None = "phase3") -> dict:
    return {
        "visibility": visibility,
        "tenant": tenant,
        "project": project,
        "domain": None,
        "labels": [],
    }


def _bootstrap(store: Store, root: Path, cls=KnowledgeSystem):
    runtime = cls(store, root)
    rules = [
        {"effect": "permit", "operation": "knowledge:*", "actor": "human:*"},
        {"effect": "permit", "operation": "knowledge:*", "actor": "process:*"},
    ]
    digest = runtime.register_policy_set(
        "review-policy", rules, "human:admin", "knowledge:policy-admin"
    )
    runtime.activate_policy_set(
        "review-policy", digest, "human:admin", "knowledge:policy-admin"
    )
    return runtime


def _store(tmp_path: Path) -> Store:
    store = Store(str(tmp_path / "review.db"))
    store.init(); store.init_phase3()
    return store


def _candidate(runtime, text: str, name: str = "fixture", scope: dict | None = None):
    scope = scope or _scope()
    source = runtime.register_source_bytes(
        text.encode(), f"{name}.txt", "text/plain", scope,
        "human:scott", "knowledge:source-register",
    )
    span = runtime.register_source_span(
        source["source_id"],
        {"kind": "text-lines", "data": {"start": 1, "end": 1}},
        text, scope, "human:scott", "knowledge:source-register",
    )
    candidate = runtime.import_candidate(
        "foundry/v1", name, text, [source["source_id"]], [span["span_id"]],
        scope, "human:scott", "knowledge:candidate-import",
    )
    claim = runtime.add_candidate_claim(
        candidate["candidate_id"], text, [span["span_id"]], {}, scope,
        "routine", "human:scott", "knowledge:claim-decompose",
    )
    return source, span, candidate, claim


def test_direct_runtime_mutation_denies_without_active_policy(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = KnowledgeRuntime(store, tmp_path / "knowledge")
    with pytest.raises(PermissionError, match="policy"):
        runtime.register_source_bytes(
            b"blocked", "blocked.txt", "text/plain", _scope(),
            "human:scott", "knowledge:source-register",
        )


def test_quarantined_candidate_cannot_reconcile_until_governed_admission(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    _, _, candidate, claim = _candidate(runtime, "Admission is required.")
    assert candidate["candidate_disposition"] == "quarantined"
    with pytest.raises(ValueError, match="admissible"):
        runtime.reconcile_claim(
            claim["candidate_claim_id"], "create", "human:scott",
            "knowledge:reconcile", 1, "before-admission",
        )
    admitted = runtime.admit_candidate(
        candidate["candidate_id"], "human:scott", "knowledge:candidate-admit",
        mission_id=1, idempotency_key="admit-fixture",
    )
    assert admitted["candidate_disposition"] == "admissible"
    decision = runtime.reconcile_claim(
        claim["candidate_claim_id"], "create", "human:scott",
        "knowledge:reconcile", 1, "after-admission",
    )
    assert decision["proposition_id"] > 0


def test_claim_identity_includes_candidate_provenance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    source = runtime.register_source_bytes(
        b"same", "same.txt", "text/plain", _scope(),
        "human:scott", "knowledge:source-register",
    )
    span = runtime.register_source_span(
        source["source_id"], {"kind": "text-lines", "data": {"start": 1, "end": 1}},
        "same", _scope(), "human:scott", "knowledge:source-register",
    )
    c1 = runtime.import_candidate(
        "foundry/a", "A", "same", [source["source_id"]], [span["span_id"]],
        _scope(), "human:scott", "knowledge:candidate-import",
    )
    c2 = runtime.import_candidate(
        "foundry/b", "B", "same", [source["source_id"]], [span["span_id"]],
        _scope(), "human:scott", "knowledge:candidate-import",
    )
    q1 = runtime.add_candidate_claim(
        c1["candidate_id"], "same", [span["span_id"]], {}, _scope(), "routine",
        "human:scott", "knowledge:claim-decompose",
    )
    q2 = runtime.add_candidate_claim(
        c2["candidate_id"], "same", [span["span_id"]], {}, _scope(), "routine",
        "human:scott", "knowledge:claim-decompose",
    )
    assert q1["candidate_claim_id"] != q2["candidate_claim_id"]
    assert q1["candidate_id"] == c1["candidate_id"]
    assert q2["candidate_id"] == c2["candidate_id"]


def test_publication_requires_exact_reviewed_promoted_revision(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    _, _, candidate, claim = _candidate(runtime, "Exact revision review.")
    runtime.admit_candidate(candidate["candidate_id"], "human:scott", "knowledge:candidate-admit", 1, "admit-exact")
    prop = runtime.reconcile_claim(claim["candidate_claim_id"], "create", "human:scott", "knowledge:reconcile", 1, "create-exact")["proposition_id"]
    concept = runtime.create_concept("Exact", "note", [prop], _scope(), "human:scott", "knowledge:concept-write")
    rev1 = runtime.create_concept_revision(concept["concept_id"], "Exact", "reviewed", [prop], [], "exact", "human:scott", "knowledge:concept-write")
    runtime.record_review(rev1["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    runtime.transition_concept(concept["concept_id"], "reviewed", rev1["revision_id"], "human:reviewer", "knowledge:promote")
    runtime.transition_concept(concept["concept_id"], "validated", rev1["revision_id"], "human:reviewer", "knowledge:promote")
    rev2 = runtime.create_concept_revision(concept["concept_id"], "Exact", "unreviewed change", [prop], [], "exact", "human:scott", "knowledge:concept-write")
    with pytest.raises(ValueError, match="exact revision"):
        runtime.publish_okf_snapshot("private", [rev2["revision_id"]], "human:scott", "knowledge:publish")
    assert runtime.publish_okf_snapshot("private", [rev1["revision_id"]], "human:scott", "knowledge:publish")["snapshot_id"]


def test_private_revision_cannot_publish_to_public_channel(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    _, _, candidate, claim = _candidate(runtime, "Private content.")
    runtime.admit_candidate(candidate["candidate_id"], "human:scott", "knowledge:candidate-admit", 1, "admit-private")
    prop = runtime.reconcile_claim(claim["candidate_claim_id"], "create", "human:scott", "knowledge:reconcile", 1, "create-private")["proposition_id"]
    concept = runtime.create_concept("Private", "note", [prop], _scope(), "human:scott", "knowledge:concept-write")
    rev = runtime.create_concept_revision(concept["concept_id"], "Private", "private", [prop], [], "private", "human:scott", "knowledge:concept-write")
    runtime.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    runtime.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    runtime.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    runtime.ensure_channel("public", _scope("public", project=None), "public", "human:admin", "knowledge:channel-admin")
    with pytest.raises(ValueError, match="scope"):
        runtime.publish_okf_snapshot("public", [rev["revision_id"]], "human:scott", "knowledge:publish")


def test_lifecycle_transition_history_is_append_only_and_revision_bound(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    _, _, candidate, claim = _candidate(runtime, "Lifecycle history.")
    runtime.admit_candidate(candidate["candidate_id"], "human:scott", "knowledge:candidate-admit", 1, "admit-life")
    prop = runtime.reconcile_claim(claim["candidate_claim_id"], "create", "human:scott", "knowledge:reconcile", 1, "create-life")["proposition_id"]
    concept = runtime.create_concept("Life", "note", [prop], _scope(), "human:scott", "knowledge:concept-write")
    rev = runtime.create_concept_revision(concept["concept_id"], "Life", "history", [prop], [], "life", "human:scott", "knowledge:concept-write")
    runtime.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    runtime.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    runtime.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    rows = store.db.execute("SELECT * FROM knowledge_concept_transitions WHERE concept_id=? ORDER BY created_at,transition_id", (concept["concept_id"],)).fetchall()
    assert [(r["from_state"], r["to_state"], r["revision_id"]) for r in rows] == [
        ("provisional", "reviewed", rev["revision_id"]),
        ("reviewed", "validated", rev["revision_id"]),
    ]
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM knowledge_concept_transitions WHERE transition_id=?", (rows[0]["transition_id"],))
    store.db.rollback()


def test_retrieval_uses_snapshot_epistemic_state_not_newer_live_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runtime = _bootstrap(store, tmp_path / "knowledge")
    _, _, candidate, claim = _candidate(runtime, "Frozen state.")
    runtime.admit_candidate(candidate["candidate_id"], "human:scott", "knowledge:candidate-admit", 1, "admit-frozen")
    prop = runtime.reconcile_claim(claim["candidate_claim_id"], "create", "human:scott", "knowledge:reconcile", 1, "create-frozen")["proposition_id"]
    concept = runtime.create_concept("Frozen", "note", [prop], _scope(), "human:scott", "knowledge:concept-write")
    rev = runtime.create_concept_revision(concept["concept_id"], "Frozen", "Frozen state.", [prop], [], "frozen", "human:scott", "knowledge:concept-write")
    runtime.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    runtime.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    runtime.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    snapshot = runtime.publish_okf_snapshot("private", [rev["revision_id"]], "human:scott", "knowledge:publish")
    runtime.build_fts_projection(snapshot["snapshot_id"])
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "new support", "human", {"source": "later"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    ledger.transition(prop, "support", evidence, "human:scott", "ledger:write", "later evidence", target_status="plausible")
    packet = runtime.hybrid_retrieve("Frozen", "private", 5, "human:scott", "knowledge:read")
    assert packet["items"][0]["epistemic_status"] == "speculative"
    assert packet["items"][0]["operational_epistemic_status"] == "plausible"
