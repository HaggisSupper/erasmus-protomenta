# Guarded Local Repository Mission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute declared and governed-worker patches against disposable local Git repositories through a durable evidence-backed flow that stops at human approval.

**Architecture:** Add a focused repository-mission module beside the existing mission engine. It owns typed contract validation, bounded Git execution, one deterministic patch gate, durable transitions, and draft-PR records while reusing the existing SQLite store and worker boundary.

**Tech Stack:** Python 3.12 standard library, SQLite, Git CLI argument vectors, pytest, existing Erasmus Store and Worker MCP contracts.

## Global Constraints

- Remain one process and one SQLite database.
- No shell command strings, GitHub writes, autonomous merge, Docker, placeholders, or new dependencies.
- Worker output is untrusted patch text and receives no repository authority.
- Every failure is durable, inspectable, bounded, and reversible.
- Windows-first operation and the complete existing test suite must remain intact.

---

### Task 1: Contract, persistence, and transition model

**Files:**
- Create: `contracts/repository-mission.schema.json`
- Modify: `src/erasmus/migrations.py`
- Create: `src/erasmus/repository_missions.py`
- Create: `tests/test_repository_missions.py`

**Interfaces:**
- Produces: `RepositoryMissionContract.from_dict(raw)`, `RepositoryMissionError`, and `RepositoryMissionService.create(contract, actor, authority) -> int`.
- Persists: `repository_missions`, `repository_mission_transitions`, `repository_mission_evidence`, and `draft_pull_requests`.

- [ ] Write failing tests proving required fields, resolved-root containment, allowed relative paths, distinct implementer/reviewer, required countercase, append-only transitions, and migration idempotence.
- [ ] Run `python -m pytest tests/test_repository_missions.py -q`; expect import/schema failures.
- [ ] Add schema version 10 with foreign keys, state checks, append-only triggers, and indexes by mission/status.
- [ ] Implement immutable dataclasses and strict schema plus semantic validation. Use `Path.resolve()` and reject absolute/traversing allowlist entries.
- [ ] Implement `create` so one transaction inserts the mission and initial `created` transition.
- [ ] Re-run the focused tests; expect all Task 1 tests to pass.
- [ ] Commit only Task 1 files with `Add repository mission contract and persistence`.

### Task 2: Deterministic Git runner and shared patch gate

**Files:**
- Modify: `src/erasmus/repository_missions.py`
- Modify: `tests/test_repository_missions.py`

**Interfaces:**
- Produces: `LocalGitRunner.run(repo: Path, args: tuple[str, ...], timeout: int = 30) -> CompletedProcess[str]`.
- Produces: `PatchGate.validate_and_apply(repo, patch_text, allowed_paths, expected_head) -> PatchEvidence`.

- [ ] Write failing real-Git tests for a valid text patch and rejection of empty, malformed, binary, absolute, traversing, rename-outside-scope, dirty-tree, stale-HEAD, and disallowed-path patches.
- [ ] Run the focused patch-gate tests; expect missing interfaces.
- [ ] Implement `LocalGitRunner` with a discovered absolute Git executable, `shell=False`, captured UTF-8 output, timeout, and exact argument tuples.
- [ ] Parse `diff --git`, `---`, and `+++` paths conservatively; reject unsupported metadata before `git apply --check` and `git apply`.
- [ ] Re-query `git diff --name-only` after application and reject any changed path outside the allowlist.
- [ ] Store SHA-256 patch evidence and bounded command evidence without environment variables or credentials.
- [ ] Re-run focused tests; expect Task 2 tests to pass.
- [ ] Commit Task 2 files with `Add bounded Git patch gate`.

### Task 3: End-to-end declared and worker mission execution

**Files:**
- Modify: `src/erasmus/repository_missions.py`
- Modify: `tests/test_repository_missions.py`

**Interfaces:**
- Produces: `RepositoryMissionService.run(mission_id, worker_patch_provider=None) -> dict[str, object]`.
- Produces: `RepositoryMissionService.inspect(mission_id) -> dict[str, object]`.
- Worker provider signature: `(request: Mapping[str, object]) -> str` returning unified diff text only.

- [ ] Write failing integration tests using temporary working and bare repositories for declared patch success, governed worker success, test failure rollback, malformed worker response, denied authority, self-review, missing countercase, push failure, and interruption recovery.
- [ ] Run focused integration tests; expect missing execution behavior.
- [ ] Implement durable state steps: `created`, `authorized`, `inspecting`, `branched`, `patch_validated`, `changed`, `tested`, `reviewed`, `draft_pr_recorded`, `awaiting_human`.
- [ ] On test failure restore the recorded base using bounded Git commands, record output digest and rollback evidence, and enter `rolled_back`.
- [ ] Commit and push only the declared mission branch to the declared local bare origin.
- [ ] Persist a draft record with base/head SHAs, changed paths, patch/test digests, reviewer, countercase, and rollback SHA. Expose no merge method or transition.
- [ ] Re-run focused integration tests; expect all Task 3 tests to pass.
- [ ] Commit Task 3 files with `Execute guarded local repository missions`.

### Task 4: CLI, manual verification, documentation, and regression gate

**Files:**
- Modify: `src/erasmus/cli/main.py`
- Create: `scripts/verify_guarded_repository_mission.py`
- Modify: `docs/runbook-windows.md`
- Modify: `README.md`
- Modify: `tests/test_repository_missions.py`
- Modify: `tests/test_migrations.py` if present; otherwise keep migration assertions in `tests/test_repository_missions.py`.

**Interfaces:**
- Commands: `repository-mission-create --contract PATH`, `repository-mission-run ID`, and `repository-mission-inspect ID`.
- Manual verifier exits zero only when both patch modes reach `awaiting_human` and their remote branches exist.

- [ ] Write failing CLI tests for create/run/inspect and a test that no merge command is registered.
- [ ] Run focused CLI tests; expect parser failures.
- [ ] Add the three CLI commands and JSON output without adding a merge command.
- [ ] Implement the disposable manual verifier using `tempfile.TemporaryDirectory`, a local bare origin, a deterministic worker fake, and explicit final assertions.
- [ ] Document the PowerShell command `py -3.12 scripts\verify_guarded_repository_mission.py` and rollback procedure.
- [ ] Run focused tests, the manual verifier, `py -3.12 -m pytest -q`, `py -3.12 -m compileall -q src tests scripts`, and `git diff --check`.
- [ ] Run `graphify update C:\Development\erasmus-protomenta` because code, schema, CLI, and architecture documentation changed.
- [ ] Commit Task 4 files with `Expose guarded repository mission verification`.

## Plan Self-Review

- Every design acceptance criterion maps to Tasks 1-4.
- Both patch modes share exactly one gate.
- The only remote is a disposable local bare repository.
- No task introduces merge authority, a background service, or a new dependency.
- State names, method names, worker signature, and CLI names are consistent across tasks.
