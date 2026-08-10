# Phase 3 Operator, API, and Runbook Contract

- **Version:** 1.0.0
- **Status:** Accepted target design; non-runtime
- **Purpose:** Define the headless command surface, request/response envelope, long-running job control, operator workflow, diagnostics, backup/recovery, Tauri boundary, and automation behavior for the governed knowledge system

## 1. Operating principle

Phase 3 must remain fully operable without a desktop UI. The authoritative implementation surface is a local headless command/service contract. Tauri, OpenCode commands, MCP adapters, and future automation are clients of that contract and never access the database or snapshot filesystem directly.

The target operator experience is subordinate to the future single-command Erasmus appliance:

```powershell
opencode-erasmus
```

The appliance starts and validates required local services. Knowledge operations remain explicit bounded commands and do not run merely because the appliance starts.

## 2. Transport-neutral service boundary

Every operation uses a versioned request and response envelope, regardless of whether invoked:

- in-process from the Python kernel;
- through a future Rust crate boundary;
- by CLI;
- through a local named pipe or loopback service;
- from Tauri IPC;
- through a read-only MCP adapter;
- by a mission worker.

### 2.1 Request envelope

```json
{
  "contract": "erasmus.knowledge-request/v1",
  "request_id": "urn:erasmus:knowledge-request:<uuid>",
  "operation": "candidate:import",
  "mission_id": 123,
  "actor": "human:governor",
  "authority": ["knowledge:ingest"],
  "idempotency_key": "stable-caller-key",
  "expected_revisions": {},
  "policy": {
    "policy_id": "urn:erasmus:knowledge-policy:default",
    "version": "1.0.0"
  },
  "registry_snapshot_id": "urn:erasmus:semantic-registry-snapshot:...",
  "channel_id": null,
  "scope": {},
  "input": {},
  "evidence_ids": [],
  "review_ids": [],
  "budgets": {
    "timeout_seconds": 300,
    "retry_limit": 0,
    "max_model_calls": 0,
    "max_output_bytes": 1048576
  },
  "dry_run": false,
  "requested_at": "ISO-8601"
}
```

Read-only operations may omit mission and authority only when policy explicitly permits anonymous local inspection. Consequential mutation always requires them.

### 2.2 Response envelope

```json
{
  "contract": "erasmus.knowledge-response/v1",
  "request_id": "urn:erasmus:knowledge-request:...",
  "operation": "candidate:import",
  "ok": true,
  "result": {},
  "job_id": null,
  "receipts": [],
  "evidence_refs": [],
  "warnings": [],
  "next_actions": [],
  "failure": null,
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "duration_ms": 42
}
```

Failure envelope:

```json
{
  "code": "authority_denied",
  "message": "knowledge:publish authority is required",
  "details": {},
  "retryable": false,
  "action": "obtain the exact authority through an authorized mission",
  "related_ids": []
}
```

The response never reports success when required work remains incomplete.

## 3. CLI design

The target namespace is:

```text
erasmus knowledge <resource> <operation>
```

An initial implementation may expose a temporary `erasmus-knowledge` console script if the existing CLI router cannot accept nested commands without unrelated refactoring. Both surfaces must invoke the same service contracts and emit identical JSON.

### 3.1 Global options

```text
--db <path>
--state-root <path>
--request <json-file>
--mission <id>
--actor <actor-id>
--authority <authority>       repeatable
--idempotency-key <value>
--expected-revision <id=rev>  repeatable
--policy <id@version>
--registry <snapshot-id>
--channel <channel-id>
--scope <json-file>
--timeout-seconds <number>
--dry-run
--format json|table|jsonl
--output <path>
--no-color
```

Default machine output is JSON. Table output is a read-only presentation convenience. JSONL is used for streaming jobs or bulk inspection.

### 3.2 Source commands

```powershell
erasmus knowledge source add --path D:\Knowledge\paper.pdf ...
erasmus knowledge source inspect <source-id>
erasmus knowledge source verify <source-id>
erasmus knowledge source list --scope <scope.json>
erasmus knowledge source tombstone <source-id> --reason "..."
erasmus knowledge source impact <source-id>
```

`source add` performs registration and approved extraction only when the request names the extractor profile. It never synthesizes claims implicitly.

### 3.3 Candidate commands

```powershell
erasmus knowledge candidate import-foundry D:\Candidates\bundle ...
erasmus knowledge candidate list --disposition quarantined
erasmus knowledge candidate inspect <candidate-id>
erasmus knowledge candidate admit <candidate-id> ...
erasmus knowledge candidate reject <candidate-id> --reason-code ...
erasmus knowledge candidate retry <candidate-id> --from-checkpoint ...
```

