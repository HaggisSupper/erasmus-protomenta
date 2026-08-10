# ADR-KNOWLEDGE-001: Authoritative Operational State and Immutable OKF Publication

- **Status:** Accepted target architecture; implementation deferred
- **Date:** 2026-08-09
- **Decision scope:** Erasmus Phase 3 knowledge system
- **Related specification:** [`../architecture/knowledge-system/ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md`](../architecture/knowledge-system/ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md)

## Context

Erasmus needs to evolve Foundry-generated draft candidates into governed knowledge while preserving provenance, contradiction, review, rollback, local-first operation, human readability, and agent portability.

The design must answer which representation is authoritative when the same knowledge appears in:

- source artifacts;
- the epistemic ledger;
- concept/revision records;
- OKF Markdown;
- lexical indexes;
- vector stores;
- graph projections;
- caches and user interfaces.

Without an explicit decision, the system could acquire multiple competing sources of truth, silently lose evidence during Markdown edits, treat vector similarity as identity, or make an index corruption an epistemic data-loss event.

## Decision drivers

- Preserve the existing append-only epistemic ledger.
- Support atomic, concurrent, resumable local operation.
- Produce portable human/agent-readable OKF v0.2 bundles.
- Make publication reproducible and rollback-safe.
- Keep FTS/vector/graph components replaceable.
- Avoid remote graph infrastructure on the hot path.
- Prevent direct filesystem edits and model output from bypassing governance.
- Preserve a reversible path from the existing Python/SQLite kernel to future Rust components.
- Operate on Windows without Docker.

## Considered approaches

### Option A — Mutable OKF Markdown is the live authoritative store

Agents and humans edit one corpus directory directly. SQLite and indexes observe or mirror the files.

#### Advantages

- immediately readable and portable;
- straightforward Git history;
- minimal database model;
- concept paths naturally form a graph.

#### Rejected because

- multi-record transitions cannot be atomic across files and the existing ledger;
- concurrent edits require a second conflict protocol;
- claim-level evidence and lifecycle transitions are difficult to preserve without hidden sidecar state;
- direct edits can bypass authority, review, and idempotency;
- rename/path changes conflate identity and presentation;
- crash recovery and current-state reconstruction become ambiguous;
- human-friendly frontmatter would be forced to carry operational details it was not designed to govern;
- last-write-wins filesystem behavior is unacceptable for contradictions and supersession.

### Option B — Append-only operational state with immutable OKF publication snapshots

SQLite and the existing epistemic ledger govern live evidence, decisions, reviews, claims, lifecycle, and publication receipts. A deterministic publisher emits immutable OKF v0.2 snapshots. Indexes are derived from a selected snapshot.

#### Advantages

- transactional integration with existing ledger and missions;
- append-only forensic history;
- exact authority and idempotency enforcement;
- immutable, reproducible publication artifacts;
- atomic current-pointer update and rollback;
- stable internal identity independent of path;
- clean distinction between truth state and publication lifecycle;
- indexes can be replaced or rebuilt;
- human edits can re-enter as candidates without losing authorship;
- supports future Rust components through language-neutral contracts.

#### Costs

- more contracts and migrations;
- a deterministic renderer and publication protocol are required;
- Markdown is not edited directly in the normal live path;
- operational database backup is required in addition to snapshot archival;
- publication may lag operational decisions until gates pass.

### Option C — Graph database is the live authoritative store

Claims, concepts, evidence, and lifecycle are represented primarily as graph nodes and edges; OKF and SQLite become projections.

#### Advantages

- natural relationship and multi-hop representation;
- mature graph query languages and visualization;
- flexible schema evolution.

#### Rejected because

- introduces a large infrastructure and operational dependency before demonstrated need;
- conflicts with the current one-SQLite local kernel and explicit Phase 1 non-goals;
- remote graph service would weaken offline/degraded operation;
- transactional integration with the existing ledger becomes more complex;
- graph stores do not remove the need for append-only evidence, publication, review, and projection contracts;
- portability and deterministic backup/restore become harder;
- the graph is useful as a projection but unnecessary as the primary authority.

## Decision

Adopt **Option B**.

### Authoritative-state rules

1. Content-addressed source artifacts are authoritative evidence bytes or immutable external evidence references.
2. The existing epistemic ledger is authoritative for proposition truth state and evidence transitions.
3. New append-only Phase 3 SQLite records are authoritative for candidates, reconciliation decisions, claim bindings, concept revisions, relationships, reviews, lifecycle transitions, publication intents, snapshots, publication receipts, channel-selection events, projection manifests, immutable evidence-packet retrieval receipts, and freshness assessments. Every authoritative append references the one global `knowledge_events.event_seq` order.
4. An immutable OKF snapshot is the authoritative portable publication for that exact snapshot ID and scope.
5. Each governed publication channel has its own mutable `current` pointer selecting one receipted published snapshot for that channel and scope; a pointer does not contain knowledge.
6. FTS, vector, graph, cache, API, UI, and model-context representations are derived projections.
7. Direct edits to a published or current OKF snapshot are prohibited. Human edits are imported as new source/candidate material.
8. Knowledge records cannot activate or modify mission, capability, tool, skill, policy, or credential authorities.

## Publication protocol consequence

Canonical publication is channel-relative snapshot membership, not a global concept lifecycle. It requires this exact per-channel order:

