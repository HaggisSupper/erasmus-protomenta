# Guarded Local Repository Mission Design

Status: approved for implementation planning

## Outcome

Prove the Phase 1 guarded pull-request loop against a disposable local Git fixture without GitHub credentials or external writes. Erasmus must accept a bounded mission, apply either a predeclared patch or a governed worker-proposed patch, run declared tests, preserve inspectable evidence, publish a mission branch to a local bare remote, create a durable draft-PR comparison record, and stop for human approval. It must never merge.

## Scope

This slice adds one deterministic repository-mission service inside the existing one-process, one-SQLite kernel. It reuses existing mission, authority, capability, evidence, worker, and 10th-Man contracts. It does not add a scheduler, background service, remote execution, generic plugin system, GitHub integration, autonomous merge, or new persistence service.

## Architecture

`GuardedRepositoryMission` coordinates execution while delegating durable state to the existing store. Operating-system access is confined to an injected `LocalGitRunner` with typed argument lists and a single resolved repository root. The service never accepts shell command strings.

A typed repository-mission contract declares:

- mission identifier and objective;
- resolved repository root and expected base SHA;
- mission branch name;
- allowed relative file paths;
- patch source: `declared` or `worker`;
- declared unified diff when the source is `declared`;
- governed worker request when the source is `worker`;
- an argument-vector test command;
- retry limit and stopping condition;
- rollback command description;
- independent reviewer identity and 10th-Man countercase.

Worker output is untrusted data. A worker can propose unified diff text but receives no filesystem, Git, review, or merge authority. Declared and worker patches pass through the same deterministic validation and application path.

## State Model

The durable state sequence is:

`created -> authorized -> inspecting -> branched -> patch_validated -> changed -> tested -> reviewed -> draft_pr_recorded -> awaiting_human`

Terminal failure states are `blocked`, `quarantined`, `failed`, and `rolled_back`. Every transition records its prior state, next state, timestamp, actor, authority, repository HEAD, reason, and evidence identifiers in append-only history.

Resume is idempotent. Before continuing, the service re-resolves the repository root, verifies repository identity, verifies the recorded HEAD, and checks that the worktree state is consistent with the last durable transition. A mismatch blocks rather than guessing or repairing silently.

## Deterministic Patch Gate

The gate:

1. requires UTF-8 unified diff text;
2. rejects empty patches, binary patches, submodule changes, absolute paths, path traversal, and paths outside the declared allowlist;
3. rejects rename or copy targets outside the allowlist;
4. checks the expected base SHA and clean initial worktree;
5. runs `git apply --check` before applying;
6. applies the patch without invoking a shell;
7. obtains changed paths from Git and verifies the allowlist again;
8. stores the patch SHA-256 and changed-path evidence.

The gate does not interpret model rationale and does not repair malformed worker output.

## Git and Draft-PR Flow

The local fixture contains a working repository with a local bare repository configured as `origin`. On success the service:

1. records base identity and cleanliness;
2. creates the declared mission branch;
3. applies the validated patch;
4. runs the declared test argument vector with a bounded timeout;
5. commits using a deterministic mission-derived message;
6. pushes only the mission branch to the declared local origin;
7. records an independent deterministic review and the supplied 10th-Man countercase;
8. stores a draft-PR record containing base SHA, head SHA, branch, changed paths, diff digest, test command, test exit status, output digest, review identity, countercase, rollback SHA, and `awaiting_human` status.

There is no merge operation in this slice.

## Evidence and Privacy

Consequential evidence is stored as structured records rather than hidden reasoning. Raw test output is bounded and may be stored only for the disposable fixture; its SHA-256 is always stored. Worker prompts and output are bounded, and credentials and environment variables are never persisted. Paths are stored relative to the declared repository root except for the locally resolved root required for containment validation.

## Failure and Recovery

- Dirty initial worktree: block before creating a branch.
- Invalid root or repository identity: block.
- Stale base or changed HEAD: block and require a new mission.
- Invalid or out-of-scope patch: quarantine without modifying canonical state.
- Test failure: record output evidence, restore the recorded rollback SHA for mission-owned changes, and enter `rolled_back`.
- Worker crash, timeout, malformed response, or prose without a patch: quarantine or block according to the existing resolver classification; never infer a patch.
- Interrupted execution: resume only after validating the durable transition, HEAD, and worktree.
- Reviewer equals implementer or lacks review authority: block.
- Missing countercase: block before draft-PR creation.
- Push failure: retain the local commit and evidence, enter `blocked`, and expose the explicit rollback command.

## Persistence

Add a reversible SQLite migration for repository missions, append-only repository mission transitions, bounded evidence, and draft-PR records. Foreign keys bind records to the existing mission where applicable. The rollback migration removes only the new tables and schema-version entry; repository rollback remains a separate explicit Git action.

## Tests

Focused unit tests cover contract validation, path containment, patch parsing, authority separation, transition legality, evidence bounds, and command construction.

Integration tests use real temporary working and bare Git repositories:

- declared patch completes through `awaiting_human`;
- governed worker patch completes through the identical gate;
- dirty worktree is denied;
- stale base and changed HEAD are denied;
- absolute, traversing, binary, malformed, and out-of-allowlist patches are quarantined;
- failed tests roll back mission-owned changes;
- denied authority and self-review are blocked;
- interruption resumes from the last valid transition without duplicating commits or records;
- missing countercase prevents draft creation;
- the mission cannot merge.

The complete existing test suite must remain green. Manual verification creates all repositories and state under a disposable directory and prints the final draft record.

## Acceptance Criteria

1. A declared-patch mission reaches `awaiting_human` against a temporary local bare remote.
2. A governed-worker mission reaches the same state through the same patch gate.
3. No worker has direct repository, review, push, or merge authority.
4. Every consequential transition has inspectable evidence and rollback data.
5. Negative authority, provenance, containment, test-failure, and recovery cases pass.
6. No merge API or transition exists.
7. The deterministic flow remains usable when the worker runtime is unavailable.
8. The full repository suite and documented manual verification command pass on Windows with Python 3.12.

## Manual Verification Contract

The implementation will provide one PowerShell-safe Python command that creates a temporary fixture, initializes a bare origin, executes both patch-source modes using deterministic fakes for worker mode, inspects the stored draft records, verifies the pushed branches, and removes no path outside its temporary root.

## Rollback

Revert the implementation commit, apply the migration rollback for the new tables, and delete only disposable fixture repositories created by the manual verification command. Existing mission, capability, evidence, worker, and governance tables are unchanged.

## 10th-Man Countercase

The strongest reason this design may be wrong is that a local draft-PR record can prove repository mechanics while concealing GitHub-specific failure modes such as permissions, branch protection, CI event timing, and stale remote reviews. The next slice must therefore test a real GitHub draft PR before Erasmus is considered to have completed the Phase 1 guarded PR loop.
