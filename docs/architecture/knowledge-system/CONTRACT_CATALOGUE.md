# Phase 3 Knowledge Contract Catalogue

- **Version:** 1.0.0
- **Status:** Accepted target contracts; experimental and non-runtime
- **Runtime registration:** None
- **Promotion requirement:** Each contract family requires a separate bounded implementation mission, JSON Schema finalization, migrations, deterministic and negative tests, compatibility evidence, rollback, and 10th-Man review

The existing Erasmus mission, capability, tool, runtime, sleep, immune, skill, and epistemic-ledger contracts remain authoritative. This catalogue defines future Phase 3 boundaries and explicitly maps them onto existing records rather than replacing them.

## 1. Contract design rules

All promoted contracts shall be:

- namespaced and versioned;
- serializable as canonical JSON at persistence and IPC boundaries;
- representable as Rust types and Python dataclasses without semantic loss;
- JSON-Schema validated where JSON crosses a boundary;
- immutable after emission when the record is evidentiary or consequential;
- backward-compatible or introduced through an explicit migration;
- independently identifiable through stable URNs;
- scoped and authorization-aware;
- linked by stable IDs rather than copied narrative text;
- explicit about idempotency, side effects, retry, timeout, and rollback;
- tolerant of unknown extension fields only where the contract declares extension support;
- subordinate to the current immutable constitution and existing ledger semantics.

## 2. Contract families

1. `SourceArtifact`
2. `SourceSpan`
3. `ExtractionReceipt`
4. `IngestionRun`
5. `CandidateConcept`
6. `CandidateClaim`
7. `ComparisonTarget`
8. `ReconciliationProposal`
9. `ReconciliationDecision`
10. `KnowledgeConcept`
11. `ConceptRevision`
12. `KnowledgeRelationship`
13. `LedgerClaimBinding`
14. `ReviewRecord`
15. `PromotionDecision`
16. `PublicationPlan`
17. `CanonicalSnapshot`
18. `PublicationReceipt`
19. `ProjectionManifest`
20. `RetrievalRequest`
21. `EvidencePacket`
22. `FreshnessAssessment`
23. `RevalidationRequest`
24. `OpenQuestion`
25. `QuestionTransition`
26. `SynthesisRecord`
27. `SynthesisTransition`
28. `KnowledgeAuditEvent`
29. `KnowledgeMutationCommand`
30. `KnowledgePolicySet`
31. `KnowledgePolicyRule`
32. `PolicyEvaluationReceipt`
33. `EntityRecord`
34. `EntityAlias`
35. `IdentityResolutionProposal`
36. `IdentityResolutionDecision`
37. `SemanticRegistrySnapshot`
38. `EntityTypeDefinition`
39. `ConceptTypeDefinition`
40. `PredicateDefinition`
41. `RelationshipTypeDefinition`
42. `SourceKindDefinition`
43. `RenderingProfile`
44. `ProjectionProfile`
45. `PublicationChannel`
46. `KnowledgeRequest`
47. `KnowledgeResponse`
48. `KnowledgeJob`
49. `KnowledgeProgressEvent`
50. `UncertaintyRecord`
51. `MaterialityAssessment`
52. `KnowledgeDependency`
53. `KnowledgeUseReceipt`
54. `InvalidationEvent`
55. `ImpactAnalysis`
56. `ServingDirective`

Publication also uses immutable `PublicationIntent`, `SnapshotEvent`, and `ChannelSelectionEvent` records; these are distinct from the immutable snapshot artifact and `PublicationReceipt`.

Experimental schema seeds are split by responsibility:

- [`schemas/knowledge-system.schema.json`](schemas/knowledge-system.schema.json) covers the principal source, candidate, claim, concept, review, publication, projection, retrieval, and mutation contracts.
- [`schemas/question-synthesis.schema.json`](schemas/question-synthesis.schema.json) covers open-question and synthesis records and transitions.
- [`schemas/governance-registry.schema.json`](schemas/governance-registry.schema.json) covers policy evaluation, stable entities, identity resolution, semantic registries, relationship definitions, and publication channels.
- [`schemas/impact-serving.schema.json`](schemas/impact-serving.schema.json) covers typed uncertainty, materiality, authoritative dependencies, use receipts, invalidation, impact, and serving directives.
- [`schemas/operator-api.schema.json`](schemas/operator-api.schema.json) covers transport-neutral requests/responses, durable jobs, progress events, budgets, and typed failures.

