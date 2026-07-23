# Guarded Local Repository Mission Implementation Report

Status: `DONE_WITH_CONCERNS`

## Outcome

Implemented the approved Phase 1 guarded local repository mission as one
in-process service using the existing SQLite store. Declared and governed-worker
patches share one deterministic gate, execute only argument-vector commands,
push only their declared branch to a local bare remote, persist append-only
transition/evidence history and a draft comparison, then stop at
`awaiting_human`. No merge method, command, state, remote service, background
worker, Docker configuration, or new dependency was added.

## Commits

1. `2465d6a` — Add repository mission contract and persistence
2. `cdfd4ed` — Add bounded Git patch gate
3. `280e5c2` — Execute guarded local repository missions
4. `22c5b68` — Expose guarded repository mission verification

## Files

- `contracts/repository-mission.schema.json`: strict typed mission contract.
- `src/erasmus/migrations.py`: additive migration 17 and explicit offline
  `rollback_repository_mission_migration`.
- `src/erasmus/repository_missions.py`: immutable contract, bounded Git runner,
  shared patch gate, durable service execution, inspection, recovery, rollback,
  review, push, and draft-record behavior.
- `src/erasmus/cli/main.py`: create/run/inspect commands only.
- `scripts/verify_guarded_repository_mission.py`: disposable Windows-safe manual
  verifier for declared and worker patch modes.
- `tests/test_repository_missions.py`: contract, migration, real-Git gate,
  end-to-end, negative-boundary, recovery, rollback, and CLI coverage.
- `tests/test_capability_graph.py`, `tests/test_continuity.py`: migration audit
  expectations advanced from 16 to 17.
- `docs/runbook-windows.md`, `README.md`: commands, behavior, and rollback.

## Contracts Added or Modified

- Added `RepositoryMissionContract.from_dict(raw)` with resolved
  `workspace_root` containment, strict additional-property rejection, relative
  allowlisted paths, patch-source exclusivity, independent review, explicit
  review authority, countercase, test timeout, stopping condition, and rollback
  description.
- Added `LocalGitRunner.run(repo, args, timeout)` using a discovered absolute Git
  executable, `shell=False`, captured UTF-8 output, timeouts, and exact tuples.
- Added `PatchGate.validate_and_apply(...) -> PatchEvidence`; both patch sources
  use this same path.
- Added `RepositoryMissionService.create`, `run`, and `inspect`. There is no
  merge API.
- Added append-only repository mission transitions/evidence/draft records and
  additive migration rollback.
- Added CLI commands `repository-mission-create`, `repository-mission-run`, and
  `repository-mission-inspect`. There is no merge command.

## TDD and Verification Evidence

- Task 1 red: focused collection failed because
  `erasmus.repository_missions` did not exist.
- Task 1 green: `12 passed in 0.67s`.
- Task 2 red: focused collection failed because `LocalGitRunner` was absent.
- Task 2 green: patch-gate subset `10 passed`; combined Task 1/2 file
  `22 passed in 12.80s`.
- Task 3 red: declared end-to-end test failed because `run` did not exist.
- Task 3 green: integration subset `9 passed`; then the focused file
  `31 passed in 130.62s`.
- Task 4 red: two CLI tests failed because the commands were unregistered.
- Task 4 green: CLI subset `2 passed`; focused file before the two final safety
  additions `33 passed in 231.22s`; additive-schema rollback and fail-closed
  recovery-mismatch subset `2 passed in 5.75s`.
- Manual verification: `py -3.12 scripts\verify_guarded_repository_mission.py`
  exited 0, both modes were `awaiting_human`, and both local remote branches
  were verified.
- Compile gate: `py -3.12 -m compileall -q src tests scripts` exited 0.
- Diff gate: `git diff --check` exited 0 before the Task 4 commit.
- State mapping: bounded `graphify update
  C:\Development\erasmus-protomenta\.worktrees\guarded-repository-mission`
  succeeded with 1,015 nodes, 2,475 edges, and 43 communities. Generated
  `graphify-out` artifacts were removed after the gate.
- Full regression attempt 1: `336 passed, 1 skipped, 4 failed`; all four failures
  were stale hard-coded migration-16 assertions.
- Full regression attempt 2: `341 passed, 1 skipped, 1 failed`; the only failure
  was one additional stale migration-16 assertion in the same upgrade test.
  After correcting it, that exact upgrade test plus the retryable migration test
  passed: `2 passed in 1.03s`. Coordination explicitly prohibited a third full
  run, so there is no single post-final-edit all-green full-suite invocation.

## Acceptance Mapping

1. Declared mode reaches `awaiting_human`: covered by real-Git integration and
   the manual verifier.
2. Governed-worker mode reaches the same state through `PatchGate`: covered by
   integration and manual verification; the worker receives only its declared
   request mapping.
3. Worker has no repository/review/push/merge authority: provider signature is
   data-in/diff-out and negative assertions exclude root and authority fields.
4. Consequential transitions preserve evidence and rollback data: append-only
   schema, evidence digests, transition references, draft record, and inspection
   output are covered.
5. Negative authority, provenance, containment, test-failure, and recovery:
   denied authority, invalid roots/paths, malformed/binary/out-of-scope patches,
   test rollback, dirty/stale state, reviewer/countercase boundaries, push
   failure, interruption recovery, and mismatch blocking are covered.
6. No merge API or transition: no method/CLI/state exists; CLI negative test
   confirms merge is an invalid command.
7. Declared mode works without a worker runtime: declared integration and manual
   mode call no provider.
8. Windows Python 3.12: exact `py -3.12` manual verifier and compile gate pass.

## New Dependencies

None. Runtime contract validation uses the repository's existing `jsonschema`
dependency when installed and a deterministic standard-library validator for
the standalone `py -3.12` disposable verifier.

## Known Limitations and Concerns

- The approved brief named schema version 10, but this branch already contained
  unrelated migrations 10 through 16. Reusing 10 would corrupt migration
  identity, so the implementation uses the next free version, 17.
- A final single-command green full-suite result was not obtained after the last
  stale assertion correction because coordination prohibited another full run.
  The prior run had 341 passing tests, one skip, and only that stale assertion;
  the corrected test and adjacent retry test pass independently.
- The local draft record does not exercise GitHub permissions, branch
  protection, hosted CI timing, or stale remote reviews.
- The service intentionally supports local filesystem bare remotes only.

## 10th-Man Countercase

The strongest reason this change may still be wrong is that a fully successful
local bare-remote loop can overstate readiness for a hosted pull-request loop:
the difficult authority and race failures may occur only at the GitHub boundary,
which this slice deliberately excludes.

## Rollback

1. Revert commits in reverse order: `22c5b68`, `280e5c2`, `cdfd4ed`, then
   `2465d6a`.
2. On an offline database or after restoring the required pre-migration backup,
   call `rollback_repository_mission_migration(db)` to remove only migration-17
   tables, triggers, and its schema-version row. Do not delete live append-only
   evidence without the Protomentat's explicit authority.
3. Repository state is separate. Inspect `rollback_args`, confirm the exact
   mission repository and branch, then run Git with `reset --hard <base-sha>` if
   rollback is authorized. Delete only disposable local verifier repositories.

