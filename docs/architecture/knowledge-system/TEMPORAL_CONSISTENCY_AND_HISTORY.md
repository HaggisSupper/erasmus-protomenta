# Phase 3 Temporal, Consistency, and Historical Query Semantics

- **Version:** 1.0.0
- **Status:** Accepted target design; non-runtime
- **Purpose:** Define valid time, transaction time, source time, publication time, as-of queries, consistency modes, revision conflicts, historical reconstruction, and canonical/publication lag

## 1. Core distinction

The knowledge system must answer four different questions without conflating them:

1. **What does the evidence claim applies at time T?** — valid/effective time.
2. **What did Erasmus know or believe as of time K?** — transaction/recorded time.
3. **What was published to channel C in snapshot S?** — publication time and immutable snapshot identity.
4. **What unreviewed or operational state is visible to an authorized reviewer now?** — consistency and authority mode.

A single `timestamp` or `latest` flag is insufficient.

## 2. Time dimensions

### 2.1 Source time

Source records may include:

- `authored_at` — when the source was authored;
- `observed_at` — when an observation/test occurred;
- `source_modified_at` — publisher/filesystem declared modification time;
- `effective_from` and `effective_to` — interval the source says its content applies;
- `acquired_at` — when Erasmus acquired the exact bytes;
- `verified_at` — when the source identity/content was independently checked.

Declared source time is evidence and may be wrong. Acquisition and verification time are local receipts.

### 2.2 Claim valid time

A claim's qualifiers may include:

- `valid_from`;
- `valid_to`;
- exact version/revision interval;
- jurisdiction/environment/project applicability;
- event time or measurement time.

Intervals use half-open semantics by default:

```text
[valid_from, valid_to)
```

An omitted boundary is unbounded only when policy and the claim type permit it. Unknown time is represented as unknown, not unbounded.

### 2.3 Transaction time

Every authoritative append-only Phase 3 record has:

- a required positive `event_seq` foreign key to the single SQLite `knowledge_events(event_seq INTEGER PRIMARY KEY AUTOINCREMENT)` order;
- `recorded_at` in UTC;
- transaction/command/decision ID.

The event and domain record commit in the same SQLite transaction. Wall-clock timestamps aid interpretation but do not establish commit order. Global `event_seq` alone is authoritative for “as known by Erasmus”; publication `attempt_sequence`, immutable artifact `snapshot_sequence`, pointer `pointer_generation`, and registry sequence are separate domain counters only.

### 2.4 Publication time

Publication records distinguish:

- `attempt_sequence` for each channel-local intent/receipt attempt;
- immutable `snapshot_sequence` allocated only on artifact creation;
- `pointer_generation` allocated only on successful channel-pointer replacement;
- snapshot creation/validation/approval/materialization times;
- exact materialization/reselection receipt ID;
- pointer update time;
- withdrawal time where applicable.

Rollback can therefore select an older `snapshot_sequence` at a newer attempt and pointer generation. Publication time does not rewrite claim valid time or transaction history.

### 2.5 Projection time

Projection manifests record:

- source snapshot;
- builder start/completion times;
- active policy, registry, and directive-set identities;
- artifact digest;
- ready/stale/retired transitions.

Projection completion time is not knowledge time.

## 3. Temporal contract

### 3.1 `TemporalScope`

```json
{
  "valid_at": "2026-08-09T00:00:00Z",
  "valid_during": null,
  "as_known_at": "2026-08-10T00:00:00Z",
  "as_known_sequence": null,
  "published_snapshot_id": null,
  "channel_id": "urn:erasmus:publication-channel:private-default",
  "timezone": "UTC"
}
```

Rules:

- `valid_at` and `valid_during` are mutually exclusive.
- `as_known_at` and `as_known_sequence` are mutually exclusive; sequence is preferred for exact replay.
- A `published_snapshot_id` fixes the published view and cannot be combined with a contradictory current-channel selector.
- All persisted timestamps use RFC 3339/ISO-8601 UTC with `Z`.
- User-entered local time must include an explicit zone and is normalized to UTC while retaining the original representation in provenance.

## 4. Consistency modes

### 4.1 `published_current`

Default agent and operator read mode.

- Reads one channel's current receipted immutable snapshot.
- Applies active policy, scope, freshness, and serving directives.
- Uses only ready projections derived from that snapshot and compatible directive/policy/registry context.
- Never includes candidates or unvalidated operational revisions.

