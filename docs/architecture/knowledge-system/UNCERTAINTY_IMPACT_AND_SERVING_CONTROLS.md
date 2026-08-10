# Phase 3 Uncertainty, Impact, Invalidation, and Serving Controls

- **Version:** 1.0.0
- **Status:** Accepted target design; non-runtime
- **Purpose:** Define non-conflated uncertainty, materiality, knowledge-use receipts, authoritative dependency impact, invalidation propagation, and immediate serving controls between an operational finding and the next immutable publication snapshot

## 1. Problem statement

Immutable publication snapshots are required for reproducibility, but immutability creates a timing problem: a published claim or source can later become contradicted, falsified, stale, withdrawn, secret-bearing, policy-prohibited, or associated with a compromised tool/model. Building and approving a replacement snapshot may take time.

The system therefore needs an operational safety layer that can immediately qualify or block affected knowledge without rewriting the published snapshot or pretending that serving policy is truth state.

The design also needs to distinguish multiple kinds of uncertainty. A single confidence number cannot safely represent measurement error, source independence, semantic ambiguity, identity uncertainty, retrieval uncertainty, staleness, and evidence sufficiency.

## 2. Uncertainty planes

Uncertainty is represented by typed records, never one universal scalar.

| Kind | Meaning | Example representation |
|---|---|---|
| `measurement` | Error or variability in an observation/test | interval, standard uncertainty, distribution, tolerance |
| `aleatoric` | Irreducible variability in the phenomenon | distribution or frequency |
| `model` | Approximation uncertainty from a statistical/simulation model | calibrated interval, ensemble spread, validation error |
| `semantic` | Ambiguity in statement meaning or equivalence | categorical alternatives and unresolved distinctions |
| `identity` | Uncertainty whether identifiers/aliases refer to the same entity | candidate relations and conflicting identifiers |
| `scope` | Uncertainty about project/domain/audience applicability | compatible/incompatible/unknown dimensions |
| `temporal` | Uncertainty about effective interval or version | bounded/unknown dates or version range |
| `evidence_sufficiency` | Missing quantity, quality, independence, or test coverage | explicit missing requirements |
| `freshness` | Recency/source-availability uncertainty | current/stale/unknown/source-unavailable |
| `retrieval` | Uncertainty that the relevant governed evidence was found | recall budget, projection availability, omitted count |
| `synthesis` | Uncertainty introduced by selection or interpretation of claims | omitted material and interpretation markers |
| `operational` | Uncertainty caused by incomplete job/publication/projection state | checkpoint and ambiguous commit-point state |

## 3. `UncertaintyRecord`

```json
{
  "uncertainty_id": "urn:erasmus:uncertainty:<uuid>",
  "subject_id": "StableId",
  "kind": "measurement",
  "representation": {
    "type": "interval",
    "lower": 9.8,
    "upper": 10.2,
    "units": "mm",
    "coverage": 0.95
  },
  "method": {
    "id": "tool:uncertainty-propagator/1.0.0",
    "receipt_id": "..."
  },
  "source_span_ids": [],
  "evidence_ids": [],
  "scope": {},
  "applicability": {},
  "status": "current",
  "created_by": "Actor",
  "created_at": "ISO-8601",
  "supersedes_uncertainty_id": null
}
```

Allowed representation types include:

- `interval`
- `distribution`
- `standard_uncertainty`
- `tolerance`
- `categorical_alternatives`
- `missing_requirements`
- `unknown`

The registry defines the schema for each representation and its units/dimensional rules.

## 4. Confidence semantics

The existing ledger confidence history remains an explicitly recorded operational estimate. Phase 3 does not reinterpret it as probability, source credibility, or a substitute for epistemic state.

Rules:

- confidence cannot advance ledger state;
- confidence changes require evidence and rationale through the existing ledger;
- model self-confidence is stored only on a proposal/diagnostic record and cannot be copied into ledger confidence automatically;
- retrieval scores, source-count, reviewer-count, and agent agreement are not confidence;
- heterogeneous uncertainty values are not averaged without a registered deterministic method;
- a missing uncertainty assessment is `unknown`, not zero;
- consequential contexts include material uncertainty records or an explicit omission notice.

## 5. Materiality

Materiality is evaluated relative to a declared use, mission, decision, and risk class. It is not an intrinsic global label.

### 5.1 `MaterialityAssessment`

Required fields:

- assessment ID;
- subject IDs;
- intended use/mission/decision class;
- risk class;
- possible effect if wrong, stale, unavailable, or omitted;
- reversibility;
- detectability;
- affected channels/scopes;
- assessment: `immaterial`, `qualifying`, `material`, `critical`, `unknown`;
- evidence and policy evaluation;
- actor/reviewer/time.

