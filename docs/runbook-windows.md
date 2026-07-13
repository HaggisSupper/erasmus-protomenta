# Erasmus Windows Runbook

Verification commands for durable continuity on Windows (PowerShell 7+).
All commands assume the repository root is the working directory and the
virtual environment is active.  Replace `state\erasmus.db` with another path
if you use a non-default location.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Initialise a fresh database

```powershell
erasmus --db state\erasmus.db init
# Expected output:  initialized state\erasmus.db
```

## Status (table row counts + applied schema versions)

```powershell
erasmus --db state\erasmus.db status
# Expected output (new database):
# {
#   "events": 0,
#   "propositions": 0,
#   "epistemic_evidence": 0,
#   "proposition_transitions": 0,
#   "missions": 0,
#   "experience_candidates": 0,
#   "sleep_runs": 0,
#   "sleep_items": 0,
#   "sleep_candidates": 0,
#   "immune_state": 0,
#   "immune_incidents": 0,
#   "immune_findings": 0,
#   "checkpoints": 0,
#   "sessions": 0,
#   "schema_versions": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
# }
```

## Database integrity check

```powershell
erasmus --db state\erasmus.db integrity
# Expected output:
# [
#   "ok"
# ]
```

## Inspect the latest checkpoint

```powershell
erasmus --db state\erasmus.db checkpoint
# Returns null when no checkpoint has been saved yet, or the most recent
# checkpoint as a JSON object with all frontier fields and source_event_ids.
```

## Run sleep consolidation (recoverable and idempotent)

```powershell
erasmus --db state\erasmus.db sleep
# Output includes the run id, stage history, disposition counts, source-event
# links, candidate provenance, and reasons. Re-running with no new events
# returns zero events and creates no duplicate durable effects.
```

To inspect a prior run or record an explicit evidence-backed decision:

```powershell
erasmus --db state\erasmus.db sleep-report 1

# This records approval only; it does not mutate the canonical ledger or train
# an adapter. candidate 3 must be a proposition_change and evidence 7 must
# already exist in the epistemic ledger.
erasmus --db state\erasmus.db sleep-decide 3 approved belief 7 `
  --actor reviewer --authority sleep:promote `
  --reason "independent evidence and scope reviewed"
```

Source events are never deleted. External and Erasmus-authored content is
quarantined; behavioral lessons remain deferred; proposition decisions require
ledger evidence plus `sleep:promote` authority. A failed run retains its stage
and classified items, then safely resumes from the same run id.

## Backup and restore

```powershell
# Backup the live database to a timestamped file
$ts = (Get-Date -Format "yyyyMMdd_HHmmss")
erasmus --db state\erasmus.db backup "backups\erasmus_$ts.db"

# Restore from that backup into the live database path
erasmus --db state\erasmus.db restore "backups\erasmus_$ts.db"
```

Both commands use `sqlite3.Connection.backup()` — the backup is a valid
SQLite database that can be opened with any SQLite tool for independent
inspection.

## Restart / reopen recovery verification

This sequence verifies that the kernel resumes correctly after a simulated
process termination.

```powershell
# 1. Initialise and write a test event.
erasmus --db state\test_recovery.db init

python - <<'PY'
from erasmus.store import Store
from erasmus.checkpoint import Checkpoint, save_checkpoint

store = Store("state/test_recovery.db")
store.init()
sid  = store.start_session()
eid  = store.add_event("observation", "recovery test event")
save_checkpoint(store, Checkpoint(
    frontier                  = "testing recovery path",
    proposition               = "kernel resumes correctly",
    strongest_support         = "deterministic WAL guarantees durability",
    strongest_contradiction   = "partial writes could corrupt if no transaction",
    unresolved_tension        = "none known at this checkpoint",
    active_mode               = "analysis",
    next_move                 = "verify checkpoint survives process restart",
    source_event_ids          = [eid],
))
print(f"session={sid}  event={eid}")
PY

# 2. Reopen and inspect — no replay needed.
erasmus --db state\test_recovery.db checkpoint

# 3. Verify interrupted-session detection.
python - <<'PY'
from erasmus.store import Store
store = Store("state/test_recovery.db")
store.init()
interrupted = store.interrupted_sessions()
print("interrupted sessions:", interrupted)
PY

# 4. Clean up the test database.
Remove-Item state\test_recovery.db -Force
Remove-Item state\test_recovery.db-wal -ErrorAction SilentlyContinue
Remove-Item state\test_recovery.db-shm -ErrorAction SilentlyContinue
```

