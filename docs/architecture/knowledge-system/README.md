# Erasmus Phase 3 Knowledge-System Design Package

- **Version:** 1.0.0
- **Status:** Complete target design; deferred and non-authorizing
- **Draft schema registration:** Registered for design discovery, review, and validation
- **Database migration:** None
- **Runtime activation:** None

This directory defines the governed Phase 3 evolution from external Foundry `status: draft` candidate concepts to provisional internal knowledge, evidence-backed claims, durable concepts, governed syntheses and open questions, immutable OKF v0.2 publication snapshots, and rebuildable retrieval projections.

## Current implementation status

The draft Phase 3 schema set has been registered as an experimental, non-runtime contract surface. Registration makes the schema identities and relationships discoverable and testable; it does not create database tables or authorize behavior.

No migration has been added. No policy, registry, candidate import, identity resolution, serving directive, canonical publication, or retrieval projection has been activated.

## Documents

1. [`ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md`](ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md) — complete architecture, invariants, components, identities, authorities, publication model, failure handling, and implementation boundaries.
2. [`CONTRACT_CATALOGUE.md`](CONTRACT_CATALOGUE.md) — target record and capability contracts, field requirements, invariants, compatibility with the current ledger, and error taxonomy.
3. [`STATE_MODEL.md`](STATE_MODEL.md) — normative separation of external Foundry status, candidate disposition, reconciliation action, ledger truth state, concept/synthesis lifecycle, question state, freshness, snapshot state, and projection state.
4. [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) — legal transitions; reconciliation decision table; contradiction, evidence-independence, supersession, and promotion rules.
5. [`OPEN_QUESTIONS_AND_SYNTHESIS.md`](OPEN_QUESTIONS_AND_SYNTHESIS.md) — open-question, hypothesis, research-mission, synthesis, grounding, coverage, closure, and publication contracts.
6. [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) — policy precedence and receipts, stable entity identity, aliases and resolution, semantic registries, relationship definitions, compatibility, and per-audience publication channels.
7. [`STORAGE_PROJECTION_AND_RETRIEVAL.md`](STORAGE_PROJECTION_AND_RETRIEVAL.md) — source-of-truth matrix, target SQLite tables, append-only and transaction boundaries, immutable snapshot layout, lexical/vector/graph projections, and evidence-packet retrieval.
8. [`UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md`](UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md) — typed uncertainty, materiality, authoritative dependencies, knowledge-use receipts, invalidation propagation, immediate serving directives, and downstream impact notification.
9. [`TEMPORAL_CONSISTENCY_AND_HISTORY.md`](TEMPORAL_CONSISTENCY_AND_HISTORY.md) — source/valid/transaction/publication/projection time, as-of queries, consistency modes, historical reconstruction, publication lag, and revision concurrency.
10. [`OPERATOR_API_AND_RUNBOOK.md`](OPERATOR_API_AND_RUNBOOK.md) — transport-neutral request/response envelopes, headless CLI, durable jobs, health, dry-run, backup/recovery, Tauri/MCP boundaries, PowerShell workflows, and exit codes.
11. [`SECURITY_PRIVACY_AND_GOVERNANCE.md`](SECURITY_PRIVACY_AND_GOVERNANCE.md) — threat model, prompt-injection and poisoning defenses, source/parser security, least privilege, privacy scopes, publication protection, incident response, and security tests.
12. [`TEST_AND_ACCEPTANCE_PLAN.md`](TEST_AND_ACCEPTANCE_PLAN.md) — fixture corpus, unit/contract/state/integration/recovery/security/retrieval tests, CI matrix, acceptance evidence, and complete-app definition of done.
13. [`GLOSSARY.md`](GLOSSARY.md) — normative terminology separating evidence, claims, concepts, truth state, lifecycle, publication, and projections.
14. [`DESIGN_TRACEABILITY_MATRIX.md`](DESIGN_TRACEABILITY_MATRIX.md) — maps every identified design gap to its normative document, contract/schema, roadmap increment, and required verification.

## Registered experimental non-runtime schema set

1. [`schemas/knowledge-system.schema.json`](schemas/knowledge-system.schema.json) — source, span, candidate claim, reconciliation, concept revision, review, snapshot, projection, evidence-packet, and mutation-command contracts.
2. [`schemas/question-synthesis.schema.json`](schemas/question-synthesis.schema.json) — open-question and synthesis records and transitions.
3. [`schemas/governance-registry.schema.json`](schemas/governance-registry.schema.json) — knowledge policy, policy evaluation, entity identity, semantic registry, relationship definition, and publication-channel contracts.
4. [`schemas/impact-serving.schema.json`](schemas/impact-serving.schema.json) — uncertainty, materiality, dependencies, use receipts, invalidation events, impact analyses, and serving directives.
5. [`schemas/temporal-consistency.schema.json`](schemas/temporal-consistency.schema.json) — valid/as-known/publication time, consistency-mode selection, and historical-query receipts.
6. [`schemas/operator-api.schema.json`](schemas/operator-api.schema.json) — transport-neutral requests/responses, durable knowledge jobs, progress events, budgets, and typed failures.

The schema files are registered draft design fixtures only. They are not imported or activated by the live Erasmus runtime.

## Governing decisions and sequence

- [`../../adr/ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md`](../../adr/ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md) fixes operational records, OKF publication, and projection authority boundaries.
- [`../../roadmap/ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md`](../../roadmap/ERASMUS_PHASE_3_KNOWLEDGE_EVOLUTION.md) decomposes Phase 3 into independently reversible missions P3.0 through P3.14, including explicit policy/registry, identity-resolution, open-question/synthesis, temporal-consistency, and impact/serving-control requirements.
- [`../okf-knowledge-foundry.md`](../okf-knowledge-foundry.md) defines the bounded PDF-to-draft-candidate seam implemented by PR #68.
- [`../../DEVELOPMENT_TRACK.md`](../../DEVELOPMENT_TRACK.md) remains the governing development sequence.

## Core decision

```text
immutable source artifacts
        ↓
append-only evidence and knowledge decisions
        ↓
existing epistemic ledger for claim truth state
        ↓
immutable concept revisions, open questions, syntheses, and dependencies
        ↓
deterministic OKF v0.2 publication snapshots per governed channel
        ↓
rebuildable lexical / vector / graph / UI projections
        ↓
authorization-aware serving directives and evidence packets
        ↓
knowledge-use receipts and downstream impact analysis
```

The model may propose candidates, claims, identities, relationships, questions, and syntheses. It cannot grant authority, activate policy or registries, make final identity decisions, verify itself, close a question, apply a serving directive, mutate canonical state, or publish a snapshot.

## State terminology

- **Foundry output:** external OKF documents remain `status: draft` and unverified.
- **Phase 3 internal concept/synthesis lifecycle:** begins at `provisional`, then may move through governed review and validation.
- **Claim truth state:** remains entirely within the existing epistemic ledger vocabulary.
- **Canonical:** means included in the current immutable published snapshot for an authorized publication channel and scope; it does not imply that every claim is established or uncontested.
- **Serving directive:** an operational qualification or block between immutable publication revisions; it does not alter claim truth or historical snapshot bytes.

## Phase boundary

Draft Phase 3 schemas are registered as non-runtime design contracts. No migration has been added. No policy, registry, candidate import, identity resolution, serving directive, canonical publication, or retrieval projection has been activated. The package remains design authority only and does not authorize Phase 3 runtime behavior.