All schemas are design fixtures and must not be imported by the live runtime. Cross-cutting normative behavior is defined in [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) and [`OPERATOR_API_AND_RUNBOOK.md`](OPERATOR_API_AND_RUNBOOK.md).

## 3. Common primitives

### 3.1 `StableId`

```text
String matching ^urn:erasmus:[a-z][a-z0-9-]*:[A-Za-z0-9._:-]+$
```

A stable ID is immutable. Human-readable titles and paths are not IDs.

### 3.1A `EventSequence`

Every authoritative append-only Phase 3 record carries `event_seq`, a positive integer foreign key to the single SQLite `knowledge_events` order. The event and domain record commit in the same transaction. Domain sequences and timestamps are facts only; historical reconstruction uses global `event_seq`.

### 3.2 `Actor`

Use the OKF actor convention and existing Erasmus role identities:

```text
human:<opaque-id>
process:<name>/<version>
agent:<role>/<version>
model:<model-id>
tool:<tool-id>/<version>
```

Public repositories must use non-identifying role IDs unless publication is explicitly approved.

### 3.3 `Authority`

A non-empty namespaced string such as `knowledge:review`. Authority is granted externally through mission and policy records. A record carrying an authority string does not prove the actor possessed it; execution receipts must establish that.

### 3.4 `Scope`

```json
{
  "visibility": "private | project | shared | public",
  "tenant": "local-user-or-deployment-id",
  "project": "optional-project-id",
  "domain": "optional-domain-id",
  "labels": ["optional", "policy-labels"]
}
```

Scope equality and compatibility are deterministic policy operations. Scope must be applied before retrieval and publication.

### 3.5 `RiskClass`

```text
routine | consequential | protected
```

### 3.6 `ContentDigest`

```json
{
  "algorithm": "sha256",
  "value": "64 lowercase hexadecimal characters",
  "canonicalization": "raw-bytes | canonical-json/v1 | okf-markdown/v1"
}
```

### 3.7 `Coordinate`

A source-kind-specific coordinate:

```json
{
  "kind": "pdf-pages",
  "start_page": 12,
  "end_page": 14,
  "start_char": 0,
  "end_char": 4312
}
```

Other allowed kinds are introduced through versioned schema additions, for example `text-lines`, `html-selector`, `database-row`, `git-range`, `image-region`, or `media-time`.

## 4. Source and ingestion contracts

### 4.1 `SourceArtifact`

Purpose: immutable identity and governance metadata for source material.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `source_id` | `StableId` | `urn:erasmus:source:<sha256>` |
| `digest` | `ContentDigest` | Digest of source bytes |
| `media_type` | string | Declared media type |
| `byte_size` | integer | Exact source size |
| `source_kind` | enum | `document`, `web`, `repository`, `database`, `observation`, `tool_receipt`, `human`, `model`, `other` |
| `locator` | string | Original path or URI; not identity |
| `scope` | `Scope` | Access and publication scope |
| `acquired_at` | ISO 8601 | Acquisition time |
| `acquired_by` | `Actor` | Acquisition actor |
| `storage_state` | enum | `available`, `external`, `tombstoned`, `removed` |
| `metadata` | object | Source-kind metadata with no authority semantics |
| `event_seq` | positive integer | Global authoritative event order |

Invariants:

- `source_id` must match the digest.
- A changed byte stream is a new source artifact even when the locator is unchanged.
- `locator` may be redacted in published projections.
- A tombstoned source retains its digest, scope, reason, and audit record but not necessarily its bytes.
- Source content never carries execution authority.

### 4.2 `SourceSpan`

Purpose: reproducible location of evidence inside a source.

Required fields:

| Field | Type |
|---|---|
| `span_id` | `StableId` |
| `source_id` | `StableId` |
| `coordinate` | `Coordinate` |
| `text_digest` | `ContentDigest` |
| `extracted_text` | string or protected external reference |
| `extraction_receipt_id` | `StableId` |
| `scope` | `Scope` |
| `event_seq` | positive integer |

Invariants:

- `span_id` is deterministic from source ID, canonical coordinate, and text digest.
- The extracted text digest must be reproducible from the extraction receipt.
- A span cannot broaden source scope.
- A span does not claim the extracted statement is true.

### 4.3 `ExtractionReceipt`

Purpose: deterministic evidence of how source content became machine-readable text or structure.

Required fields:

```json
{
  "receipt_id": "urn:erasmus:extraction-receipt:<uuid>",
  "source_id": "urn:erasmus:source:<sha256>",
  "extractor": {
    "implementation_id": "pypdf",
    "version": "5.x",
    "digest": "optional executable/package digest"
  },
  "options": {},
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "status": "success | partial | failure",
  "event_seq": 31,
  "page_or_object_count": 10,
  "textless_or_failed_coordinates": [],
  "output_digest": {
    "algorithm": "sha256",
    "value": "...",
    "canonicalization": "canonical-json/v1"
  },
  "failure": null
}
```

### 4.4 `IngestionRun`

Purpose: resumable, bounded processing of one or more sources.

Key fields:

- `run_id`
- `mission_id`
- `idempotency_key`
- `source_ids`
- `producer_profile`
- `runtime_identity`
- `budgets`
- `status`: `proposed`, `running`, `completed`, `partial`, `failed`, `cancelled`
- `checkpoint`
- `candidate_ids`
- `failure`
- timestamps

The same idempotency key and unchanged source digests must not create duplicate candidates.

## 5. Candidate contracts

### 5.1 `CandidateConcept`

Purpose: quarantined semantic grouping proposed by a producer.

Required fields:

| Field | Type |
|---|---|
| `candidate_id` | `StableId` |
| `producer` | `Actor` |
| `producer_profile` | string/version |
| `title` | string |
| `proposed_type` | string |
| `description` | string |
| `body` | string |
| `tags` | string array |
| `source_span_ids` | stable-ID array |
| `candidate_claim_ids` | stable-ID array |
| `related_candidate_ids` | stable-ID array |
| `scope` | `Scope` |
| `risk_class` | `RiskClass` |
| `disposition` | candidate-disposition enum |
| `content_digest` | `ContentDigest` |
| `created_at` | ISO 8601 |

Invariants:

- initial disposition is `quarantined`;
- `verified` is prohibited;
- a candidate cannot reference a broader scope than all supporting spans permit;
- a candidate may be discarded without altering any current channel publication;
- candidate body text is never the unit of epistemic promotion; candidate claims are.

### 5.2 `CandidateClaim`

Purpose: atomic assertion extracted or proposed from candidate material.

Required fields:

```json
{
  "candidate_claim_id": "urn:erasmus:candidate-claim:<uuid>",
  "candidate_id": "urn:erasmus:candidate:<uuid>",
  "statement": "Atomic declarative proposition",
  "subject": "optional stable entity or concept reference",
  "predicate": "namespaced predicate",
  "object": "typed literal or stable reference",
  "qualifiers": {
    "temporal": {},
    "environment": {},
    "applicability": {},
    "units": null,
    "uncertainty": null
  },
  "source_span_ids": ["urn:erasmus:span:..."],
  "scope": {},
  "risk_class": "routine",
  "content_digest": {},
  "event_seq": 32,
  "created_at": "ISO-8601"
}
```

Rules:

- A claim must be narrow enough to admit support or contradiction.
- Units, coordinate frames, model/runtime/hardware context, and temporal applicability are mandatory when material.
- The same words under incompatible qualifiers are not duplicates.
- Candidate claims remain untrusted until a reconciliation decision and required review exist.

## 6. Comparison and reconciliation contracts

### 6.1 `ComparisonTarget`

Purpose: record why an existing claim or concept was selected for comparison.

Fields:

- target claim/concept ID;
- target revision and snapshot;
- exact-match signals;
- lexical score;
- vector score and embedding identity;
- graph path and edge types;
- scope compatibility;
- temporal compatibility;
- applicability compatibility;
- selected-source independence;
- retrieval reason codes;
- rank.

Comparison targets are evidence about search, not evidence that two claims are equivalent.

### 6.2 `ReconciliationProposal`

Purpose: bounded semantic and deterministic proposal before authority is applied.

```json
{
  "proposal_id": "urn:erasmus:reconciliation-proposal:<uuid>",
  "candidate_claim_id": "...",
  "comparison_targets": [],
  "proposed_action": "create | corroborate | amend | contradict | supersede | duplicate | reject | insufficient_evidence",
  "proposed_target_ids": [],
  "reason_codes": [],
  "structured_rationale": "No hidden chain of thought",
  "deterministic_checks": [],
  "model_identity": null,
  "confidence": 0.0,
  "event_seq": 33,
  "created_at": "ISO-8601"
}
```

The proposal has no side effect.

### 6.3 `ReconciliationDecision`

Purpose: authoritative, immutable decision after policy and review.

