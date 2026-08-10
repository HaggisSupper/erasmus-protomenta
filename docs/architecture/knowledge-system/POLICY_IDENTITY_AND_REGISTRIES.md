# Phase 3 Knowledge Policy, Identity, and Registry Model

- **Version:** 1.0.0
- **Status:** Accepted target design; non-runtime
- **Purpose:** Define the policy authority, entity identity model, semantic registries, publication channels, compatibility rules, and governance receipts required by the Phase 3 knowledge system

## 1. Why this layer is required

The Phase 3 architecture refers to policy versions, stable subjects, relationship types, concept types, predicates, rendering profiles, source kinds, and publication scope. Those references cannot remain informal strings without creating hidden authority and inconsistent semantics.

This layer provides four governed services:

1. **Knowledge policy** — selects required evidence, reviews, authorities, automation limits, retention, freshness, and publication behavior.
2. **Identity resolution** — distinguishes stable real-world or system entities from titles, aliases, paths, and model guesses.
3. **Semantic registries** — define which concept types, predicates, relationship types, source kinds, and rendering profiles have recognized semantics.
4. **Publication channels** — define independent current snapshots for private, project, shared, or public audiences.

None of these services may be controlled by ordinary knowledge content. Policies and registries constrain knowledge; knowledge does not silently rewrite them.

## 2. Authority precedence

The effective decision context is evaluated in this order:

```text
immutable constitution
    ↓
explicit human/governor prohibition or protected approval requirement
    ↓
governing mission contract
    ↓
capability and exact implementation contract
    ↓
active knowledge-policy snapshot
    ↓
registered semantic/profile definitions
    ↓
request parameters
```

Rules:

- A lower layer may narrow authority but cannot broaden a higher layer.
- Explicit deny wins over permit.
- Missing policy is deny-by-default for mutation and publication.
- A mission may narrow scope, budget, or allowed actions but cannot waive constitution, capability, evidence, review, or protected approval requirements.
- A knowledge document, candidate, claim, synthesis, source, model, or retrieval result is never part of authority precedence.
- Policy evaluation determines whether a declared capability may proceed; it does not replace capability validation or tool identity verification.

## 3. Knowledge policy contracts

### 3.1 `KnowledgePolicySet`

An immutable versioned collection of rules activated for an exact deployment and scope.

```json
{
  "policy_id": "urn:erasmus:knowledge-policy:default",
  "version": "1.0.0",
  "policy_digest": {
    "algorithm": "sha256",
    "value": "...",
    "canonicalization": "canonical-json/v1"
  },
  "scope": {
    "visibility": "private",
    "tenant": "local-deployment",
    "project": null,
    "domain": null,
    "labels": []
  },
  "status": "active",
  "effective_at": "2026-08-09T00:00:00Z",
  "expires_at": null,
  "parent_policy_id": null,
  "parent_policy_version": null,
  "rules": [],
  "created_by": "human:governor",
  "created_at": "2026-08-09T00:00:00Z",
  "review_ids": [],
  "approval_id": "..."
}
```

Policy states:

- `proposed`
- `reviewed`
- `approved`
- `active`
- `superseded`
- `suspended`
- `revoked`
- `expired`

Only one policy set may be active for the same policy ID, version domain, and scope selector. More specific active policies may narrow a parent policy; they cannot broaden it.

### 3.2 `KnowledgePolicyRule`

Each rule is declarative and independently identified.

Required fields:

| Field | Meaning |
|---|---|
| `rule_id` | Stable rule identity |
| `operations` | Exact governed operations such as `knowledge:reconcile` or `snapshot:publish` |
| `subject_kinds` | Candidate, claim, concept, synthesis, question, snapshot, projection, source |
| `risk_classes` | Routine, consequential, protected |
| `scope_selector` | Deterministic scope predicate |
| `source_requirements` | Required/forbidden source kinds, count, independence, availability |
| `epistemic_requirements` | Minimum allowed ledger states and contradiction behavior |
| `lifecycle_requirements` | Allowed prior and target states |
| `freshness_requirements` | Current/stale/unknown behavior |
| `required_authorities` | Exact authorities |
| `required_reviews` | Review types and independence constraints |
| `human_approval` | `never`, `conditional`, or `required` |
| `tenth_man` | Trigger or mandatory condition |
| `automation` | `deny`, `observation_only`, `propose_only`, or `permit` |
| `budgets` | Time, retries, source count, model calls, tokens, storage, fan-out |
| `retention` | Source/evidence/audit/snapshot retention behavior |
| `publication` | Allowed channels, attribution, licensing, redaction, withdrawal |
| `fallback` | Deny, degrade, qualify, request approval, or create mission candidate |
| `priority` | Deterministic ordering only within the same specificity class |