### 3.4 Claim and comparison commands

```powershell
erasmus knowledge claim decompose <candidate-id> ...
erasmus knowledge claim inspect <candidate-claim-id>
erasmus knowledge compare run <candidate-claim-id> --observation-only
erasmus knowledge compare inspect <proposal-id>
erasmus knowledge reconcile propose <candidate-claim-id>
erasmus knowledge reconcile decide <proposal-id> --action corroborate ...
```

The final decision command re-evaluates policy and all gates; it does not trust proposal fields.

### 3.5 Concept, entity, and relationship commands

```powershell
erasmus knowledge entity create --input entity.json ...
erasmus knowledge entity alias-add <entity-id> --input alias.json ...
erasmus knowledge identity propose --input identity-proposal.json
erasmus knowledge identity decide <proposal-id> ...
erasmus knowledge concept create --input concept-revision.json ...
erasmus knowledge concept inspect <concept-id> --revision current
erasmus knowledge concept preview <concept-id> --snapshot <id>
erasmus knowledge relationship add --input relationship.json ...
erasmus knowledge relationship inspect <relationship-id>
```

### 3.6 Question and synthesis commands

```powershell
erasmus knowledge question create --input question.json ...
erasmus knowledge question inspect <question-id>
erasmus knowledge question transition <question-id> --to investigating ...
erasmus knowledge question mission-propose <question-id>
erasmus knowledge synthesis produce --input synthesis-request.json ...
erasmus knowledge synthesis inspect <synthesis-id>
erasmus knowledge synthesis review <synthesis-id> --review <review.json> ...
```

A synthesis command writes `provisional` output only. It cannot close a question or become canonical without separate decisions.

### 3.7 Review and lifecycle commands

```powershell
erasmus knowledge review record --input review.json ...
erasmus knowledge review inspect <review-id>
erasmus knowledge lifecycle evaluate <concept-id> --target validated --dry-run
erasmus knowledge lifecycle transition <concept-id> --target validated ...
erasmus knowledge contradiction inspect <set-id>
erasmus knowledge contradiction resolve <set-id> --decision <json-file> ...
```

### 3.8 Policy and registry commands

```powershell
erasmus knowledge policy validate <policy.json>
erasmus knowledge policy diff <old-policy> <new-policy>
erasmus knowledge policy evaluate --request <json-file>
erasmus knowledge policy inspect <policy-id@version>
erasmus knowledge registry validate <registry.json>
erasmus knowledge registry inspect <snapshot-id>
erasmus knowledge registry diff <old> <new>
erasmus knowledge channel inspect <channel-id>
```

Policy/registry activation is deliberately excluded from ordinary knowledge commands until separately authorized. A protected governance command or installer-controlled path handles activation.

### 3.9 Publication commands

```powershell
erasmus knowledge publish plan --channel <id> --output plan.json ...
erasmus knowledge publish preview --plan plan.json --dest D:\Preview
erasmus knowledge publish validate --plan plan.json
erasmus knowledge publish apply --plan plan.json ...
erasmus knowledge publish status <snapshot-id>
erasmus knowledge publish diff <snapshot-a> <snapshot-b>
erasmus knowledge publish rollback --channel <id> --to <snapshot-id> ...
erasmus knowledge publish withdraw <snapshot-id> --reason "..." ...
```

`publish apply` accepts an exact approved plan digest. It will not regenerate an open-ended plan during the side effect.

### 3.10 Projection and retrieval commands

```powershell
erasmus knowledge projection build --kind fts --snapshot <id> ...
erasmus knowledge projection status <projection-id>
erasmus knowledge projection verify <projection-id>
erasmus knowledge projection retire <projection-id> ...
erasmus knowledge retrieve --request retrieval.json
erasmus knowledge retrieve-explain --packet <packet-id>
erasmus knowledge context-render --packet <packet-id> --budget 1200
```

### 3.11 Freshness and maintenance commands

```powershell
erasmus knowledge freshness assess <subject-id>
erasmus knowledge freshness list --state stale
erasmus knowledge revalidation propose <subject-id>
erasmus knowledge maintenance status
erasmus knowledge maintenance pause
```

### 3.11A Uncertainty, impact, and serving-control commands