Required fields:

| Field | Meaning |
|---|---|
| `decision_id` | Stable decision identity |
| `proposal_id` | Proposal under review |
| `action` | Final action enum |
| `candidate_claim_id` | Input candidate claim |
| `target_claim_ids` | Existing claims affected |
| `target_concept_ids` | Existing concepts affected |
| `evidence_ids` | Existing ledger evidence or newly admitted evidence |
| `review_ids` | Completed required reviews |
| `policy_version` | Exact policy used |
| `actor` | Deciding actor |
| `authority` | Exact authority |
| `mission_id` | Governing mission |
| `idempotency_key` | Duplicate-command protection |
| `structured_rationale` | Evidence-based summary |
| `event_seq` | Global authoritative event order |
| `created_at` | Commit time |

Invariants:

- immutable after commit;
- cannot use the proposal producer as the only reviewer;
- `contradict` and `supersede` require explicit targets;
- `corroborate` requires independent evidence not already attached to the target claim;
- `duplicate` creates no new ledger proposition;
- `insufficient_evidence` preserves the candidate for future review without promotion;
- decision actor must possess `knowledge:reconcile` or stronger authority under policy.

## 7. Canonical concept contracts

### 7.1 `KnowledgeConcept`

Purpose: stable semantic subject independent of any one revision.

Fields:

```json
{
  "concept_id": "urn:erasmus:concept:<uuid>",
  "event_seq": 34,
  "created_at": "ISO-8601",
  "created_by": "Actor",
  "scope": {},
  "risk_class": "routine | consequential | protected",
  "current_revision_id": "urn:erasmus:concept-revision:<uuid>",
  "lifecycle": "provisional | reviewed | validated | contested | superseded | rejected | deprecated",
  "superseded_by": null,
  "canonical_path": "domain/concept-name",
  "prior_paths": [],
  "version": 1
}
```

The row identifying the concept may be immutable except for a current-state projection; authoritative lifecycle and revision history are append-only records. Current publication is separately derived per channel from a verified receipted pointer and snapshot membership.

### 7.2 `ConceptRevision`

Purpose: immutable selected representation of a concept at one point in history.

Required fields:

- `revision_id`;
- `concept_id`;
- monotonic `revision_number`;
- `parent_revision_id`;
- `expected_parent_revision_id` supplied by the command;
- title, description, type, tags;
- ordered claim IDs;
- relationship IDs;
- applicability and exclusions;
- target OKF path;
- rendering-profile version;
- content digest;
- generation actor and time;
- review and decision references.

A revision conflict fails closed. A merge requires an explicit reconciliation command producing a new revision.

### 7.3 `KnowledgeRelationship`

Purpose: typed edge between durable objects.

```json
{
  "relationship_id": "urn:erasmus:relationship:<uuid>",
  "from_id": "StableId",
  "type": "erasmus.relationship/<name>/v1",
  "to_id": "StableId",
  "qualifiers": {},
  "evidence_ids": [],
  "scope": {},
  "created_by": "Actor",
  "created_at": "ISO-8601",
  "supersedes_relationship_id": null
}
```

Execution-sensitive relationship types require registration in a separately authorized relationship registry. An unknown relationship is descriptive only.

### 7.4 `LedgerClaimBinding`

Purpose: link a Phase 3 claim identity to the existing epistemic-ledger proposition without duplicating truth state.

Fields:

- `claim_id`;
- `proposition_id`;
- normalized statement digest;
- binding decision ID;
- scope;
- global `event_seq`;
- created time.

Rules:

- one active claim binding points to one proposition;
- equivalent claims may bind to the same proposition only after reconciliation;
- current proposition status is read from the ledger transition history;
- concept storage may cache status for display but must identify it as a projection.

## 7A. Open-question and synthesis contracts

`OpenQuestion`, `QuestionTransition`, `SynthesisRecord`, and `SynthesisTransition` are defined normatively in [`OPEN_QUESTIONS_AND_SYNTHESIS.md`](OPEN_QUESTIONS_AND_SYNTHESIS.md) and seeded in [`schemas/question-synthesis.schema.json`](schemas/question-synthesis.schema.json).

Open questions record bounded evidence gaps and closure requirements. Hypotheses reuse existing ledger propositions. Syntheses are derived artifacts bound to exact input claims, revisions, contradiction sets, source spans, and a snapshot; they cannot upgrade truth state or introduce unsupported bridge claims.

## 7B. Uncertainty, impact, and serving-control contracts