Rules are data interpreted by a deterministic policy engine. Arbitrary executable expressions are prohibited in the first implementation.

### 3.3 Policy selectors

The first implementation shall support a deliberately small selector language:

- exact operation;
- exact/registered subject kind;
- exact risk class;
- visibility/project/domain labels;
- lifecycle state;
- epistemic state;
- freshness state;
- contradiction present/absent;
- source kind and availability;
- publication channel;
- actor role;
- mission ID or mission class when explicitly declared.

Selectors are conjunctive within one rule. Complex disjunction is represented by multiple rules. No user-supplied regular expressions or code execution are required initially.

### 3.4 `PolicyEvaluationReceipt`

Every consequential evaluation produces an immutable receipt:

```json
{
  "evaluation_id": "urn:erasmus:policy-evaluation:<uuid>",
  "policy_id": "urn:erasmus:knowledge-policy:default",
  "policy_version": "1.0.0",
  "policy_digest": {},
  "operation": "snapshot:publish",
  "subject_ids": [],
  "request_digest": {},
  "matched_rule_ids": [],
  "decision": "permit",
  "required_authorities": [],
  "required_reviews": [],
  "required_approvals": [],
  "remaining_conditions": [],
  "budgets": {},
  "reason_codes": [],
  "evaluated_by": "process:erasmus-knowledge-policy/1.0.0",
  "evaluated_at": "ISO-8601"
}
```

Decision values:

- `permit`
- `deny`
- `observation_only`
- `requires_review`
- `requires_human_approval`
- `requires_tenth_man`
- `insufficient_policy`

A permit receipt is necessary but not sufficient: all capability, contract, evidence, and state-transition checks still apply.

## 4. Policy lifecycle and change control

A policy cannot be generated, activated, or superseded by the ordinary knowledge pipeline.

Activation requires:

1. exact canonical policy bytes and digest;
2. schema validation;
3. static conflict and shadowing analysis;
4. test fixtures demonstrating intended permit and deny cases;
5. independent governance review;
6. human approval;
7. rollback to a prior active policy;
8. activation receipt;
9. no unresolved rule ambiguity.

A model may draft a policy candidate, but it remains an external document until explicitly admitted through governance outside Phase 3 knowledge promotion.

Policy changes do not retroactively rewrite prior decisions. Every decision retains the exact policy version and digest used.

## 5. Policy conflict resolution

Rules are resolved deterministically:

1. Constitution and protected human requirements are evaluated first.
2. Scope-incompatible policies are excluded.
3. Most specific selector wins only when it is equally or more restrictive.
4. Any applicable deny overrides permit.
5. Required reviews/approvals are unioned, not overwritten.
6. Budgets take the most restrictive applicable limit.
7. Retention takes the stricter legal/privacy requirement.
8. Publication takes the narrowest allowed audience.
9. Ambiguity or incomparable rules produce `insufficient_policy` and fail closed.

The policy validator rejects cycles in parent-policy references and conflicting rules that cannot be resolved by these rules.

## 6. Stable entity identity

### 6.1 Entity versus concept

- An **entity** is a stable referent: a person, organization, project, repository, file, model, runtime, tool, device, asset, standard, process, location, or other identifiable object.
- A **concept** is a publication and reasoning subject that organizes claims. It may describe one entity, a class of entities, a method, a relationship, or an abstract principle.
- A **claim** references entities, concepts, registered predicates, or typed literals.

Entity identity is not inferred from title similarity alone.

### 6.2 `EntityRecord`

