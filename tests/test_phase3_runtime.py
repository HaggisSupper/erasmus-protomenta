from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from erasmus.ledger import EpistemicLedger
from erasmus.store import Store


def _runtime(tmp_path: Path):
    from erasmus.knowledge_runtime import KnowledgeRuntime

    store = Store(str(tmp_path / "erasmus.db"))
    store.init()
    store.init_phase3()
    return store, KnowledgeRuntime(store, artifact_root=tmp_path / "knowledge")


def _scope() -> dict:
    return {"visibility": "private", "tenant": "local", "project": "phase3", "domain": None, "labels": []}


def test_phase3_migrations_are_applied_after_legacy_schema(tmp_path: Path) -> None:
    store, _ = _runtime(tmp_path)
    versions = {row[0] for row in store.db.execute("SELECT version FROM schema_version")}
    assert {17, 18, 19, 20} <= versions
    tables = {row[0] for row in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "knowledge_policy_sets", "knowledge_sources", "knowledge_source_spans",
        "knowledge_candidates", "knowledge_candidate_claims", "knowledge_entities",
        "knowledge_reconciliation_decisions", "knowledge_claim_bindings",
        "knowledge_concepts", "knowledge_concept_revisions", "knowledge_reviews",
        "knowledge_questions", "knowledge_syntheses", "knowledge_snapshots",
        "knowledge_projection_manifests", "knowledge_serving_directives",
        "knowledge_use_receipts", "knowledge_jobs",
    } <= tables