### 5.2 Rules

- `unknown` fails closed for protected use.
- A claim can be immaterial for one use and critical for another.
- Publication summaries may omit immaterial detail but must retain material contradictions, exclusions, and uncertainty.
- Materiality does not change truth state; it selects review, serving, revalidation, withdrawal, and approval behavior.

## 6. Authoritative dependency records

Impact propagation cannot rely solely on a derived graph projection. Consequential dependencies are append-only authoritative records.

### 6.1 `KnowledgeDependency`

```json
{
  "dependency_id": "urn:erasmus:knowledge-dependency:<uuid>",
  "from_id": "dependent StableId",
  "type": "uses_claim",
  "to_id": "dependency StableId",
  "materiality": "material",
  "qualifiers": {},
  "decision_id": "...",
  "evidence_ids": [],
  "created_at": "ISO-8601",
  "supersedes_dependency_id": null
}
```

Initial dependency types:

- `derived_from_source`
- `uses_span`
- `binds_proposition`
- `uses_claim`
- `uses_concept_revision`
- `uses_relationship`
- `uses_synthesis`
- `answers_question`
- `renders_revision`
- `publishes_in_snapshot`
- `indexes_snapshot`
- `retrieved_in_packet`
- `used_by_mission`
- `used_by_decision`
- `validated_by_review`
- `evaluated_under_policy`
- `interpreted_under_registry`
- `served_by_channel`

Unknown dependencies remain descriptive until registered.

## 7. Knowledge-use receipts

A system cannot assess downstream impact unless it knows which governed knowledge was actually supplied to or materially used by a mission or decision.

### 7.1 `KnowledgeUseReceipt`

```json
{
  "use_receipt_id": "urn:erasmus:knowledge-use:<uuid>",
  "mission_id": 123,
  "decision_or_action_id": "...",
  "evidence_packet_id": "...",
  "channel_id": "...",
  "snapshot_id": "...",
  "claim_ids": [],
  "concept_revision_ids": [],
  "source_span_ids": [],
  "serving_directive_ids": [],
  "usage_class": "consulted",
  "materiality": "material",
  "actor": "Actor",
  "created_at": "ISO-8601"
}
```

Usage classes:

- `retrieved`
- `presented`
- `consulted`
- `cited`
- `material_to_decision`
- `rejected_by_decision`

Rules:

- Retrieval automatically records `retrieved` and `presented` where applicable.
- A mission/decision records `consulted`, `cited`, or `material_to_decision` explicitly; the model cannot infer material use after the fact without review.
- The receipt records exact snapshot and directives so later reconstruction is possible.
- Use receipts are append-only and do not create authority or truth.

## 8. Invalidation triggers

An `InvalidationEvent` may be created by:

- source digest mismatch, withdrawal, removal, or availability loss;
- claim contradiction, falsification, supersession, or reopen;
- identity merge/split/conflict;
- material uncertainty increase;
- failed or expired verification;
- stale/source-unavailable freshness assessment;
- policy revocation or stricter replacement;
- semantic registry revocation or corrected definition;
- compromised parser, tool, model, renderer, validator, or projection builder;
- secret/privacy/license discovery;
- snapshot or projection integrity failure;
- human/governor protected stop;
- 10th-Man finding accepted as a material blocker.

### 8.1 `InvalidationEvent`

Required fields:

- event ID;
- trigger kind;
- directly affected IDs;
- evidence and review IDs;
- scope/channel applicability;
- severity;
- policy evaluation;
- actor/authority/mission;
- timestamp;
- immediate serving requirement;
- recovery/revalidation requirement.

An invalidation event does not delete or rewrite the affected records.

## 9. Impact analysis

### 9.1 `ImpactAnalysis`

```json
{
  "impact_id": "urn:erasmus:knowledge-impact:<uuid>",
  "invalidation_event_id": "...",
  "root_subject_ids": [],
  "dependency_snapshot": {},
  "affected": {
    "claims": [],
    "concept_revisions": [],
    "syntheses": [],
    "open_questions": [],
    "relationships": [],
    "snapshots": [],
    "projections": [],
    "channels": [],
    "evidence_packets": [],
    "missions": [],
    "decisions": []
  },
  "materiality_by_subject": {},
  "unresolved_dependencies": [],
  "recommended_directives": [],
  "required_missions": [],
  "created_by": "process:erasmus-impact-analyzer/1.0.0",
  "created_at": "ISO-8601"
}
```

