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
#   "missions": 0,
#   "experience_candidates": 0,
#   "immune_state": 0,
#   "checkpoints": 0,
#   "sessions": 0,
#   "schema_versions": [1, 2, 3]
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

## Run sleep consolidation (idempotent — safe to run repeatedly)

```powershell
erasmus --db state\erasmus.db sleep
# Example output after two correction events have been added:
# {
#   "events": 2,
#   "experience_candidates": 2,
#   "last_event_id": 2
# }
```

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
# All tests must pass.  As of Mission 01, there are 55 tests.
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