### 4.2 `published_snapshot`

Exact reproducible read.

- Caller supplies channel and snapshot ID.
- Snapshot bytes and manifest are immutable.
- Current serving directives still apply when the query is used operationally, unless an authorized forensic request explicitly asks for the historical unfiltered publication view.
- The response distinguishes `snapshot_content` from `currently_servable_content`.

### 4.3 `operational_review`

Authorized reviewer mode.

- Reads append-only operational claims, concept revisions, reviews, questions, syntheses, policies, directives, and pending publication state.
- Requires exact review authority and scope.
- Labels every non-published record and its lifecycle.
- Cannot be used as the default context source for mission execution.

### 4.4 `candidate_review`

Quarantine-only mode.

- Reads Foundry/imported candidates, candidate claims, model proposals, comparison targets, and rejected/deferred material.
- Requires candidate-review authority.
- Does not join candidate text into canonical evidence packets.

### 4.5 `historical_as_known`

Forensic reconstruction mode.

- Reconstructs operational current-state projections at a transaction sequence/time.
- Uses only records committed by that point.
- Does not apply later corrections as if they were known earlier.
- Can optionally compare with later-known corrections in a separately labeled section.

### 4.6 `historical_valid_at`

Temporal applicability mode.

- Selects claims whose declared valid intervals intersect the requested time.
- Uses the caller-selected `as_known` boundary to avoid hindsight leakage.
- Requires explicit handling of claims with unknown valid time.

## 5. Query examples

| User intent | Consistency/temporal interpretation |
|---|---|
| “What does Erasmus currently consider canonical?” | `published_current`, current channel |
| “What did we know on 2026-06-01?” | `historical_as_known` at transaction sequence/time |
| “What requirement applied to version 2.4 in March?” | `historical_valid_at` with version/time qualifiers and explicit as-known boundary |
| “Why did mission 123 make that decision?” | Exact `KnowledgeUseReceipt`, evidence packet, snapshot, directives, and operational records at decision time |
| “Show the unreviewed candidate comparison” | `candidate_review`, never canonical context |
| “Reproduce snapshot 41” | `published_snapshot` pinned to channel/snapshot and manifest digest |
| “Would we still serve the content from snapshot 41 today?” | Snapshot content plus current serving-directive evaluation |

## 6. Current-state projections

Tables or views named `current_*` are derived from append-only records using:

1. `WHERE event_seq <= :as_known_sequence ORDER BY event_seq`, selecting the latest committed event within each subject's state plane;
2. supersession/tombstone rules;
3. scope and policy selection;
4. no wall-clock last-write-wins;
5. no model-generated timestamp precedence.

A duplicate or missing `event_seq` is an integrity error. Timestamps are temporal facts, never ordering keys or tie-breakers. Records committed in one command transaction retain their allocated event order, while readers observe the transaction atomically.

## 7. Corrections and hindsight

- A later correction creates new evidence, transition, decision, revision, or directive.
- Historical queries do not rewrite the past record.
- The UI/API may show “known then” and “known now” side-by-side.
- A source publishing an earlier effective date does not imply Erasmus knew it earlier.
- Backdated source content is represented with earlier valid time and later transaction/acquisition time.
- Supersession may change current applicability while preserving the prior claim's historical interval.

## 8. Temporal contradiction semantics

Two claims are not contradictory when their valid intervals, versions, environments, or scopes do not materially overlap.

Comparison order:

1. normalize subject/entity identity as known at the comparison time;
2. compare scope and applicability;
3. compare valid intervals and version ranges;
4. compare units/coordinate frames;
5. evaluate logical incompatibility only over the overlap;
6. record unresolved temporal ambiguity when boundaries are unknown.

A later claim may supersede rather than contradict an earlier valid claim.

## 9. Publication lag and read-your-writes

Operational decisions may precede the next canonical snapshot. The system makes this lag explicit.

- A successful reconciliation/lifecycle decision returns the operational record IDs and states that publication is pending.
- It does not report the concept as current-channel canonical until the publication receipt and pointer update exist.
- An authorized reviewer may use `operational_review` to inspect the decision immediately.
- Normal agents continue using the current published snapshot plus active serving directives.
- A critical invalidation can block unsafe old content immediately without pretending a new snapshot exists.

## 10. Concurrency and revision semantics

Mutating commands include exact expected revision values for every affected current-state object. Publication specifically compares the generation-free `expected_prior_pointer_payload` plus the separate authoritative `expected_prior_pointer_generation`; it never embeds a second generation or substitutes attempt/snapshot counters.