## Run the test suite

```powershell
pip install pytest
python -m pytest tests\ -v
# All tests must pass.
```

## Schema audit

To list every applied migration with its timestamp:

```powershell
python - <<'PY'
import sqlite3, json
db = sqlite3.connect("state/erasmus.db")
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT version, applied_at FROM schema_version ORDER BY version"
).fetchall()
print(json.dumps([dict(r) for r in rows], indent=2))
PY
```

## Capability graph verification

The version-controlled manifest is canonical. SQLite is a rebuildable
operational projection.

```powershell
$manifest = "capabilities\okf\pr-governance"
$db = "state\capability_graph.db"

erasmus --db $db graph-validate $manifest
erasmus --db $db graph-import $manifest
erasmus --db $db graph-list
erasmus --db $db graph-inspect "merge_pull_request@1.0.0"
erasmus --db $db graph-plan inspect_repository --authority repository:read
erasmus --db $db graph-export "state\exported-capabilities"

# The supported OKF 0.1 subset must round-trip byte-for-byte.
$canonical = Get-ChildItem $manifest -Recurse -File | ForEach-Object {
    [PSCustomObject]@{ Path = $_.FullName.Substring((Resolve-Path $manifest).Path.Length); Hash = (Get-FileHash $_.FullName).Hash }
}
$exported = Get-ChildItem "state\exported-capabilities" -Recurse -File | ForEach-Object {
    [PSCustomObject]@{ Path = $_.FullName.Substring((Resolve-Path "state\exported-capabilities").Path.Length); Hash = (Get-FileHash $_.FullName).Hash }
}
if (Compare-Object $canonical $exported -Property Path, Hash) { throw "OKF round-trip drift" }

python -m pytest tests\test_capability_graph.py -v
```

The canonical interchange is an OKF 0.1 Markdown bundle. Its JSON-form
frontmatter is a valid YAML 1.2 subset and keeps parsing dependency-free.
`merge_guarded_pull_request` intentionally returns no plan until every
prerequisite has successful execution evidence bound to the requested exact
head SHA. Re-importing the canonical manifest rebuilds the projection; schema
migration rollback is the governed revert of migration 4.

## Signed tool registry verification

```powershell
$db = "state\tool_registry.db"
$cache = "state\tool-cache"
$target = "any-py3-none"

erasmus --db $db --tool-cache $cache graph-import "capabilities\okf\pr-governance"
erasmus --db $db --tool-cache $cache tool-publisher-register "tools\publishers.json"

Get-ChildItem "tools\manifests\*.json" | ForEach-Object {
    erasmus --db $db --tool-cache $cache tool-register $_.FullName
}

$manifest = "tools\manifests\sqlite_reader.json"
$artifact = "tools\artifacts\sqlite_reader.py"
erasmus --db $db --tool-cache $cache tool-verify $manifest $artifact
erasmus --db $db --tool-cache $cache tool-install $manifest $artifact
erasmus --db $db --tool-cache $cache tool-activate sqlite_reader 1.0.0 $target
erasmus --db $db --tool-cache $cache tool-health sqlite_reader 1.0.0 $target --authority database:read
erasmus --db $db --tool-cache $cache tool-list
erasmus --db $db --tool-cache $cache tool-export "state\tool-registry-export.json"
erasmus --db $db toolchain-validate TOOLCHAIN.md --manifests tools\manifests

# Reversible removal; audit history and the signed manifest remain.
erasmus --db $db --tool-cache $cache tool-deactivate sqlite_reader 1.0.0 $target
erasmus --db $db --tool-cache $cache tool-uninstall sqlite_reader 1.0.0 $target

python -m pytest tests\test_tool_registry.py -v
```