### 9.2 Propagation algorithm

1. Verify the invalidation event and its authority/evidence.
2. Resolve directly affected authoritative IDs.
3. Traverse registered authoritative dependency types under bounded fan-out/depth.
4. Include current concept revisions, syntheses, questions, snapshots, channels, projections, use receipts, and consequential missions/decisions.
5. Evaluate materiality per use/channel, not globally.
6. Record unresolved or missing dependency evidence.
7. Propose immediate serving directives.
8. Mark affected projections stale or blocked through operational transitions.
9. Create bounded revalidation, republish, rollback, incident, or human-notification mission candidates.
10. Require independent review for consequential/critical impact.

A derived graph may accelerate traversal, but the final analysis reconciles against authoritative dependency records.

## 10. Serving directives

A serving directive is an immediate operational control applied after authorization and before any projection content is returned. It bridges the period before a corrected immutable snapshot is published.

### 10.1 `ServingDirective`

```json
{
  "directive_id": "urn:erasmus:serving-directive:<uuid>",
  "subject_ids": [],
  "channel_ids": [],
  "scope_selector": {},
  "effect": "exclude",
  "qualification": null,
  "reason_code": "source_withdrawn",
  "invalidation_event_id": "...",
  "impact_id": "...",
  "evidence_ids": [],
  "policy_evaluation_id": "...",
  "actor": "Actor",
  "authority": "knowledge:withdraw",
  "mission_id": 123,
  "effective_at": "ISO-8601",
  "expires_at": null,
  "replacement_snapshot_id": null,
  "created_at": "ISO-8601"
}
```

Effects:

- `allow` — no additional restriction;
- `qualify` — result may be served only with exact warning/limitations;
- `exclude` — affected subject is removed from ordinary results;
- `block` — request fails closed when the subject is material to the query/use;
- `channel_suspend` — no results may be served from the affected channel.

Restrictiveness order:

```text
allow < qualify < exclude < block < channel_suspend
```

The most restrictive applicable active directive wins.

### 10.2 Directive invariants

- Directives do not alter ledger truth state, concept lifecycle, or historical snapshots.
- A directive requires exact scope/channel and policy evaluation.
- A source, candidate, model, or retrieved document cannot create a directive.
- Protected emergency directives require an authorized governor/security capability; they may precede full impact analysis but must reference a bounded incident and expiry/review condition.
- A directive is removed only through expiration or a superseding directive with evidence.
- Context packets include active qualification directive IDs and warnings.
- Excluded/blocked records must not enter model context or caches.
- Cache keys include the active directive-set digest.

## 11. Retrieval order with serving controls

```text
request authorization and channel selection
  -> active policy and registry resolution
  -> active serving-directive snapshot/digest
  -> projection candidate generation using allowed partitions
  -> pre-materialization exclusion/block filter
  -> lifecycle/freshness/contradiction filtering
  -> reranking
  -> qualification injection
  -> evidence-packet creation
  -> knowledge-use receipt
```

For protected content, directives and scope filters must be applied before text is loaded into process memory where the projection technology supports pre-filtering. A technology that cannot provide this isolation is not acceptable for protected scopes.

## 12. Projection invalidation

A projection moves to `stale` or `failed` when:

- its source snapshot is withdrawn or tampered;
- its policy, registry, rendering, embedding, graph-definition, or directive assumptions no longer match;
- its builder is revoked;
- protected removal is incomplete;
- integrity or fixture checks fail.

A stale projection is excluded from normal retrieval unless a declared degraded read policy permits a safe exact/lexical fallback. A serving directive can block stale projection use immediately.

## 13. Downstream mission and decision notification

When a material or critical invalidation affects prior `KnowledgeUseReceipt` records:

- create a structured impact notification;
- identify mission/decision owner, use receipt, affected claim, new state, and recommended action;
- do not automatically reverse an external decision unless a separately authorized capability exists;
- create a bounded review/revalidation/rollback mission candidate where policy requires;
- record acknowledgement and disposition;
- preserve cases where knowledge was retrieved but explicitly rejected by the decision.

## 14. Uncertainty-aware synthesis and publication

A concept or synthesis renderer must include material uncertainty in a deterministic form:

- measurement units and intervals;
- model validity envelope;
- unresolved identity/scope alternatives;
- missing evidence requirements;
- freshness/source availability;
- contested claims;
- omitted uncertainty due to publication scope.

A synthesis cannot convert an interval into a point estimate, categorical ambiguity into certainty, or missing evidence into a confidence score without a registered deterministic method and a new claim.

## 15. Storage targets