`UncertaintyRecord`, `MaterialityAssessment`, `KnowledgeDependency`, `KnowledgeUseReceipt`, `InvalidationEvent`, `ImpactAnalysis`, and `ServingDirective` are defined normatively in [`UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md`](UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md) and seeded in [`schemas/impact-serving.schema.json`](schemas/impact-serving.schema.json).

These records are append-only. `ServingDirective.supersedes_directive_id` is required and nullable only for an initial directive; replacements and retirement/`allow` successors form an acyclic same-subject/channel/scope chain ordered by global `event_seq`. Conflicting active leaves fail closed. Serving directives constrain retrieval and publication channels but never mutate claim truth, concept lifecycle, or historical snapshots. A final impact analysis reconciles against authoritative dependencies even when graph projections accelerate traversal.

## 8. Review and promotion contracts

### 8.1 `ReviewRecord`

```json
{
  "review_id": "urn:erasmus:review:<uuid>",
  "review_type": "deterministic | independent_model | domain | security_privacy | tenth_man | human",
  "subject_ids": [],
  "reviewer": "Actor",
  "independence_key": "producer/reviewer separation evidence",
  "inputs_digest": {},
  "verdict": "pass | pass_with_conditions | fail | insufficient_evidence",
  "findings": [],
  "required_actions": [],
  "evidence_ids": [],
  "policy_version": "...",
  "event_seq": 35,
  "created_at": "ISO-8601"
}
```

A review is append-only. A corrected subject requires a new review; prior failed reviews remain visible.

### 8.2 `PromotionDecision`

Purpose: append an internal lifecycle or snapshot-event transition after all gates are satisfied. Channel publication selection uses its separate receipt-first event contract.

Fields:

- decision ID;
- subject concept/revision/snapshot;
- prior state;
- target state;
- evidence IDs;
- review IDs;
- deterministic gate receipts;
- actor and authority;
- human approval ID where required;
- 10th-Man review ID where required;
- risk class;
- policy version;
- rollback target;
- reason;
- global `event_seq`;
- timestamp.

The promotion service recalculates gates from referenced records. It does not trust the command's assertion that gates passed.

## 9. Publication contracts

### 9.1 `PublicationPlan`

Purpose: complete deterministic build plan before filesystem writes.

Contains:

- plan ID;
- base snapshot ID;
- target snapshot ID;
- exact concept revision IDs;
- exact source references included;
- renderer and validator versions;
- target root;
- expected document paths and digests;
- redirect/alias paths;
- scope and publication audience;
- required approval records;
- rollback snapshot ID.

### 9.2 Publication counter vocabulary

- `attempt_sequence` is a per-channel counter consumed by every immutable `PublicationIntent`, including failed materialization attempts and rollback/reselection attempts.
- `snapshot_sequence` is a per-channel immutable artifact identity allocated once for a new `CanonicalSnapshot`. Reselecting an old snapshot retains its original value.
- `pointer_generation` is a per-channel compare-and-swap generation advanced only by a successful pointer replacement.

These counters are machine-readable and independent. No contract contains a generic publication `sequence`, and no equality is inferred between these three counters.

### 9.3 `PublicationIntent`

Required fields include `intent_id`, `channel_id`, `attempt_sequence`, `intent_kind`, `selection_kind`, proposed `target_snapshot_id`, reserved `snapshot_sequence`, complete nullable generation-free `expected_prior_pointer_payload`, required `expected_prior_pointer_generation`, nullable `exact_plan`, nullable `target_materialization_receipt_id`, `event_seq`, and creation time. The payload contains every exact prior `current.json` identity field except `pointer_generation`; the separate generation field is authoritative and an embedded generation is rejected.

`intent_kind = new_snapshot` requires `selection_kind = publish`, an exact non-null plan, and a null target materialization receipt. `intent_kind = reselect_existing` requires `selection_kind = rollback | reselect`, a null plan, and the original verified materialization receipt for the same-channel target. A null expected prior payload is legal only for an unselected channel and requires generation 0; a non-null payload requires its separate exact generation of at least 1.

### 9.4 `CanonicalSnapshot`

```json
{
  "snapshot_id": "urn:erasmus:snapshot:<uuid>",
  "creating_intent_id": "urn:erasmus:publication-intent:<uuid>",
  "channel_id": "urn:erasmus:publication-channel:private-default",
  "snapshot_sequence": 42,
  "parent_snapshot_id": "urn:erasmus:snapshot:<uuid>",
  "scope": {},
  "concept_revision_ids": [],
  "manifest_digest": {},
  "root_path": "local immutable snapshot path",
  "event_seq": 100,
  "created_at": "ISO-8601"
}
```

