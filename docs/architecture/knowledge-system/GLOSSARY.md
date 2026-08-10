# Phase 3 Knowledge-System Glossary

- **Version:** 1.0.0
- **Status:** Normative terminology for the deferred Phase 3 design

This glossary is normative. Where a term has multiple common meanings, the definition here controls Phase 3 contracts.

### Actor
A human, process, tool, model, or agent identity responsible for an auditable operation.

### Admission
The governed transition by which quarantined candidate material becomes eligible for reconciliation. Admission grants no truth or publication status.

### Alias
A non-authoritative label, acronym, prior name, path, identifier, misspelling, or display label associated with a stable entity. Alias similarity never merges entities by itself.

### Append-only
A persistence rule under which committed evidentiary and consequential records are never updated in place or deleted to change history; corrections occur through new records, transitions, supersession, tombstones, or directives.

### Attempt sequence
The channel-local `attempt_sequence` consumed by every publication intent, including failed, rollback, and reselection attempts. It is independent of snapshot identity and pointer activation.

### Authority
A capability-scoped permission to perform a consequential operation. Authority is explicit, independently evaluable, and cannot be inferred from model output, knowledge content, or similarity.

### Bitemporal knowledge
Knowledge interpreted with separate valid/effective time and transaction/as-known time, preventing later corrections from being represented as if they were known earlier.

### Binding
An explicit, auditable relationship joining two authoritative records, such as a candidate claim to an existing epistemic-ledger proposition.

### Candidate
Untrusted or unadmitted material proposed for possible reconciliation. Foundry documents remain external `status: draft` candidates until governed import and admission.

### Candidate disposition
The Phase 3 state plane describing whether candidate material is `quarantined`, `admissible`, `duplicate`, `insufficient_evidence`, or `rejected`.

### Canonical
Included in the current receipted immutable publication snapshot for one authorized publication channel and scope. This is a channel-relative relation, not an internal lifecycle or global property. Canonical publication does not imply that every contained claim is established or uncontested.

### Channel publication state
The derived relation `unpublished`, `current`, `historical`, or `withdrawn` for one revision and publication channel, computed from the verified receipted pointer and immutable snapshot membership.

### Claim
An atomic proposition capable of independent support, contradiction, falsification, qualification, or supersession.

### Claim epistemic state
The existing ledger truth-state vocabulary: `speculative`, `analogy`, `leap`, `unresolved`, `plausible`, `supported`, `established`, `contradicted`, or `falsified`.

### Comparison target
An existing claim or concept selected as a possible match for a candidate, together with exact, lexical, vector, graph, scope, and applicability evidence explaining its selection.

### Concept
A stable semantic subject that organizes claims and relationships. Concept identity is independent of title or path.

### Concept ID
In OKF, the bundle-relative file path without `.md`. Erasmus additionally uses a stable concept resource URN independent of the path.

### Concept lifecycle
Internal review-readiness and history: `provisional`, `reviewed`, `validated`, `contested`, `superseded`, `rejected`, or `deprecated`. `draft` is reserved for external Foundry candidate documents and is not an internal Phase 3 concept lifecycle state. Channel publication does not mutate this lifecycle.

### Concept revision
An immutable selected representation of one concept, containing exact claim and relationship IDs plus rendering metadata.

### Consequential knowledge
Knowledge that may materially influence engineering, financial, operational, security, health, legal, or deployment decisions.

### Consistency mode
The explicit read boundary selecting current publication, pinned snapshot, authorized operational review, candidate review, historical-as-known, or historical-valid-at state.

### Content address
Identity derived from a cryptographic digest of bytes or canonical content.

### Content digest
An algorithm, value, and canonicalization profile proving the identity of content.

### Context broker
The governed boundary that assembles bounded evidence packets for agents after authority, scope, lifecycle, freshness, contradiction, temporal, and serving-control checks.

### Contradiction set
A durable grouping of materially incompatible claims preserved without forcing premature resolution.

### Directive set
The active, scope/channel-specific collection of serving directives applied before knowledge enters caches or model context.

### Entity
A stable identified subject such as a person, organization, repository, model, component, asset, standard, or versioned object. Identity is governed separately from concept text.

### Epistemic ledger
The existing Erasmus append-only authority for proposition truth-state transitions. Phase 3 binds claims to it rather than replacing it.

### Evidence
A source span, observation, deterministic receipt, test result, or explicit human decision that can support an auditable claim or transition.