```powershell
erasmus knowledge uncertainty record --input uncertainty.json ...
erasmus knowledge uncertainty inspect <uncertainty-id>
erasmus knowledge materiality assess --input assessment-request.json ...
erasmus knowledge use inspect <use-receipt-id>
erasmus knowledge impact analyze <invalidation-event-id> --dry-run
erasmus knowledge impact inspect <impact-id>
erasmus knowledge directive list --channel <channel-id>
erasmus knowledge directive inspect <directive-id>
erasmus knowledge directive apply --input approved-directive.json ...
erasmus knowledge directive supersede <directive-id> --input replacement.json ...
```

Directive mutation is consequential. The final command re-evaluates exact policy, authority, impact evidence, channel/scope, and expected directive-set revision; a model or source cannot apply a directive.

### 3.12 Diagnostics and recovery commands

```powershell
erasmus knowledge status
erasmus knowledge doctor
erasmus knowledge integrity
erasmus knowledge jobs list
erasmus knowledge jobs inspect <job-id>
erasmus knowledge jobs cancel <job-id>
erasmus knowledge jobs resume <job-id>
erasmus knowledge audit query --subject <id>
erasmus knowledge backup D:\Backups\knowledge-backup.erb
erasmus knowledge restore D:\Backups\knowledge-backup.erb --validate-only
erasmus knowledge recover --inspect
erasmus knowledge recover --apply <recovery-plan-id> ...
```

`recover --apply` requires a deterministic recovery plan produced by `--inspect`; it does not invent repair actions interactively.

## 4. Long-running job model

Source extraction, candidate decomposition, comparison, projection builds, publication, revalidation, and large imports may be durable jobs.

### 4.1 `KnowledgeJob`

```json
{
  "job_id": "urn:erasmus:knowledge-job:<uuid>",
  "request_id": "...",
  "mission_id": 123,
  "operation": "projection:build",
  "state": "queued",
  "priority": 100,
  "lease": null,
  "checkpoint": {},
  "attempt": 0,
  "retry_limit": 2,
  "cancel_requested": false,
  "progress": {
    "completed_units": 0,
    "total_units": null,
    "current_stage": "queued"
  },
  "created_at": "ISO-8601",
  "started_at": null,
  "completed_at": null,
  "failure": null
}
```

States:

- `queued`
- `running`
- `paused`
- `blocked`
- `cancelling`
- `cancelled`
- `completed`
- `failed`

Rules:

- Jobs are not missions; a job is one bounded execution under a mission.
- Job state is operational and mutable through guarded transitions; receipts and checkpoints are append-only.
- Leases expire and can be recovered deterministically.
- Cancellation is cooperative, bounded, and produces a terminal receipt.
- Retry occurs only for typed retryable failures and within the request budget.
- Non-idempotent side effects must not retry after an ambiguous commit point without reconciliation.
- Completion means the operation's acceptance receipt exists, not merely that the worker exited.

### 4.2 Progress events

JSONL progress events contain:

- job/request IDs;
- stage;
- completed/total units;
- current source/subject ID where safe;
- elapsed time;
- warnings;
- checkpoint ID;
- terminal result/failure.

Progress never includes hidden reasoning or protected source text.

## 5. Exit codes

| Code | Meaning |
|---:|---|
| `0` | Operation completed and all requested gates passed |
| `1` | Valid request completed with a negative governed result, such as validation failure |
| `2` | CLI/request syntax or contract error |
| `3` | Authority, mission, policy, or approval denied |
| `4` | Source, subject, revision, snapshot, projection, or dependency not found |
| `5` | Conflict, stale expected revision, or idempotency conflict |
| `6` | Runtime/tool/parser/model dependency unavailable |
| `7` | Timeout, cancellation, or retry budget exhausted |
| `8` | Integrity, publication, projection, backup, or recovery failure |
| `9` | Security/privacy violation or protected-content block |

Human-readable messages go to stderr. Machine response goes to stdout. An error stack is emitted only under an explicit local diagnostic flag and must redact secrets.

## 6. Dry-run contract

Every consequential command supports `dry_run` unless the operation is inherently read-only.

Dry run:

- validates request, mission, authority, policy, scope, expected revisions, evidence, reviews, and deterministic prerequisites;
- produces a proposed mutation/publication/recovery plan and exact remaining gates;
- does not write authoritative records, source bytes, snapshot directories, projections, or current pointers;
- may write an explicitly labeled ephemeral diagnostic file under a controlled work root;
- never produces a receipt claiming the real operation completed.

## 7. Health and readiness

`erasmus knowledge doctor` reports separately:

- database integrity and schema version;
- active policy and digest;
- active semantic registry snapshot and digest;
- publication channels and current snapshot receipts;
- source-store root and write/read checks;
- work/snapshot/projection root confinement;
- pending/blocked/stale jobs;
- parser/extractor availability;
- local semantic runtime availability and advertised model;
- projection readiness and snapshot compatibility;
- active directive-set digests and blocked/qualified counts per channel;
- incomplete impact analyses and downstream notifications;
- stale/source-unavailable counts;
- backup age and last restore test;
- recovery-required conditions.

Readiness states:

- `ready`
- `degraded`
- `blocked`
- `recovery_required`

A degraded system may allow exact/lexical reads while vector/model services are unavailable. It may not silently skip required publication or promotion gates.

## 8. Local service boundary

### 8.1 Initial implementation

Prefer in-process invocation in the existing Python CLI/kernel. This minimizes infrastructure and preserves one SQLite writer.

### 8.2 Future persistent service

A later persistent runtime may expose the same contracts through:

- Windows named pipe;
- authenticated loopback HTTP;
- Tauri IPC adapter;
- in-process Rust/Python FFI only after a separately validated boundary.

Requirements:

- local-only by default;
- explicit authentication/authorization;
- one authoritative mutation coordinator;
- request size and concurrency limits;
- cancellation and backpressure;
- no direct SQL endpoint;
- no arbitrary file path access;
- structured audit and health endpoints;
- protocol version negotiation.

### 8.3 MCP and agent adapters

MCP or other agent protocols may expose:

- read-only status, inspect, retrieve, and evidence-packet resources;
- proposal operations that create quarantined candidates or mission candidates.

They do not expose unrestricted publish, policy activation, registry activation, protected source retrieval, or raw database mutation. Protocol content remains untrusted data.

## 9. Tauri boundary

A future Tauri 2 knowledge UI is a client of the same service. It may provide:

- source/candidate queues;
- claim comparison and evidence views;
- contradiction review;
- question/synthesis review;
- lifecycle and policy-gate status;
- publication preview/diff;
- projection health;
- audit/recovery views.

It must not:

- directly read/write SQLite;
- edit the current snapshot;
- store authority in browser state;
- treat a clicked approval as sufficient without a signed/receipted service command;
- hide material contradiction, stale state, or missing evidence.

UI state is disposable. Reopening the app reconstructs state from service records.

## 10. Operator workflows

### 10.1 Ingest and review a Foundry bundle

```powershell
# Validate the external candidate bundle first.
erasmus-foundry validate `
  D:\Knowledge\candidates `
  --write-report

# Import into Phase 3 quarantine through an authorized mission.
erasmus knowledge candidate import-foundry `
  D:\Knowledge\candidates `
  --mission 123 `
  --actor human:governor `
  --authority knowledge:ingest `
  --idempotency-key "foundry-<bundle-digest>" `
  --policy urn:erasmus:knowledge-policy:default@1.0.0 `
  --registry urn:erasmus:semantic-registry-snapshot:<id> `
  --format json

# Inspect before any semantic or ledger mutation.
erasmus knowledge candidate list `
  --disposition quarantined `
  --format table
```

### 10.2 Reconcile one candidate claim

```powershell
erasmus knowledge compare run <candidate-claim-id> `
  --mission 124 `
  --actor agent:knowledge-analyst/1.0.0 `
  --authority knowledge:read `
  --dry-run `
  --format json

erasmus knowledge reconcile propose <candidate-claim-id> `
  --mission 124 `
  --actor agent:knowledge-analyst/1.0.0 `
  --authority knowledge:reconcile `
  --idempotency-key "proposal-<claim-digest>-<snapshot-id>"
```

A separate authorized actor records the final decision after review.

### 10.3 Publish a channel snapshot

```powershell
erasmus knowledge publish plan `
  --channel urn:erasmus:publication-channel:private-default `
  --mission 130 `
  --actor process:erasmus-okf-planner/1.0.0 `
  --authority knowledge:publish `
  --output D:\Knowledge\plans\snapshot-plan.json `
  --dry-run

erasmus knowledge publish validate `
  --request D:\Knowledge\plans\snapshot-plan.json

erasmus knowledge publish apply `
  --request D:\Knowledge\plans\approved-snapshot-plan.json
```

### 10.4 Recover after interrupted publication

```powershell
erasmus knowledge recover --inspect --format json > recovery-plan.json
# Review the exact current pointer, receipts, and suggested deterministic action.
erasmus knowledge recover --apply recovery-plan.json `
  --mission 131 `
  --actor human:governor `
  --authority knowledge:admin `
  --idempotency-key "recovery-<plan-digest>"