Never place the private signing key in the repository, SQLite registry, cache,
environment logs, or `TOOLCHAIN.md`. A signature verifies publisher possession;
it does not grant capability authority.

## Capability runtime verification

The runtime dispatches only implementations explicitly configured by the local
process. A contract must advance through every lifecycle gate before invocation;
all successful and rejected requests are recorded in the append-only invocation
ledger.

```powershell
python -m pytest tests\test_capability_runtime.py -v
```

Reference handlers cover Draft 2020-12 JSON Schema validation, SHA-256 hashing
of text or files inside configured roots, and bounded read-only SQLite FTS
queries. External handlers exchange canonical JSON over standard input/output
and return typed timeout, exit-code, and output-validation failures.

## Bounded mission verification

```powershell
$db = "state\mission-engine.db"
erasmus --db $db init
erasmus --db $db graph-import "capabilities\okf\pr-governance"

# Explicitly configure and advance the reviewed reference implementation.
@'
from erasmus.capability_runtime import CapabilityRuntime, validate_json_schema
from erasmus.store import Store

store = Store("state/mission-engine.db")
store.init()
runtime = CapabilityRuntime(store)
runtime.configure(
    "validate_json_schema", "1.0.0",
    "jsonschema_validator", "1.0.0", validate_json_schema,
)
for state in ("implemented", "isolated_test", "adversarial_review", "approved", "active"):
    runtime.transition("validate_json_schema", "1.0.0", state)
'@ | python -

$mission = erasmus --db $db mission-create --contract "contracts\fixtures\valid_mission.json"
erasmus --db $db mission-inspect $mission
erasmus --db $db mission-authorize $mission --actor Protomentat --evidence "approval:manual"
erasmus --db $db mission-run-one $mission
erasmus --db $db mission-inspect $mission

python -m pytest tests\test_missions.py -v
```

`mission-run-one` never loops. Authority expansion and irreversible steps create
append-only approval requests. `mission-pause`, `mission-resume`,
`mission-cancel`, and `mission-rollback` apply only declared deterministic state
transitions; uncertain interrupted side effects fail closed.

## Epistemic ledger verification

Evidence insertion and proposition changes are separate commands. Retrieval,
model repetition, and confidence scores never change proposition status by
themselves.

```powershell
$db = "state\epistemic-ledger.db"
erasmus --db $db init

$evidence = erasmus --db $db ledger-evidence-add "registered observation" `
  --type evidence --source-kind observation `
  --provenance '{"source":"instrument-7","sample":"A"}' `
  --trust primary --effective-date 2026-07-13 --scope lab `
  --actor operator --authority evidence:write | ConvertFrom-Json

$claim = erasmus --db $db ledger-propose "Treatment A changes outcome B" `
  $evidence.evidence_id --scope lab --actor operator `
  --authority ledger:write | ConvertFrom-Json

erasmus --db $db ledger-inspect $claim.proposition_id
erasmus --db $db ledger-query $claim.proposition_id
python -m pytest tests\test_ledger.py -v
```

Rollback is a code rollback plus database restore from the pre-migration
backup. Migration 10 is intentionally forward-only because its records are
append-only; do not drop ledger tables from a live database.

## Cognitive immune cascade verification

The cascade runs deterministic checks first, wakes only matching dormant
investigators, records advisory mitigations, and returns investigators to
sleep. It has no authority to update canonical evidence or propositions.

```powershell
$db = "state\immune-cascade.db"
erasmus --db $db init

@'
{
  "event_type": "retrieval",
  "source_kind": "rag",
  "attempted_belief_promotion": true,
  "consequence": 0.7,
  "canonical_ref": "proposition:1"
}
'@ | Set-Content "state\immune-event.json"

erasmus --db $db immune-process "state\immune-event.json" --authority immune:inspect
erasmus --db $db immune-agents
python -m pytest tests\test_immune.py -v
```

False-positive decisions require `immune:regulate` authority and are appended
with actor and reason. After repeated verified false positives, the regulator
suppresses the matching specialist while leaving the incident auditable.
Consequential unresolved findings use the `escalate` outcome for the
Protomentat. Rollback restores the database backup taken before migration 11;
never delete live immune audit rows.