1. a SQLite prepare transaction appends the exact intent, generation-free expected prior-pointer payload, and separate expected generation; bootstrap alone permits null/generation 0 when no pointer or selection exists;
2. a new-snapshot intent renders two byte-identical roots, while rollback/reselection instead verifies an existing same-channel artifact and original materialization receipt;
3. only new-snapshot approval inserts one immutable snapshot/member set and artifact events;
4. only a new artifact is fsynced and atomically renamed on one filesystem, then reverified;
5. a SQLite transaction commits a new materialization or reselection receipt and future pointer-payload digest;
6. only then is the fsynced pointer temporary file atomically replaced and its directory fsynced;
7. pointer verification appends the channel-selection/activation event;
8. deterministic recovery handles every gap by event sequence, remains non-serving when bootstrap has no confirmed pointer, and reconstructs only a confirmed receipted pointer when one exists.

SQLite and filesystem actions are not atomic together. Safety comes from receipt-before-pointer ordering: `current` must never reference an unreceipted snapshot. `attempt_sequence`, immutable `snapshot_sequence`, and `pointer_generation` are independent channel-local counters. Rollback/reselection advances attempt and pointer counters through a new intent/receipt/selection chain while retaining the target's original snapshot counter; it never reinserts members or artifacts.

## Retrieval consequence

Retrieval must identify a publication channel, verify its exact receipted pointer and snapshot membership, and resolve active policy/registry/directives and authorized scope before querying projections. Internal lifecycle is quality metadata, not channel authorization. Each returned evidence packet is an immutable event-ordered retrieval receipt recording the publication receipt, snapshot counter, pointer generation, directive-set digest, and as-known event boundary. Projection scores are evidence about relevance only.

## Immediate serving-control consequence

Immutable snapshots remain historical publication authority, but authorized append-only serving directives may temporarily qualify, exclude, block, or suspend affected content per channel when a material invalidation is discovered before a corrected snapshot can be published. Minimum invalidation/apply/supersede/suspend behavior is mandatory before first current selection or retrieval. `supersedes_directive_id` creates an acyclic same-scope chain ordered by global `event_seq`; conflicting active leaves fail closed. The directive set is part of publication selection, retrieval authorization, and cache identity. It cannot rewrite claim truth state or snapshot bytes.

## Human-authoring consequence

The system remains human-authorable through a governed import round trip:

```text
published OKF snapshot
  -> human copy/edit
  -> source registration and diff
  -> candidate claims
  -> reconciliation/review/promotion
  -> new immutable snapshot
```

This is slower than direct editing but preserves identity, evidence, review, and rollback.

## Existing-system compatibility

- Existing `propositions`, `epistemic_evidence`, transition, confidence, and supersession records remain authoritative.
- Existing capability OKF manifests remain portable source documents for the capability graph; they are not automatically merged into Phase 3 canonical knowledge.
- Existing Foundry output remains draft candidate material.
- Existing sleep candidates can be bridged only through explicit import contracts.
- No current runtime behavior changes when this ADR lands.

## Migration strategy

1. Land design only.
2. Add source registry and candidates without changing any channel publication.
3. Add observation-only comparison and reconciliation proposals.
4. Add governed ledger binding.
5. Add concept/revision records.
6. Add review/lifecycle gates.
7. Add preview publication.
8. Enable receipt-first current pointer selection after every cross-resource failpoint test.
9. Add lexical, then vector/graph projections.

Each step is separately reversible as defined in the Phase 3 roadmap.

## Consequences

### Positive

- One authority per record class.
- Strong crash recovery and auditability.
- OKF remains portable and readable.
- Vector/graph technology can change without migration of truth.
- Contradictions and supersessions retain history.
- Publication rollback is a pointer/snapshot operation rather than destructive editing.
- Future native components can be introduced incrementally.

### Negative

- More schema and implementation work.
- Two forms of storage must be backed up: operational records/source artifacts and publication snapshots.
- Direct manual edits require an import/review cycle.
- Publication is eventually consistent with approved operational state.
- A renderer bug can affect publication, so reproducibility and validator diversity are mandatory.

## Rejected shortcuts

- Store only Markdown and infer decisions from Git history.
- Store only embeddings and regenerate prose when needed.
- Let the graph store be authoritative because it can represent links.
- Copy current ledger status into concept rows and treat it as authority.
- Permit human edits directly in the current snapshot.
- Use model consensus as publication approval.
- Rebuild canonical knowledge from conversation transcripts.

## Compliance tests

An implementation complies only when:

- deleting every projection leaves authoritative knowledge intact;
- two identical publication plans produce byte-identical snapshots;
- direct mutation of published snapshots is detected;
- current pointer references only a same-channel immutable snapshot with an already committed exact success receipt;
- claim status is reconstructed from the existing ledger;
- concept path rename preserves stable resource identity;
- human edits enter through candidates;
- scope filtering occurs before projection content is returned;
- rollback selects a prior immutable snapshot without deleting audit history;
- historical reconstruction uses global `event_seq`, never timestamp tie-breaking.

## 10th-Man countercase

This decision could over-engineer personal knowledge by introducing operational records and publication snapshots where a Git-managed Markdown directory might be sufficient.

The containment is staged implementation. Direct Markdown remains appropriate for manually maintained static knowledge. The operational architecture is promoted only when Erasmus must continuously reconcile model-produced candidates, claim-level evidence, contradictions, lifecycle, scope, and crash-consistent publication. If those failures are not observed, later increments remain deferred.
