# Phase 3 Governed Knowledge System Design

## Approval and scope

The user directed Erasmus to fill all previously identified Phase 3 design gaps and fully specify the evolution from bounded Foundry candidates to governed canonical knowledge. This document records the resulting design decision and points to the complete architecture package.

This is a documentation-only, non-authorizing increment. Implementation remains decomposed into separately bounded missions.

## Context inspected

The design reconciles:

- the locked Phase 1–3 development track;
- the existing append-only epistemic ledger and its proposition states;
- the existing sleep candidate and explicit promotion-decision path;
- the current OKF capability graph and portable-manifest pattern;
- the existing local OpenAI-compatible runtime abstraction;
- the bounded PDF-to-OKF draft Foundry in PR #68;
- the deferred engineering-platform and adaptive-routing requirements;
- Google Open Knowledge Format v0.2 provenance, trust, lifecycle, and attestation conventions.

## Approaches considered

### 1. Mutable Markdown-authoritative corpus

Use one directly edited OKF directory as live authority. This is simple and readable but cannot atomically coordinate claim-level evidence, existing ledger transitions, review, concurrency, contradiction, publication, and rollback. Rejected for continuously agent-maintained canonical state.

### 2. Append-only operational authority plus immutable OKF snapshots

Use the existing ledger and new append-only SQLite records for live decisions; emit deterministic immutable OKF publication snapshots; treat indexes as projections. Selected because it preserves audit, atomicity, portability, rollback, and current architecture.

### 3. Graph-database authority

Use a graph database as the primary knowledge store. It supports relationships but introduces unnecessary infrastructure, weakens the local one-SQLite operating model, and still requires separate evidence, review, publication, and rollback contracts. Rejected as primary authority; graph remains a derived projection.

## Selected architecture

- Source artifacts are content-addressed evidence.
- Source spans and extraction receipts are reproducible.
- Candidates remain quarantined until admitted.
- Candidate concepts decompose into atomic candidate claims.
- Retrieval scouts propose comparison targets but do not decide identity or truth.
- Reconciliation produces explicit `create`, `corroborate`, `amend`, `contradict`, `supersede`, `duplicate`, `reject`, or `insufficient_evidence` decisions.
- The existing epistemic ledger remains authoritative for claim truth state.
- Stable concepts organize claim IDs through immutable revisions and typed relationships.
- Independent reviews and risk-based gates control lifecycle promotion.
- A deterministic publisher emits immutable OKF v0.2 snapshots.
- FTS, vector, graph, cache, UI, and context representations are rebuildable projections.
- Retrieval returns evidence packets with source, claim, truth, lifecycle, freshness, contradiction, and scope metadata.
- Human edits re-enter as candidate changes rather than mutating the active snapshot.

## Design package

- [`../../architecture/knowledge-system/README.md`](../../architecture/knowledge-system/README.md)
- [`../../architecture/knowledge-system/ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md`](../../architecture/knowledge-system/ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md)
- [`../../architecture/knowledge-system/CONTRACT_CATALOGUE.md`](../../architecture/knowledge-system/CONTRACT_CATALOGUE.md)
- [`../../architecture/knowledge-system/KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](../../architecture/knowledge-system/KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md)
- [`../../architecture/knowledge-system/OPEN_QUESTIONS_AND_SYNTHESIS.md`](../../architecture/knowledge-system/OPEN_QUESTIONS_AND_SYNTHESIS.md)
- [`../../architecture/knowledge-system/POLICY_IDENTITY_AND_REGISTRIES.md`](../../architecture/knowledge-system/POLICY_IDENTITY_AND_REGISTRIES.md)
- [`../../architecture/knowledge-system/STORAGE_PROJECTION_AND_RETRIEVAL.md`](../../architecture/knowledge-system/STORAGE_PROJECTION_AND_RETRIEVAL.md)
- [`../../architecture/knowledge-system/UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md`](../../architecture/knowledge-system/UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md)
- [`../../architecture/knowledge-system/OPERATOR_API_AND_RUNBOOK.md`](../../architecture/knowledge-system/OPERATOR_API_AND_RUNBOOK.md)
- [`../../architecture/knowledge-system/DESIGN_TRACEABILITY_MATRIX.md`](../../architecture/knowledge-system/DESIGN_TRACEABILITY_MATRIX.md)
- [`../../architecture/knowledge-system/SECURITY_PRIVACY_AND_GOVERNANCE.md`](../../architecture/knowledge-system/SECURITY_PRIVACY_AND_GOVERNANCE.md)
- [`../../architecture/knowledge-system/TEST_AND_ACCEPTANCE_PLAN.md`](../../architecture/knowledge-system/TEST_AND_ACCEPTANCE_PLAN.md)
- [`../../architecture/knowledge-system/GLOSSARY.md`](../../architecture/knowledge-system/GLOSSARY.md)
- [`../../roadmap/ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md`](../../roadmap/ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md)
- [`../../adr/ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md`](../../adr/ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md)

## Self-review

- No placeholders or unresolved design decisions remain in the target architecture.
- Candidate disposition, reconciliation action, ledger truth state, provisional concept/synthesis lifecycle, open-question state, freshness, projection state, and snapshot state are distinct.
- Every canonical mutation has authority, evidence, review, transaction, idempotency, rollback, and audit requirements.
- Existing ledger and capability authorities are preserved.
- The design is decomposed into P3.0–P3.14 rather than one implementation plan.
- The schema seed is experimental and cannot be mistaken for a live registered contract.
- Windows-first, local-first, Rust migration seams, mistral.rs/llama.cpp posture, CUDA/Vulkan/WebGPU preference, Tauri boundary, and no-Docker requirements are preserved.