The base snapshot is inserted exactly once by its creating intent. `prepared`, `validated`, `approved`, `materialized`, and `failed` are append-only artifact `SnapshotEvent` values, not mutable snapshot columns. Receipt and channel activation are separate state planes and do not create snapshot events. Rollback/reselection does not insert a new snapshot or member row and does not change `snapshot_sequence`.

### 9.5 `PublicationReceipt`

Fields:

- receipt and publication-intent IDs, with one terminal receipt per intent;
- `receipt_kind = materialization | reselection`;
- channel ID and `attempt_sequence`;
- nullable target snapshot ID and `snapshot_sequence`, which are mandatory and FK-checked for success but may both be null for a pre-artifact failure;
- `expected_prior_pointer_generation` plus nullable `next_pointer_generation`;
- publisher implementation/version/digest;
- validator implementation/version/digest;
- file count;
- document digests;
- internal-link result;
- OKF conformance result;
- secret/privacy scan result;
- deterministic rebuild comparison result;
- exact manifest and future pointer-payload digests;
- duration;
- fixed `success` or `failure` status and typed failure;
- global event sequence.

A success receipt requires non-null snapshot ID/sequence, manifest and future-pointer digests, `next_pointer_generation = expected_prior_pointer_generation + 1`, and `failure = null`. Only success is eligible for selection, is durably committed before `current.json` can name it, and does not claim the pointer already moved. A failure receipt requires the complete typed failure, has no next pointer generation, and may record its artifact fields as null when failure precedes snapshot creation; it never creates selection authority or a snapshot event without a snapshot row. Publisher, validator, results, and evidence objects remain deterministic on both branches. `ChannelSelectionEvent` records the later verified pointer generation for success only. Rollback is a new intent/receipt/selection chain targeting a prior receipted snapshot.

### 9.6 `ChannelSelectionEvent` and current pointer

The append-only event requires selection-event and intent IDs, channel ID, snapshot ID, immutable `snapshot_sequence`, publication-receipt ID plus constant receipt status `success`, `attempt_sequence`, selection kind, nullable prior snapshot ID, `prior_pointer_generation`, new `pointer_generation`, exact pointer digest, `event_seq`, and creation time. The composite receipt/status FK makes failure receipts non-selectable. `(channel_id, pointer_generation)` and intent ID are unique. Bootstrap requires prior snapshot null, prior generation 0, and new generation 1; later selections require a complete prior pointer/generation and advance exactly once.

`current.json` is the exact payload pre-digested by the receipt:

```json
{
  "channel_id": "urn:erasmus:publication-channel:private-default",
  "snapshot_id": "urn:erasmus:snapshot:<uuid>",
  "snapshot_sequence": 1,
  "receipt_id": "urn:erasmus:publication-receipt:<uuid>",
  "intent_id": "urn:erasmus:publication-intent:<uuid>",
  "attempt_sequence": 3,
  "pointer_generation": 3,
  "manifest_digest": {},
  "policy_id": "...",
  "policy_version": "...",
  "registry_snapshot_id": "..."
}
```

For example, publishing S1, publishing S2, then rolling back to S1 yields snapshot sequences `1,2,1`, attempt sequences `1,2,3`, and pointer generations `1,2,3`; only two immutable snapshot rows exist.

## 10. Projection and retrieval contracts

### 10.1 `ProjectionManifest`

```json
{
  "projection_id": "urn:erasmus:projection:<uuid>",
  "kind": "fts | vector | graph | cache | ui",
  "source_snapshot_id": "urn:erasmus:snapshot:<uuid>",
  "builder": {"id": "...", "version": "...", "digest": "..."},
  "configuration": {},
  "model_identity": null,
  "scope": {},
  "status": "queued | building | ready | failed | stale | retired",
  "artifact_digest": {},
  "event_seq": 36,
  "created_at": "ISO-8601",
  "completed_at": null,
  "failure": null
}
```

Projection readiness never changes source snapshot status.

### 10.2 `RetrievalRequest`

Required fields:

- request ID;
- query text or structured query;
- actor;
- authorized scope;
- project/domain/applicability constraints;
- optional internal lifecycle quality constraints, never channel authorization;
- stale/contested handling policy;
- retrieval modes;
- per-mode limits;
- total evidence/token budget;
- snapshot selector, normally current published snapshot;
- required source kinds or trust signals;
- timeout and cancellation token.