```json
{
  "entity_id": "urn:erasmus:entity:<uuid>",
  "entity_type": "erasmus.entity/project/v1",
  "canonical_label": "Erasmus",
  "scope": {},
  "identifiers": [
    {
      "namespace": "github-repository",
      "value": "HaggisSupper/erasmus-protomenta",
      "valid_from": null,
      "valid_to": null,
      "source_span_ids": []
    }
  ],
  "created_by": "Actor",
  "created_at": "ISO-8601"
}
```

The base entity record is immutable. Label, identifier, alias, equivalence, split, and retirement changes are append-only events.

### 6.3 `EntityAlias`

Fields:

- alias ID;
- entity ID;
- alias string;
- normalized alias;
- language/locale;
- alias kind: `name`, `acronym`, `prior_name`, `path`, `identifier`, `misspelling`, `display_label`;
- validity interval;
- scope;
- evidence/source spans;
- created actor/time;
- supersession reference.

An alias improves lookup but does not prove identity by itself.

### 6.4 `IdentityResolutionProposal`

Possible relations:

- `same_entity`
- `distinct_entity`
- `alias_of`
- `successor_of`
- `version_of`
- `part_of`
- `unresolved`

The proposal records exact identifiers, aliases, temporal overlap, source evidence, deterministic matches, conflicting signals, and optional semantic analysis.

### 6.5 `IdentityResolutionDecision`

A governed immutable decision containing:

- proposal ID;
- relation;
- source and target entity IDs;
- evidence and review IDs;
- scope and temporal qualifiers;
- actor, authority, mission, policy evaluation;
- reason codes;
- idempotency key;
- timestamp.

Rules:

- `same_entity` requires compatible entity types and non-conflicting authoritative identifiers.
- Identity merge is represented as an equivalence decision plus canonical-representative projection; original IDs remain valid historical IDs.
- A split creates new entity IDs and a split decision; prior claims are not silently reassigned.
- `distinct_entity` prevents future automatic merge within the declared scope unless new evidence triggers a superseding decision.
- A model cannot make a final identity decision.
- Entity equivalence does not merge concept identity automatically.

### 6.6 Identity projection

The current canonical representative is a projection over append-only identity decisions. Claims continue to retain the exact entity ID used when created. Retrieval may expand equivalent IDs while preserving original provenance.

## 7. Semantic registry snapshot

A `SemanticRegistrySnapshot` is an immutable collection of recognized semantic definitions used by one decision, revision, publication, or projection.

```json
{
  "registry_snapshot_id": "urn:erasmus:semantic-registry-snapshot:<uuid>",
  "sequence": 4,
  "parent_snapshot_id": "...",
  "definitions": [],
  "manifest_digest": {},
  "status": "active",
  "created_at": "ISO-8601",
  "approval_id": "..."
}
```

Registry states:

- `proposed`
- `reviewed`
- `approved`
- `active`
- `superseded`
- `revoked`

Every consequential record references the registry snapshot that defined its semantic types.

## 8. Definition types

### 8.1 `EntityTypeDefinition`

Defines:

- stable type ID and version;
- name and description;
- allowed identifier namespaces;
- required qualifiers;
- parent type where applicable;
- scope behavior;
- examples and negative examples;
- validation profile.

### 8.2 `ConceptTypeDefinition`

Defines:

- concept type ID/version;
- intended purpose;
- allowed/required sections;
- allowed claim and relationship classes;
- default risk and freshness policy hints;
- renderer profile;
- prohibited authority semantics.

### 8.3 `PredicateDefinition`

Defines structured claim predicates:

- predicate ID/version;
- allowed subject types;
- allowed object type or literal schema;
- required qualifiers and units;
- inverse predicate where applicable;
- temporal semantics;
- whether contradiction comparison is defined;
- deterministic normalization/validation profile.

Unregistered predicates may be stored as descriptive strings in provisional claims but cannot drive automated reconciliation or policy.

### 8.4 `RelationshipTypeDefinition`

```json
{
  "relationship_type_id": "erasmus.relationship/depends_on/v1",
  "label": "depends on",
  "source_types": [],
  "target_types": [],
  "inverse_type": null,
  "symmetric": false,
  "transitive": false,
  "cardinality": {},
  "cycle_policy": "forbid | permit | bounded",
  "qualifier_schema": {},
  "evidence_required": true,
  "policy_effective": false,
  "renderer": {},
  "status": "active"
}
```

Rules:

- Descriptive relationship types do not grant authority.
- `policy_effective: true` is prohibited in the initial Phase 3 implementation unless the relationship is backed by a separate immutable capability/policy contract.
- Transitivity is never inferred unless registered and validated for the exact type.
- Inverse and symmetric edges may be materialized as derived projection edges, clearly labeled.
- Cycle and cardinality checks are deterministic.

### 8.5 `SourceKindDefinition`

Defines source metadata, acquisition rules, coordinate types, extraction profiles, privacy defaults, and publication/redistribution behavior.

### 8.6 `RenderingProfile`

Defines deterministic concept/question/synthesis rendering, key and section order, path rules, Markdown escaping, source-footnote behavior, aliases, and canonicalization version.

### 8.7 `ProjectionProfile`

Defines FTS/vector/graph input rendering, builder identity requirements, configuration schema, evaluation fixtures, and compatibility rules.

## 9. Unknown and extension semantics

- Unknown OKF frontmatter fields are preserved on import.
- Unknown entity, concept, predicate, or relationship types can be stored in quarantine/provisional records when policy permits.
- Unknown types are descriptive only and cannot drive automated policy, reconciliation, contradiction, transitivity, or publication paths.
- Promotion requiring unknown semantics fails with `unregistered_semantic_type`.
- Registration never retroactively changes the meaning of prior records; a new semantic registry snapshot and explicit revalidation are required.

## 10. Publication channels

A single global `current` pointer is insufficient when private, project, shared, and public corpora have different scope and redaction requirements.

### 10.1 `PublicationChannel`

```json
{
  "channel_id": "urn:erasmus:publication-channel:private-default",
  "name": "Private canonical knowledge",
  "audience": "private",
  "scope_selector": {},
  "root_path": "state/knowledge/channels/private-default",
  "policy_id": "urn:erasmus:knowledge-policy:default",
  "policy_version": "1.0.0",
  "rendering_profile": "erasmus.okf-renderer/v1",
  "retention": {},
  "redaction_profile": null,
  "current_snapshot_id": null,
  "status": "active"
}
```

Channel states:

- `proposed`
- `active`
- `suspended`
- `retired`

Channel activation requires policy, scope, root confinement, backup, publication, and rollback tests.

### 10.2 Current-pointer semantics

- There is one current pointer per channel, not one global current pointer.
- A snapshot belongs to exactly one channel and scope.
- The same concept revision may appear in multiple channels only through separate publication plans and receipts.
- Public/shared channels use redacted or declassified source references where required.
- Updating one channel never changes another channel's pointer.
- Retrieval requests select a channel explicitly or through deterministic policy.

Recommended layout:

```text
state/knowledge/channels/
├── private-default/
│   ├── current.json
│   └── snapshots/
├── project-<id>/
│   ├── current.json
│   └── snapshots/
└── public/
    ├── current.json
    └── snapshots/
```

## 11. Registry and policy persistence

Target append-only records:

```sql
CREATE TABLE knowledge_policy_sets (
    policy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    policy_digest_json TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    parent_policy_id TEXT,
    parent_policy_version TEXT,
    rules_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(policy_id, version)
);

CREATE TABLE knowledge_policy_transitions (
    transition_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    prior_state TEXT,
    new_state TEXT NOT NULL,
    review_ids_json TEXT NOT NULL,
    approval_id TEXT,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_policy_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    policy_digest_json TEXT NOT NULL,
    request_digest_json TEXT NOT NULL,
    matched_rule_ids_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    result_json TEXT NOT NULL,
    evaluated_by TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE knowledge_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_label TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_kind TEXT NOT NULL,
    language TEXT,
    valid_from TEXT,
    valid_to TEXT,
    scope_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    source_span_ids_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    supersedes_alias_id TEXT,
    FOREIGN KEY(entity_id) REFERENCES knowledge_entities(entity_id)
);

CREATE TABLE knowledge_identity_decisions (
    decision_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    source_entity_ids_json TEXT NOT NULL,
    target_entity_ids_json TEXT NOT NULL,
    qualifiers_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    review_ids_json TEXT NOT NULL,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    mission_id INTEGER NOT NULL,
    policy_evaluation_id TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_semantic_registry_snapshots (
    registry_snapshot_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL UNIQUE,
    parent_snapshot_id TEXT,
    manifest_digest_json TEXT NOT NULL,
    definitions_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_registry_transitions (
    transition_id TEXT PRIMARY KEY,
    registry_snapshot_id TEXT NOT NULL,
    prior_state TEXT,
    new_state TEXT NOT NULL,
    review_ids_json TEXT NOT NULL,
    approval_id TEXT,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_publication_channels (
    channel_id TEXT PRIMARY KEY,
    configuration_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE knowledge_channel_transitions (
    transition_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    prior_state TEXT,
    new_state TEXT NOT NULL,
    current_snapshot_id TEXT,
    policy_evaluation_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    authority TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

Mutable current views are derived from transitions. Base records and transitions are append-only.

## 12. Compatibility and migration

### 12.1 Contract compatibility

- Contract IDs include major version.
- Additive optional fields may remain within one major version only when default behavior is unambiguous and fail-closed.
- Changed required semantics require a new major version.
- Consumers declare supported contract/profile versions.
- Unknown major versions fail closed for mutation and may be preserved as opaque data for export.

### 12.2 Semantic compatibility

A new semantic definition version does not silently reinterpret existing claims or relationships. Revalidation or explicit migration creates new revisions/decisions.

### 12.3 Policy compatibility

A new policy version applies only from activation time unless a separately authorized audit mission evaluates prior records. Prior receipts remain valid evidence of what policy was used at the time, even if that policy is later revoked.

### 12.4 Publication compatibility

Each snapshot records policy, semantic-registry, rendering-profile, validator, and publisher versions. A consumer can reject unsupported profiles without corrupting the snapshot.

## 13. Operator and API integration

Every mutating knowledge command includes:

- exact policy ID/version or deterministic active-policy resolution;
- exact semantic registry snapshot;
- publication channel where applicable;
- mission, actor, authority, idempotency key, expected revision, evidence, and reviews.

Read commands return the policy/registry/channel context used to interpret the result.

The complete target command and service surface is defined in [`OPERATOR_API_AND_RUNBOOK.md`](OPERATOR_API_AND_RUNBOOK.md).

## 14. Failure taxonomy additions

- `policy_not_found`
- `policy_not_active`
- `policy_digest_mismatch`
- `policy_conflict`
- `insufficient_policy`
- `policy_denied`
- `registry_not_found`
- `registry_not_active`
- `registry_digest_mismatch`
- `unregistered_semantic_type`
- `invalid_relationship_semantics`
- `identity_ambiguous`
- `identity_conflict`
- `identity_revision_conflict`
- `identifier_namespace_unregistered`
- `publication_channel_not_found`
- `publication_channel_suspended`
- `publication_scope_mismatch`
- `channel_snapshot_conflict`

## 15. Security properties

- Policy and registry files are not loaded from untrusted source folders.
- Policy/registry activation uses exact digests and approved roots.
- No LLM evaluates final policy decisions.
- Identity resolution proposals from models remain proposals.
- Aliases and similarity cannot grant identity or authority.
- Relationship semantics cannot be defined by ordinary concept text.
- Public channels cannot reference private source paths or bytes.
- A compromised channel pointer cannot make an unreceipted snapshot valid.

## 16. Acceptance tests

A promoted implementation must prove:

1. Deny overrides permit and missing policy fails closed.
2. More specific policy cannot broaden a parent policy.
3. Required review/approval sets are unioned.
4. Identical policy input produces identical evaluation receipt.
5. Policy changes do not alter historical decision receipts.
6. Candidate/model content cannot activate policy or registry changes.
7. Entity aliases do not merge entities without a decision.
8. Conflicting identifiers produce `identity_conflict` or `identity_ambiguous`.
9. Entity merge/split preserves original IDs and claim provenance.
10. Unknown relationship and predicate types remain descriptive and cannot drive policy.
11. Transitivity, inverse, cardinality, and cycle rules follow the exact registry snapshot.
12. Each publication channel has an independent current pointer and rollback path.
13. Public/shared channels reject private source paths and scope violations.
14. Snapshot receipts identify policy, registry, renderer, validator, and channel.
15. Unsupported contract/profile major versions fail closed without data loss.
16. Policy/registry/channel backup and restore reproduce active views and evaluation fixtures.