### Evidence independence
The requirement to distinguish genuinely independent corroboration from copies, mirrors, shared upstream sources, or mutually derived assertions.

### Evidence packet
An authoritative immutable retrieval receipt containing stable IDs plus source, truth, lifecycle, freshness, contradiction, temporal, scope, uncertainty, and serving-control metadata. It records its own global `event_seq`, the resolved `as_known_event_seq` boundary, and the exact receipted channel pointer used.

### Foundry
The bounded PDF-to-OKF process that emits external unverified `status: draft` candidate bundles. It does not promote or reconcile knowledge.

### Freshness
The state of recency or source availability relative to an explicit policy. Stale knowledge is not automatically false.

### Historical-as-known
A consistency mode reconstructing only records committed by a selected transaction sequence/time, without hindsight leakage from later corrections.

### Identity resolution
A governed decision such as `same_entity`, `distinct_entity`, `alias_of`, `successor_of`, `version_of`, `part_of`, or `unresolved`.

### Invalidation event
An append-only record that identifies material knowledge potentially made unsafe, stale, unavailable, contradicted, revoked, compromised, or policy-prohibited.

### Knowledge dependency
An authoritative append-only edge declaring that one consequential record materially depends on another. It supports impact analysis independently of rebuildable graph projections.

### Knowledge use receipt
An append-only record identifying the exact evidence packet, snapshot, claims, sources, directives, mission, and usage class involved in a mission or decision.

### Materiality
The significance of an error, omission, staleness, or invalidation relative to an explicit use/mission/risk class. Materiality does not change truth state.

### Open question
A governed unresolved inquiry with closure criteria, evidence state, related claims, optional child questions, and lifecycle transitions.

### Policy evaluation receipt
The deterministic record of the exact policy version/digest, request, matched rules, decision, required reviews/approvals, budgets, and reason codes for an operation.

### Pointer generation
The channel-local `pointer_generation` advanced only by a successful compare-and-swap of `current.json`. Bootstrap begins absent and non-serving at logical generation 0; the first verified selection is generation 1.

### Projection
A rebuildable derivative used for retrieval or presentation, including FTS, vector, graph, cache, API, or UI state. A projection is never epistemic authority.

### Snapshot sequence
The channel-local immutable `snapshot_sequence` allocated exactly once when a new snapshot artifact is created. Rollback or reselection retains the target artifact's original snapshot sequence while advancing attempt sequence and pointer generation.

### Publication channel
A governed audience/scope-specific publication surface with its own policy, renderer, immutable snapshots, projections, retention, and current pointer.

### Reconciliation
The governed process of deciding whether an admissible candidate claim creates, corroborates, amends, contradicts, supersedes, duplicates, rejects, or lacks sufficient evidence relative to existing knowledge.

### Registry snapshot
An immutable versioned semantic definition set controlling registered entity types, predicates, relationship types, source kinds, rendering profiles, and projection profiles.

### Review
An auditable independent assessment of a proposal, transition, promotion, synthesis, policy, registry, identity decision, or publication action.

### Serving directive
An authorized immediate operational control that can `qualify`, `exclude`, `block`, or `channel_suspend` affected knowledge before a corrected immutable snapshot is published. It does not rewrite truth or history.

### Snapshot
An immutable deterministic OKF publication artifact for one publication channel and scope, accompanied by a manifest and publication receipt.

### Source artifact
Immutable source bytes identified by content digest and acquisition provenance.

### Source span
A stable reference to a bounded portion of a source artifact, such as PDF pages or character/line coordinates, used as claim evidence.

### Synthesis
A governed derived explanation or composition whose material statements map to exact claims/evidence or are explicitly labeled as interpretation.

### Transaction time
The global SQLite `event_seq` at which Erasmus committed an authoritative Phase 3 append. It is the total-order boundary for “what was known then”; timestamps remain temporal facts only.

### Truth state
The proposition-level epistemic state owned exclusively by the existing epistemic ledger. It is not candidate disposition, concept lifecycle, freshness, publication state, or projection state.

### Uncertainty
A typed representation of what is unknown or variable. Measurement, aleatoric, model, semantic, identity, scope, temporal, evidence-sufficiency, freshness, retrieval, synthesis, and operational uncertainty are not collapsed into one universal scalar.

### Valid time
The time interval during which a source or claim says its content applies, distinct from when Erasmus recorded it.

### Verification
An independently governed determination supported by declared evidence. Model generation, repetition, retrieval rank, or agreement alone is not verification.
