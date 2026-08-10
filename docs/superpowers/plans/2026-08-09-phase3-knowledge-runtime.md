# Phase 3 Knowledge Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the merged P3.0A-P3.14 governed knowledge runtime as an additive, testable layer over the existing Erasmus epistemic ledger and mission/capability authorities.

**Architecture:** Preserve the existing epistemic ledger as the only proposition truth-state authority. Add Phase 3 persistence through migration versions 17+, a focused `KnowledgeRuntime` service that owns policy/registry/source/candidate/entity/reconciliation/concept/review/question/publication/retrieval/maintenance records, and a transport-neutral CLI. Derived FTS/graph/vector metadata remain rebuildable and never become truth authorities.

**Tech Stack:** Python 3.12, SQLite/FTS5, JSON Schema contracts already merged in the repository, local Mistral.rs-compatible semantic runtime where semantic work is required, llama.cpp-compatible fallback at the existing runtime boundary.

## Global Constraints

- No Docker or container runtime.
- Existing epistemic ledger remains sole proposition truth-state authority.
- Missing or ambiguous mutation policy denies by default.
- Phase 3 writes are append-only where the design specifies historical evidence/decisions.
- External Foundry documents remain untrusted `status: draft` candidates until governed import/admission.
- Canonical publication is deterministic, immutable and per publication channel.
- FTS/vector/graph/cache/UI structures are projections and are rebuildable.
- Every mutation is mission/actor/authority/idempotency scoped and auditable.
- Windows and Ubuntu Python 3.12 CI must pass before merge.

---

### Task 1: Phase 3 persistence and policy foundation
**Files:** Create `src/erasmus/phase3_migrations.py`; modify `src/erasmus/store.py`; test `tests/test_phase3_runtime.py`.
**Produces:** schema versions 17-20 and all authoritative Phase 3 tables/triggers.
- [ ] Write failing migration/policy tests.
- [ ] Verify RED.
- [ ] Implement additive migrations and policy evaluation.
- [ ] Verify GREEN.

### Task 2: Source, candidate, claim and identity pipeline
**Files:** Create/modify `src/erasmus/knowledge_runtime.py`; test `tests/test_phase3_runtime.py`.
**Produces:** deterministic sources/spans, Foundry candidate quarantine/import, atomic claims, entity aliases and governed identity decisions.
- [ ] Write failing behavior tests.
- [ ] Verify RED.
- [ ] Implement minimal governed pipeline.
- [ ] Verify GREEN.

### Task 3: Comparison, reconciliation and ledger binding
**Files:** Modify `src/erasmus/knowledge_runtime.py`; test `tests/test_phase3_runtime.py`.
**Produces:** observation-only comparison/proposals and idempotent governed reconciliation through `EpistemicLedger`.
- [ ] Write failing behavior tests.
- [ ] Verify RED.
- [ ] Implement and enforce ledger authority/transaction boundaries.
- [ ] Verify GREEN.

### Task 4: Concepts, review, questions and synthesis
**Files:** Modify `src/erasmus/knowledge_runtime.py`; test `tests/test_phase3_runtime.py`.
**Produces:** stable concept revisions/relationships, review lifecycle, open questions and grounded synthesis.
- [ ] Write failing behavior tests.
- [ ] Verify RED.
- [ ] Implement state machines and independence/grounding checks.
- [ ] Verify GREEN.

### Task 5: Publication, retrieval, projections and serving controls
**Files:** Modify `src/erasmus/knowledge_runtime.py`; test `tests/test_phase3_runtime.py`.
**Produces:** deterministic OKF snapshot renderer, per-channel current pointer, FTS projection, evidence packets, use receipts, directives/freshness/invalidation and projection manifests.
- [ ] Write failing behavior tests.
- [ ] Verify RED.
- [ ] Implement atomic publication and rebuildable projection paths.
- [ ] Verify GREEN.

### Task 6: Operator CLI and complete regression gate
**Files:** Create `src/erasmus/knowledge_cli.py`; modify `pyproject.toml`; test `tests/test_phase3_runtime.py` and full suite.
**Produces:** `erasmus-knowledge` inspect/validate/import/reconcile/publish/retrieve/maintenance commands with JSON output and typed failures.
- [ ] Write failing CLI tests.
- [ ] Verify RED.
- [ ] Implement CLI.
- [ ] Run focused tests, full repository tests, OpenCode validator and governance validator on Windows and Ubuntu CI.
- [ ] Resolve independent review findings before merge.
