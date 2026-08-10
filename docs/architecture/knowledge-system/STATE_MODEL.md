# Phase 3 Normative State Model

- **Version:** 1.0.0
- **Status:** Normative terminology for the deferred design
- **Purpose:** Prevent candidate disposition, reconciliation action, claim truth state, concept/synthesis lifecycle, open-question state, freshness, projection state, and snapshot state from being conflated

## 1. External Foundry document status

The bounded Foundry emits external OKF candidate documents with:

```yaml
status: draft
```

`draft` means only that the external candidate bundle is unverified and not canonical. It is not an internal Phase 3 concept, claim, synthesis, or truth state.

## 2. Candidate disposition

```text
quarantined
admissible
duplicate
insufficient_evidence
rejected
```

Candidate disposition determines whether incoming material can be reconciled. It does not describe truth or publication readiness.

## 3. Reconciliation action

```text
create
corroborate
amend
contradict
supersede
duplicate
reject
insufficient_evidence
```

A reconciliation action is an immutable decision about how one admissible candidate claim relates to governed existing knowledge. It is not a lifecycle state.

## 4. Claim epistemic state

The existing Erasmus epistemic ledger remains authoritative:

```text
speculative
analogy
leap
unresolved
plausible
supported
established
contradicted
falsified
```

No Phase 3 table, OKF field, vector score, graph edge, synthesis, or publication state may replace these truth states.

## 5. Concept and synthesis lifecycle

```text
provisional
reviewed
validated
contested
canonical
superseded
rejected
deprecated    # concepts only when historical compatibility is retained
```

`provisional` is the initial internal Phase 3 lifecycle state. It means the record has been assembled from governed inputs but has not passed independent review.

`canonical` means a validated revision is included in the current immutable published snapshot for an authorized scope. It does not imply that every constituent claim is `established`, current, or uncontested.

## 6. Open-question state

```text
open
investigating
partially_answered
answered
blocked
superseded
closed_invalid
```

A question becomes `answered` only when governed answer claims and declared closure criteria pass. Model prose alone cannot close a question.

## 7. Freshness state

```text
current
approaching_stale
stale
unknown
source_unavailable
```

Freshness is orthogonal to truth. `stale` does not mean `falsified`; it means current verification or recency requirements are not satisfied.

## 8. Snapshot state

```text
building
validated
approved
published
withdrawn
failed
```

A snapshot becomes current only after a successful deterministic publication receipt. Snapshot `validated` is not concept lifecycle `validated` and is not claim truth `established`.

## 9. Projection state

```text
queued
building
ready
failed
stale
retired
```

A projection can fail or become stale without changing its source snapshot or authoritative knowledge.

## 10. Policy-set state

```text
proposed
reviewed
approved
active
superseded
suspended
revoked
expired
```

Policy state controls whether one exact policy version may be evaluated. It never describes knowledge truth or concept lifecycle.

## 11. Semantic-registry state

```text
proposed
reviewed
approved
active
superseded
revoked
```

A registry snapshot defines semantics for exact records. Activating a later registry does not reinterpret older records automatically.

## 12. Publication-channel state

```text
proposed
active
suspended
retired
```

Each active channel owns its own current snapshot pointer and scope. Channel state is not snapshot state.

## 13. Knowledge-job state

```text
queued
running
paused
blocked
cancelling
cancelled
completed
failed
```

Job state is operational. `completed` requires the operation's terminal acceptance receipt and does not imply knowledge validation or publication.

## 14. Required API separation

No API or database column named only `status` may cross record families without its contract type. Interfaces shall use explicit names such as:

- `candidate_disposition`;
- `reconciliation_action`;
- `epistemic_status`;
- `concept_lifecycle`;
- `synthesis_lifecycle`;
- `question_state`;
- `freshness_state`;
- `snapshot_state`;
- `projection_state`;
- `policy_state`;
- `registry_state`;
- `channel_state`;
- `job_state`.

## 15. Forbidden implicit transitions

- Foundry `draft` does not imply Phase 3 `provisional` until governed import and admission complete.
- Candidate `admissible` does not imply a claim is `plausible` or `supported`.
- Reconciliation `corroborate` does not imply a ledger support transition unless existing ledger rules pass.
- Claim `established` does not automatically make its concept `canonical`.
- Concept `validated` does not automatically publish a snapshot.
- Snapshot `published` does not make a stale claim current.
- Projection `ready` does not establish truth or trust.
- Open question `answered` does not automatically canonicalize its answer synthesis.

## 16. Cross-reference

- [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md)
- [`OPEN_QUESTIONS_AND_SYNTHESIS.md`](OPEN_QUESTIONS_AND_SYNTHESIS.md)
- [`CONTRACT_CATALOGUE.md`](CONTRACT_CATALOGUE.md)
- [`STORAGE_PROJECTION_AND_RETRIEVAL.md`](STORAGE_PROJECTION_AND_RETRIEVAL.md)
- [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md)
- [`OPERATOR_API_AND_RUNBOOK.md`](OPERATOR_API_AND_RUNBOOK.md)