### 10.3 `EvidencePacket`

```json
{
  "packet_id": "urn:erasmus:evidence-packet:<uuid>",
  "request_id": "...",
  "channel_id": "urn:erasmus:publication-channel:private-default",
  "snapshot_id": "...",
  "snapshot_sequence": 1,
  "publication_receipt_id": "urn:erasmus:publication-receipt:<uuid>",
  "pointer_generation": 3,
  "directive_set_digest": {},
  "as_known_event_seq": 104,
  "items": [
    {
      "claim_id": "...",
      "proposition_id": 123,
      "concept_id": "...",
      "concept_path": "...",
      "selected_text": "...",
      "epistemic_status": "supported",
      "concept_lifecycle": "validated",
      "channel_publication_state": "current",
      "freshness": "current | stale | unknown",
      "contested": false,
      "source_refs": [],
      "retrieval_features": {
        "lexical": null,
        "vector": null,
        "graph": null,
        "rerank": null
      }
    }
  ],
  "omitted": {"count": 0, "reasons": []},
  "budget": {"used": 0, "limit": 0},
  "event_seq": 106,
  "created_at": "ISO-8601"
}
```

The packet is reference context only and carries no instruction authority. It is also an authoritative immutable retrieval receipt: its `event_seq` orders persistence, while `as_known_event_seq <= event_seq` records the resolved query boundary. Canonical packet bytes/digest are persisted so a later `KnowledgeUseReceipt` can reproduce the exact channel, snapshot, receipt, pointer generation, and directive set used.

## 11. Freshness contracts

### 11.1 `FreshnessAssessment`

Fields:

- assessment ID;
- subject claim/concept/source IDs;
- source last-modified signals;
- `generated.at`, verification events, and `stale_after`;
- environment/applicability drift signals;
- status: `current`, `approaching_stale`, `stale`, `unknown`, `source_unavailable`;
- reason codes;
- assessor and deterministic receipt;
- recommended action.

### 11.2 `RevalidationRequest`

A revalidation request is a bounded mission candidate, not an automatic state mutation. It declares subject IDs, reason, required sources, validators, risk class, deadline, retry budget, and the fallback behavior if revalidation cannot complete.

## 12. Mutation and audit contracts

### 12.1 `KnowledgeMutationCommand`

```json
{
  "command_id": "urn:erasmus:knowledge-command:<uuid>",
  "idempotency_key": "caller-defined stable key",
  "mission_id": 0,
  "actor": "Actor",
  "authority": "knowledge:...",
  "operation": "namespaced operation",
  "target_ids": [],
  "expected_revisions": {},
  "evidence_ids": [],
  "review_ids": [],
  "policy_version": "...",
  "rollback_ref": "...",
  "requested_at": "ISO-8601"
}
```

### 12.2 `KnowledgeAuditEvent`

Every accepted or rejected command emits an immutable event:

- event ID;
- command ID;
- operation;
- actor and authority result;
- prior and resulting IDs/states;
- evidence/review references;
- deterministic check receipts;
- result: `success`, `failure`, `denied`, `no_op`;
- structured failure code;
- timestamp and duration.

## 13. Error taxonomy

Minimum typed errors:

- `invalid_contract`
- `invalid_source_digest`
- `source_unavailable`
- `source_scope_violation`
- `span_not_reproducible`
- `candidate_quarantined`
- `candidate_schema_violation`
- `candidate_budget_exceeded`
- `comparison_ambiguous`
- `scope_incompatible`
- `temporal_scope_incompatible`
- `applicability_incompatible`
- `independence_violation`
- `insufficient_evidence`
- `contradiction_unresolved`
- `invalid_reconciliation_action`
- `ledger_transition_rejected`
- `revision_conflict`
- `relationship_type_unregistered`
- `authority_denied`
- `human_approval_required`
- `tenth_man_required`
- `publication_validation_failed`
- `publication_non_deterministic`
- `snapshot_conflict`
- `projection_snapshot_mismatch`
- `projection_stale`
- `retrieval_scope_violation`
- `context_budget_exceeded`
- `freshness_unknown`
- `rollback_unavailable`
- `idempotency_conflict`
- `cancelled`
- `timeout`

Every error includes `code`, human-readable `message`, machine-readable `details`, `retryable`, `action`, and related record IDs.