```sql
CREATE TABLE knowledge_uncertainties (
    uncertainty_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    uncertainty_kind TEXT NOT NULL,
    representation_json TEXT NOT NULL,
    method_json TEXT NOT NULL,
    source_span_ids_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    applicability_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    supersedes_uncertainty_id TEXT
);

CREATE TABLE knowledge_dependencies (
    dependency_id TEXT PRIMARY KEY,
    from_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    materiality TEXT NOT NULL,
    qualifiers_json TEXT NOT NULL,
    decision_id TEXT,
    evidence_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    supersedes_dependency_id TEXT
);

CREATE TABLE knowledge_use_receipts (
    use_receipt_id TEXT PRIMARY KEY,
    mission_id INTEGER,
    decision_or_action_id TEXT,
    evidence_packet_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    claim_ids_json TEXT NOT NULL,
    concept_revision_ids_json TEXT NOT NULL,
    source_span_ids_json TEXT NOT NULL,
    serving_directive_ids_json TEXT NOT NULL,
    usage_class TEXT NOT NULL,
    materiality TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_invalidation_events (
    invalidation_event_id TEXT PRIMARY KEY,
    trigger_kind TEXT NOT NULL,
    affected_ids_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    review_ids_json TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    severity TEXT NOT NULL,
    policy_evaluation_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    mission_id INTEGER,
    immediate_serving_requirement TEXT NOT NULL,
    recovery_requirement_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_impact_analyses (
    impact_id TEXT PRIMARY KEY,
    invalidation_event_id TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_serving_directives (
    directive_id TEXT PRIMARY KEY,
    subject_ids_json TEXT NOT NULL,
    channel_ids_json TEXT NOT NULL,
    scope_selector_json TEXT NOT NULL,
    effect TEXT NOT NULL,
    qualification_json TEXT,
    reason_code TEXT NOT NULL,
    invalidation_event_id TEXT NOT NULL,
    impact_id TEXT,
    evidence_ids_json TEXT NOT NULL,
    policy_evaluation_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    mission_id INTEGER,
    effective_at TEXT NOT NULL,
    expires_at TEXT,
    replacement_snapshot_id TEXT,
    created_at TEXT NOT NULL
);
```

Base records are append-only. Active/current directives and dependencies are projections over supersession and time.

## 16. Roadmap placement

- Typed uncertainty and authoritative dependencies begin with P3.3/P3.7 as relevant records are introduced.
- Knowledge-use receipts and serving-directive enforcement are mandatory before P3.10 serves canonical evidence to agents.
- Freshness, invalidation, impact propagation, and downstream notification are completed in P3.12.
- Continuous maintenance in P3.13 consumes invalidation and impact queues.
- Routing integration in P3.14 records knowledge-use receipts for material route decisions.

## 17. Failure taxonomy additions

- `uncertainty_representation_invalid`
- `uncertainty_method_unregistered`
- `materiality_unknown`
- `dependency_type_unregistered`
- `dependency_traversal_budget_exceeded`
- `impact_incomplete`
- `use_receipt_missing`
- `invalidation_not_authorized`
- `serving_directive_conflict`
- `serving_blocked`
- `channel_suspended`
- `directive_set_mismatch`
- `downstream_notification_required`

## 18. Acceptance tests

A promoted implementation must prove:

1. Measurement, model, semantic, identity, scope, freshness, and retrieval uncertainty are not collapsed into one scalar.
2. Ledger confidence cannot be changed from model self-confidence or retrieval score.
3. Unit/dimensional incompatibility blocks uncertainty aggregation.
4. Unknown uncertainty remains unknown and fails closed for protected use.
5. Authoritative dependency edges reconstruct impact without relying on a vector/graph projection.
6. Knowledge-use receipts identify exact channel, snapshot, packet, claims, and directives.
7. Source withdrawal immediately excludes or blocks affected protected results before republishing.
8. Active directives apply before content reaches model context or cache.
9. The most restrictive applicable directive wins deterministically.
10. Directives cannot change claim truth state or historical snapshots.
11. Directive expiration/supersession is append-only and auditable.
12. Projection invalidation prevents mismatched/stale artifacts from serving.
13. Impact analysis reaches affected syntheses, questions, snapshots, projections, missions, and decisions within bounded traversal.
14. Traversal-budget exhaustion produces incomplete/blocked impact, not false completeness.
15. Downstream notifications distinguish knowledge that was material, merely presented, or explicitly rejected.
16. Corrected publication and revalidation retire emergency directives without deleting the incident history.
17. Consequential synthesis and retrieval preserve material uncertainty and omitted-material notices.