def test_policy_is_deterministic_deny_by_default_and_deny_overrides_permit(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    receipt = rt.evaluate_policy("knowledge:publish", actor="human:scott", scope=_scope(), dry_run=True)
    assert receipt["decision"] == "deny"
    digest = rt.register_policy_set(
        "local-default",
        [
            {"effect": "permit", "operation": "knowledge:*", "actor": "human:*"},
            {"effect": "deny", "operation": "knowledge:publish", "actor": "human:*"},
        ],
        actor="human:scott",
        authority="knowledge:policy-admin",
    )
    rt.activate_policy_set("local-default", digest, actor="human:scott", authority="knowledge:policy-admin")
    assert rt.evaluate_policy("knowledge:source-register", "human:scott", _scope())["decision"] == "permit"
    assert rt.evaluate_policy("knowledge:publish", "human:scott", _scope())["decision"] == "deny"


def test_source_registration_is_content_addressed_and_spans_are_immutable(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    data = b"page one\npage two\n"
    source = rt.register_source_bytes(data, locator="fixture.txt", media_type="text/plain", scope=_scope(), actor="human:scott", authority="knowledge:source-register")
    expected = hashlib.sha256(data).hexdigest()
    assert source["source_id"].endswith(expected)
    assert Path(source["storage_path"]).read_bytes() == data
    again = rt.register_source_bytes(data, locator="different-name.txt", media_type="text/plain", scope=_scope(), actor="human:scott", authority="knowledge:source-register")
    assert again["source_id"] == source["source_id"]
    span = rt.register_source_span(source["source_id"], {"kind": "text-lines", "data": {"start": 1, "end": 1}}, "page one", scope=_scope(), actor="human:scott", authority="knowledge:source-register")
    assert rt.get_source_span(span["span_id"])["text_digest"] == span["text_digest"]


def test_candidate_import_quarantines_and_reimport_is_idempotent(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    source = rt.register_source_bytes(b"evidence", "fixture.txt", "text/plain", _scope(), "human:scott", "knowledge:source-register")
    candidate = rt.import_candidate(
        producer="foundry/v1",
        title="Pump cavitation",
        body="Low NPSH can cause cavitation.",
        source_ids=[source["source_id"]],
        source_span_ids=[],
        scope=_scope(),
        actor="human:scott",
        authority="knowledge:candidate-import",
    )
    assert candidate["candidate_disposition"] == "quarantined"
    assert rt.import_candidate(**{**{k: candidate[k] for k in []}, "producer": "foundry/v1", "title": "Pump cavitation", "body": "Low NPSH can cause cavitation.", "source_ids": [source["source_id"]], "source_span_ids": [], "scope": _scope(), "actor": "human:scott", "authority": "knowledge:candidate-import"})["candidate_id"] == candidate["candidate_id"]


def test_candidate_claims_require_source_evidence_and_are_idempotent(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    source = rt.register_source_bytes(b"A causes B.", "fixture.txt", "text/plain", _scope(), "human:scott", "knowledge:source-register")
    span = rt.register_source_span(source["source_id"], {"kind": "text-lines", "data": {"start": 1, "end": 1}}, "A causes B.", _scope(), "human:scott", "knowledge:source-register")
    candidate = rt.import_candidate("foundry/v1", "A", "A causes B.", [source["source_id"]], [span["span_id"]], _scope(), "human:scott", "knowledge:candidate-import")
    claim = rt.add_candidate_claim(candidate["candidate_id"], "A causes B.", [span["span_id"]], {}, _scope(), "routine", "human:scott", "knowledge:claim-decompose")
    assert claim["candidate_claim_id"] == rt.add_candidate_claim(candidate["candidate_id"], "A causes B.", [span["span_id"]], {}, _scope(), "routine", "human:scott", "knowledge:claim-decompose")["candidate_claim_id"]
    with pytest.raises(ValueError):
        rt.add_candidate_claim(candidate["candidate_id"], "Unsupported", [], {}, _scope(), "routine", "human:scott", "knowledge:claim-decompose")


def test_entity_alias_does_not_merge_without_governed_decision(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    a = rt.create_entity("component", "Mistral.rs", _scope(), "human:scott", "knowledge:identity-write")
    b = rt.create_entity("component", "mistralrs", _scope(), "human:scott", "knowledge:identity-write")
    rt.add_entity_alias(a["entity_id"], "mistralrs", "name", "human:scott", "knowledge:identity-write")
    assert rt.resolve_entity_exact("mistralrs", _scope())["ambiguous"] is True
    decision = rt.record_identity_decision(a["entity_id"], b["entity_id"], "same_entity", actor="human:scott", authority="knowledge:identity-decide", rationale="explicitly reviewed")
    assert decision["decision"] == "same_entity"


def test_comparison_and_reconciliation_preserve_ledger_as_truth_authority(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    source = rt.register_source_bytes(b"Pump A is red.", "fixture.txt", "text/plain", _scope(), "human:scott", "knowledge:source-register")
    span = rt.register_source_span(source["source_id"], {"kind": "text-lines", "data": {"start": 1, "end": 1}}, "Pump A is red.", _scope(), "human:scott", "knowledge:source-register")
    candidate = rt.import_candidate("foundry/v1", "Pump A", "Pump A is red.", [source["source_id"]], [span["span_id"]], _scope(), "human:scott", "knowledge:candidate-import")
    claim = rt.add_candidate_claim(candidate["candidate_id"], "Pump A is red.", [span["span_id"]], {}, _scope(), "routine", "human:scott", "knowledge:claim-decompose")
    assert rt.compare_claim(claim["candidate_claim_id"])["targets"] == []
    decision = rt.reconcile_claim(claim["candidate_claim_id"], "create", actor="human:scott", authority="knowledge:reconcile", mission_id=1, idempotency_key="create-red")
    proposition_id = decision["proposition_id"]
    assert ledger.inspect(proposition_id)["statement"] == "Pump A is red."
    again = rt.reconcile_claim(claim["candidate_claim_id"], "create", actor="human:scott", authority="knowledge:reconcile", mission_id=1, idempotency_key="create-red")
    assert again["decision_id"] == decision["decision_id"]


def test_concept_revision_review_and_lifecycle_are_revision_aware(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "fixture", "human", {"source": "fixture"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    proposition = ledger.propose("Pump A is red.", evidence, "human:scott", "ledger:write")
    concept = rt.create_concept("Pump A", "component", [proposition], _scope(), "human:scott", "knowledge:concept-write")
    rev1 = rt.create_concept_revision(concept["concept_id"], "Pump A", "A pump.", [proposition], [], "pump-a", actor="human:scott", authority="knowledge:concept-write")
    review = rt.record_review(rev1["revision_id"], "tenth_man", "pass", reviewer="human:reviewer", producer="human:scott", authority="knowledge:review")
    assert review["verdict"] == "pass"
    assert rt.transition_concept(concept["concept_id"], "reviewed", rev1["revision_id"], actor="human:reviewer", authority="knowledge:promote")["concept_lifecycle"] == "reviewed"
    with pytest.raises(ValueError):
        rt.record_review(rev1["revision_id"], "tenth_man", "pass", reviewer="human:scott", producer="human:scott", authority="knowledge:review")


def test_questions_require_grounded_answer_and_synthesis_cannot_upgrade_claim_state(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "fixture", "human", {"source": "fixture"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    proposition = ledger.propose("Flow is uncertain.", evidence, "human:scott", "ledger:write", status="unresolved")
    question = rt.create_question("What is the flow?", [proposition], _scope(), "human:scott", "knowledge:question-write")
    with pytest.raises(ValueError):
        rt.answer_question(question["question_id"], [], "human:scott", "knowledge:question-write")
    synthesis = rt.create_synthesis("Flow remains uncertain.", [proposition], interpretations=[], scope=_scope(), actor="human:scott", authority="knowledge:synthesis-write")
    assert synthesis["claim_states"][str(proposition)] == "unresolved"


def test_publication_is_deterministic_immutable_and_channel_scoped(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "fixture", "human", {"source": "fixture"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    proposition = ledger.propose("Pump A is red.", evidence, "human:scott", "ledger:write")
    concept = rt.create_concept("Pump A", "component", [proposition], _scope(), "human:scott", "knowledge:concept-write")
    rev = rt.create_concept_revision(concept["concept_id"], "Pump A", "A pump.", [proposition], [], "pump-a", actor="human:scott", authority="knowledge:concept-write")
    rt.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    rt.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    rt.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    first = rt.publish_snapshot("private", [rev["revision_id"]], actor="human:scott", authority="knowledge:publish")
    second = rt.render_snapshot_bytes([rev["revision_id"]])
    assert hashlib.sha256(second).hexdigest() == first["manifest_digest"]
    assert rt.current_snapshot("private")["snapshot_id"] == first["snapshot_id"]
    assert rt.current_snapshot("public") is None


def test_fts_retrieval_returns_bounded_evidence_packet_and_use_receipt(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "fixture", "human", {"source": "fixture"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    proposition = ledger.propose("Cavitation damages impellers.", evidence, "human:scott", "ledger:write")
    concept = rt.create_concept("Cavitation", "phenomenon", [proposition], _scope(), "human:scott", "knowledge:concept-write")
    rev = rt.create_concept_revision(concept["concept_id"], "Cavitation", "Cavitation damages impellers.", [proposition], [], "cavitation", actor="human:scott", authority="knowledge:concept-write")
    rt.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    rt.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    rt.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    snapshot = rt.publish_snapshot("private", [rev["revision_id"]], "human:scott", "knowledge:publish")
    projection = rt.build_fts_projection(snapshot["snapshot_id"])
    assert projection["projection_state"] == "ready"
    packet = rt.retrieve("cavitation impellers", channel_id="private", limit=3, actor="human:scott", authority="knowledge:read")
    assert packet["items"] and packet["items"][0]["claim_id"]
    assert packet["budget"]["used"] <= 3
    assert rt.get_use_receipt(packet["packet_id"])["packet_id"] == packet["packet_id"]


def test_serving_directive_excludes_claim_before_context_materialization(tmp_path: Path) -> None:
    store, rt = _runtime(tmp_path)
    ledger = EpistemicLedger(store)
    evidence = ledger.add_evidence("evidence", "fixture", "human", {"source": "fixture"}, "primary", "2026-08-09", "global", "human:scott", "ledger:write")
    proposition = ledger.propose("Unsafe obsolete claim.", evidence, "human:scott", "ledger:write")
    concept = rt.create_concept("Unsafe", "note", [proposition], _scope(), "human:scott", "knowledge:concept-write")
    rev = rt.create_concept_revision(concept["concept_id"], "Unsafe", "Unsafe obsolete claim.", [proposition], [], "unsafe", actor="human:scott", authority="knowledge:concept-write")
    rt.record_review(rev["revision_id"], "tenth_man", "pass", "human:reviewer", "human:scott", "knowledge:review")
    rt.transition_concept(concept["concept_id"], "reviewed", rev["revision_id"], "human:reviewer", "knowledge:promote")
    rt.transition_concept(concept["concept_id"], "validated", rev["revision_id"], "human:reviewer", "knowledge:promote")
    snap = rt.publish_snapshot("private", [rev["revision_id"]], "human:scott", "knowledge:publish")
    rt.build_fts_projection(snap["snapshot_id"])
    rt.add_serving_directive("exclude", "claim", str(proposition), "private", "invalidated", "human:scott", "knowledge:serve-control")
    packet = rt.retrieve("obsolete", "private", 5, "human:scott", "knowledge:read")
    assert packet["items"] == []
    assert packet["omitted"]["count"] >= 1


def test_projection_rebuild_and_maintenance_are_non_authoritative(tmp_path: Path) -> None:
    _, rt = _runtime(tmp_path)
    before = rt.authoritative_digest()
    report = rt.run_maintenance(actor="process:maintenance", authority="knowledge:maintain")
    after = rt.authoritative_digest()
    assert report["status"] == "completed"
    assert before == after


def test_phase3_cli_emits_json_status(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from erasmus import knowledge_cli

    db = tmp_path / "cli.db"
    monkeypatch.setattr("sys.argv", ["erasmus-knowledge", "--db", str(db), "status"])
    knowledge_cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract"] == "erasmus.knowledge-status/v1"
    assert payload["schema_version"] >= 20