```

## 11. Backup and restore

The knowledge backup command coordinates with the existing Erasmus database backup and records:

- SQLite backup digest;
- source artifact inventory/digests according to retention policy;
- active policy and registry snapshots;
- publication channels/current pointers;
- immutable snapshot manifests;
- projection manifests;
- configuration profile digests;
- backup receipt.

Projection artifacts may be excluded if the manifest declares them rebuildable.

Restore stages:

1. validate archive and receipt without mutation;
2. verify available disk and target-root confinement;
3. restore into an isolated target root;
4. run database integrity/migrations in validation mode;
5. verify source and snapshot digests;
6. reconcile current pointers and publication receipts;
7. rebuild or reject incompatible projections;
8. run retrieval fixtures;
9. atomically activate restored root only after approval;
10. record restore receipt and rollback target.

Restore never overwrites the only known-good state in place.

## 12. Logging and observability

Default local logs are structured JSONL with:

- timestamp;
- severity;
- request/job/mission IDs;
- operation and stage;
- actor role, not secret identity data where unnecessary;
- subject/source/snapshot/projection IDs;
- tool/runtime component identity;
- result/failure code;
- duration and resource counts;
- evidence/receipt references;
- redaction indicators.

Logs exclude:

- hidden chain of thought;
- credentials;
- unrestricted source text;
- private absolute paths in shared/public logs;
- full prompts unless an explicit protected diagnostic mission authorizes capture.

## 13. Concurrency and backpressure

- One SQLite mutation coordinator is authoritative in the initial implementation.
- Read operations may run concurrently against a consistent snapshot/transaction.
- Publication is serialized per channel.
- Reconciliation is serialized per affected claim/concept revision through expected revisions.
- Source registration deduplicates by digest.
- Projection builds are serialized per `(kind, snapshot, configuration)` idempotency key.
- Queues have maximum depth and per-operation concurrency.
- Candidate floods produce backpressure and a bounded blocked result rather than unbounded memory use.
- High-priority recovery and integrity work can pause lower-priority semantic jobs.

## 14. Version negotiation

Every request names its contract major version. Service status advertises supported versions and feature flags. Unsupported major versions return `unsupported_contract_version` without partial work.

A CLI built against a newer service may use only operations whose request/response versions are mutually supported. Human-readable output cannot hide version incompatibility.

## 15. Error recovery matrix

| Failure | Automatic behavior | Operator action |
|---|---|---|
| Local model unavailable | Pause semantic job; deterministic reads remain | Start/repair runtime or cancel job |
| Parser failure on one source | Mark partial/failed coordinate; no invented text | Inspect receipt; choose approved alternate extractor |
| Revision conflict | No retry with stale input | Re-read current revision and create a new command |
| Policy denied | No mutation | Obtain policy-compliant mission/approval or stop |
| Projection corrupted | Mark failed/stale; fall back if permitted | Rebuild from verified snapshot |
| Publication validation failure | Snapshot remains non-current | Inspect receipt and repair inputs/renderer |
| Crash after pointer swap | Enter recovery-required | Apply deterministic pointer/receipt recovery plan |
| Source removed | Mark unavailable; impact analysis | Revalidate, redact, withdraw, or replace |
| Disk full | Stop at safe checkpoint | Free space and resume exact job |
| Secret detected | Block publication | Redact/declassify through protected review |

## 16. Acceptance tests

A promoted implementation must prove:

1. CLI and in-process service emit schema-equivalent results.
2. Machine JSON is stable and stdout contains no unrelated text.
3. Every mutation requires mission, actor, exact authority, policy, idempotency, and expected revision where applicable.
4. Dry-run performs no authoritative or filesystem side effect.
5. Exit codes match typed failures.
6. Long-running jobs resume exactly once after process restart.
7. Cancellation produces a terminal receipt and no ambiguous side effect.
8. Retrying an idempotent request returns the original result.
9. Stale expected revisions fail before mutation.
10. Publication serializes independently per channel.
11. Read-only degraded operation works without the semantic runtime when policy permits.
12. Tauri/MCP adapters cannot bypass the service boundary or expand authority.
13. Backup/restore validates in isolation and preserves the original state until activation.
14. Recovery plans are deterministic, reviewable, and idempotent.
15. Logs and diagnostics contain no synthetic secrets or protected source content.
16. Windows PowerShell commands work with spaces, Unicode paths, and long-path-safe roots.
17. Unsupported contract versions fail closed.
18. `doctor` distinguishes ready, degraded, blocked, and recovery-required states using capability checks rather than process existence alone.