## 14. Target capability contracts

The following capabilities are future design targets and are not registered:

| Capability | Classification | Side effects |
|---|---|---|
| `register_source_artifact` | deterministic | source metadata write |
| `extract_source_spans` | deterministic | span/receipt writes |
| `import_foundry_candidates` | deterministic | quarantine writes |
| `decompose_candidate_claims` | semantic with schema validation | candidate-claim writes |
| `retrieve_comparison_targets` | deterministic/statistical | none |
| `propose_reconciliation` | semantic | proposal write |
| `decide_reconciliation` | governed deterministic policy | ledger/concept writes |
| `record_knowledge_review` | governed | review write |
| `promote_concept_lifecycle` | governed deterministic policy | lifecycle transition |
| `plan_okf_snapshot` | deterministic | plan write |
| `publish_okf_snapshot` | deterministic side effect | immutable filesystem publication |
| `build_knowledge_projection` | deterministic/statistical | derived artifact write |
| `retrieve_knowledge_evidence` | deterministic/statistical read | none |
| `assess_knowledge_freshness` | deterministic/statistical | assessment write |
| `record_open_question` | governed | open-question write |
| `transition_open_question` | governed | question transition |
| `produce_knowledge_synthesis` | semantic with strict grounding contract | provisional synthesis write |
| `review_knowledge_synthesis` | governed/deterministic | synthesis review/transition |
| `request_revalidation` | governed | mission candidate write |
| `withdraw_snapshot` | governed consequential | current-pointer change |

Each capability shall define exact ports, authority, evidence, rollback, cost, and 10th-Man triggers using the existing Erasmus capability-contract profile when implemented.

## 15. Compatibility with existing Erasmus records

| Phase 3 record | Existing authority reused |
|---|---|
| Source-derived evidence | `epistemic_evidence` |
| Claim truth state | `propositions`, `proposition_transitions`, `confidence_history` |
| Contradiction/falsification | existing ledger operations |
| Claim supersession | `proposition_supersessions` |
| Mission authorization | `missions`, `mission_approvals`, `mission_transitions` |
| Deterministic execution receipts | `capability_invocations`, `capability_evidence` |
| Candidate experience | `sleep_candidates` where applicable, bridged explicitly |
| Skills | existing skill lifecycle; never promoted through knowledge contracts |
| Capabilities/tools | existing registries; knowledge remains descriptive |

Phase 3 introduces concept, revision, relationship, review, publication, projection, and freshness records because those responsibilities do not currently exist. It does not duplicate ledger truth state.

## 16. Illustrative typed boundary

The implementation language may differ, but the boundary shall remain equivalent to this Rust-style example:

```rust
/// Immutable command accepted by the knowledge control plane.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ReconciliationDecisionV1 {
    /// Globally stable decision identity.
    pub decision_id: String,
    /// Candidate claim being reconciled.
    pub candidate_claim_id: String,
    /// Final governed action; never arbitrary model text.
    pub action: ReconciliationActionV1,
    /// Existing claims affected by the decision.
    pub target_claim_ids: Vec<String>,
    /// Evidence already admitted to the Erasmus ledger.
    pub evidence_ids: Vec<i64>,
    /// Immutable reviews satisfying policy gates.
    pub review_ids: Vec<String>,
    /// Exact policy evaluated by the decision service.
    pub policy_version: String,
    /// Actor and authority are explicit; no inherited authority.
    pub actor: String,
    pub authority: String,
    /// Mission is required for consequential work.
    pub mission_id: i64,
    /// Repeated delivery of the same command is a no-op, not a duplicate write.
    pub idempotency_key: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ReconciliationActionV1 {
    Create,
    Corroborate,
    Amend,
    Contradict,
    Supersede,
    Duplicate,
    Reject,
    InsufficientEvidence,
}
```

## 17. Contract acceptance gate

A contract is ready for runtime promotion only when:

1. Its responsibility does not overlap an existing authority.
2. JSON Schema and language types agree exactly.
3. Canonical serialization and digest tests pass.
4. Unknown-field and version behavior are explicit.
5. Positive, negative, malformed, boundary, and compatibility fixtures exist.
6. Authorization, scope, idempotency, retry, timeout, and rollback are declared.
7. SQLite migration and downgrade/rollback behavior are tested where persistence changes.
8. Windows and Ubuntu CI pass.
9. Independent review and 10th-Man countercase are recorded.
10. No implementation path bypasses candidate quarantine, the ledger, or publication validation.