- Stale expected revision fails before mutation.
- No automatic rebase or last-write-wins occurs for epistemic records.
- A caller re-reads current state and submits a new command.
- Idempotent replay with the same command digest returns the original result.
- Reuse of an idempotency key with changed content fails.
- Publication is serialized per channel, not globally.
- Identity and reconciliation decisions lock or compare exact affected entity/claim/concept sequences.

## 11. Retention and temporal availability

Policy defines how long source bytes, snapshots, operational records, use receipts, and projections remain locally available.

- Append-only audit metadata needed to interpret decisions is retained unless a protected deletion law/policy requires otherwise.
- Source removal produces a tombstone and may make historical text unavailable.
- Historical responses distinguish metadata-known from content-available.
- Disposable projections may be deleted at any time; exact snapshot and operational reconstruction remains possible where retained.
- A retention action cannot silently make `source_unavailable` appear `current`.

## 12. Clock and timezone safety

- Persist UTC only.
- Require explicit timezone for operator-entered local dates/times.
- Use database sequence/monotonic process timing for ordering and duration.
- Detect material system-clock regressions and emit a health/security finding.
- Do not use file modification time as immutable source identity.
- Preserve declared source time separately from verified acquisition time.
- Daylight-saving and locale formatting never change stored values.

## 13. Retrieval request additions

`RetrievalRequest` includes:

```json
{
  "consistency": "published_current",
  "temporal_scope": {
    "valid_at": null,
    "valid_during": null,
    "as_known_at": null,
    "as_known_sequence": null,
    "published_snapshot_id": null,
    "channel_id": "urn:erasmus:publication-channel:private-default",
    "timezone": "UTC"
  },
  "include_later_corrections": false
}
```

The evidence packet is an immutable authoritative retrieval receipt. It records its own global `event_seq`, the normalized temporal query's `as_known_event_seq` boundary, exact publication receipt, immutable snapshot counter, pointer generation, and directive-set digest. The as-known boundary is never later than the packet event.

## 14. Storage requirements

- Every authoritative append-only Phase 3 table has a required unique global `event_seq` reference in addition to timestamp; it is inserted with the event row in the same transaction.
- Relevant claims, entities, aliases, policies, relationships, sources, and directives store valid/effective intervals where applicable.
- Snapshot sequence is unique per publication channel and immutable per artifact; attempt sequence and pointer generation have their own channel-local uniqueness and never define historical order.
- Evidence packets persist an event reference and as-known boundary in the same transaction as their canonical packet bytes/digest.
- Use receipts record decision/action time and exact as-known snapshot/directive context.
- Historical views apply complete committed events in `event_seq` order up to the resolved boundary; no separate mutable historical truth table or timestamp tie-break is created.

## 15. Failure taxonomy additions

- `temporal_scope_invalid`
- `timezone_required`
- `valid_interval_invalid`
- `transaction_boundary_unavailable`
- `historical_content_unavailable`
- `hindsight_boundary_violation`
- `consistency_mode_unauthorized`
- `snapshot_channel_mismatch`
- `projection_temporal_mismatch`
- `clock_regression_detected`
- `publication_pending`

## 16. Acceptance tests

A promoted implementation must prove:

1. “Valid then” and “known then” return different correct fixtures where acquisition is delayed.
2. Later corrections do not appear in historical-as-known results unless explicitly requested and labeled.
3. Backdated sources retain later acquisition/transaction time.
4. Non-overlapping time/version intervals do not produce false contradiction.
5. Unknown intervals remain unknown and do not become unbounded silently.
6. Snapshot-pinned reads reproduce exact content and manifest.
7. Current serving directives can block content from an older snapshot without changing snapshot bytes.
8. Candidate/operational records never appear in `published_current`.
9. `operational_review` and `candidate_review` require exact authority and label non-published content.
10. Stale expected revisions fail before mutation; no last-write-wins occurs.
11. Snapshot sequences are independent per publication channel.
12. Retrieval packets record exact consistency, valid/as-known boundaries, snapshot, policy, registry, and directive-set IDs.
13. UTC normalization preserves original entered timezone in provenance.
14. Clock regression creates a finding but transaction sequence remains ordered.
15. Source removal yields content-unavailable historical responses rather than fabricated text.
16. Publication lag is reported as pending rather than canonical completion.
