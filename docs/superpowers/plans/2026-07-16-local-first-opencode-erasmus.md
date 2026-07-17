# Local-First OpenCode Erasmus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Windows-first local Erasmus installation that is launched with `opencode-erasmus`, silently starts and validates all required local state and services, restores persistent context, and remains usable without GitHub connectivity.

**Architecture:** Keep the repository as the development and release source. Build a versioned local package containing an idempotent PowerShell installer, an OpenCode persona, a typed service supervisor, SQLite-backed persistent state, retrieval/indexing, typed local tools, model-runtime control, diagnostics, and rollback. The launcher delegates to the supervisor; it does not contain service logic.

**Tech Stack:** PowerShell 7, Python 3.11+ with strict typing or Rust for the supervisor, SQLite, Polars for analytical paths, local embedding/index runtime, `mistral.rs` as primary model runtime, OpenCode custom agent integration, pytest and Windows GitHub Actions.

## Global Constraints

- Windows-first and PowerShell-first.
- No Docker.
- No Electron.
- No new OAuth or mandatory hosted-provider dependency.
- GitHub is not required during normal installed operation.
- Strongly typed public contracts; no untyped dictionary plumbing.
- Argv-safe subprocess invocation; no shell interpolation.
- One canonical typed configuration source plus separate local overrides.
- SQLite is canonical persistent storage.
- Persistent memory layers remain semantically separate.
- No silent promotion of observations into beliefs, experiences into skills, or content into authority.
- `mistral.rs` is the primary headless LLM runtime; fallbacks require explicit configuration.
- Every task requires deterministic tests, rollback, and a 10th-Man countercase.

---

### Task 1: Define the installed layout and typed configuration contract

**Files:**
- Create: `src/erasmus/config.py`
- Create: `config/erasmus.default.toml`
- Create: `tests/test_config.py`
- Modify: `pyproject.toml`

**Produces:** Immutable typed models for paths, executable identities, ports, timeouts, service dependencies, runtime selections, resource limits, logging, and resident-service policy.

- [ ] Write failing tests proving defaults load, local overrides are isolated, invalid ports and executable identities fail closed, and secrets are excluded from serialization.
- [ ] Implement immutable typed configuration models and deterministic TOML loading.
- [ ] Add schema-version validation and explicit configuration error variants.
- [ ] Run `python -m pytest tests/test_config.py -v` and require all tests to pass.
- [ ] Commit as `feat: add typed local Erasmus configuration`.

### Task 2: Build the local state store and migrations

**Files:**
- Create: `src/erasmus/storage/database.py`
- Create: `src/erasmus/storage/migrations.py`
- Create: `src/erasmus/storage/schema/0001_local_substrate.sql`
- Create: `tests/storage/test_database.py`
- Create: `tests/storage/test_migrations.py`

**Produces:** SQLite database APIs and versioned migrations for observations, retrieval records, propositions and evidence, missions and checkpoints, immune incidents, experience candidates, skills, approvals, runtime sessions, process evidence, and health history.

- [ ] Write failing migration tests for a clean database, repeat migration, interrupted migration, and upgrade preserving existing rows.
- [ ] Implement transactional migration application with schema version and integrity checks.
- [ ] Implement strongly typed repository interfaces without treating retrieval records as beliefs.
- [ ] Add backup-before-migration and restoration tests.
- [ ] Run the storage test suite and commit as `feat: add persistent Erasmus substrate`.

### Task 3: Implement the typed local service supervisor

**Files:**
- Create: `src/erasmus/supervisor/models.py`
- Create: `src/erasmus/supervisor/process.py`
- Create: `src/erasmus/supervisor/graph.py`
- Create: `src/erasmus/supervisor/supervisor.py`
- Create: `tests/supervisor/test_process.py`
- Create: `tests/supervisor/test_supervisor.py`

**Produces:** `start`, `status`, `doctor`, `stop`, and process-tree lifecycle APIs with dependency ordering, health checks, bounded retries, cancellation, stale-lock recovery, and rollback of partial startup.

- [ ] Write failing tests for healthy reuse, stale locks, occupied ports, missing executables, startup timeout, stderr-heavy processes, unexpected exit, partial-start rollback, and clean Windows process-tree shutdown.
- [ ] Implement explicit lifecycle states and typed startup, timeout, process-exit, health, cancellation, and shutdown errors.
- [ ] Implement concurrent stdout/stderr draining and bounded evidence capture with redaction.
- [ ] Implement deterministic dependency ordering and reverse-order rollback.
- [ ] Run supervisor tests on Windows and commit as `feat: add robust local service supervisor`.

### Task 4: Harden model-runtime control

**Files:**
- Modify: `src/erasmus/headless.py`
- Create: `src/erasmus/runtime/contracts.py`
- Modify: `tests/test_headless.py`
- Create: `tests/runtime/test_real_cli_contract.py`

**Produces:** Typed `mistral.rs` primary runtime control and explicitly configured fallback adapters, validated against real binary help/version output.

- [ ] Write failing tests for the known one-shot prompt, server-option ordering, single-turn fallback, invalid LoRA/X-LoRA combinations, stderr deadlock, timeout, restart, and process-versus-adapter lifecycle semantics.
- [ ] Replace generic runtime exceptions with explicit typed failures.
- [ ] Bind argv rendering to a pinned or detected real CLI contract and reject unsupported versions before launch.
- [ ] Add optional real-binary contract tests that run when approved executables are available.
- [ ] Run exact-head Windows runtime tests and commit as `fix: harden local runtime contracts`.

### Task 5: Implement retrieval and memory-boundary services

**Files:**
- Create: `src/erasmus/memory/observations.py`
- Create: `src/erasmus/memory/retrieval.py`
- Create: `src/erasmus/memory/ledger.py`
- Create: `src/erasmus/memory/immune.py`
- Create: `tests/memory/test_boundaries.py`
- Create: `tests/memory/test_restart.py`

**Produces:** Typed local APIs for ingestion, retrieval, proposition/evidence updates, immune incidents, and restart-safe checkpoint recovery.

- [ ] Write failing tests proving observations do not become propositions automatically, retrieval rank does not grant truth, and skill promotion cannot occur through ingestion.
- [ ] Implement source provenance, content digests, schema versions, and explicit promotion commands.
- [ ] Implement restart tests proving retrieval and mission state survive supervisor shutdown and startup.
- [ ] Add corruption detection and index rebuild from canonical source records.
- [ ] Run memory tests and commit as `feat: add governed local memory services`.

### Task 6: Expose typed Erasmus tools to OpenCode

**Files:**
- Create: `src/erasmus/tools/server.py`
- Create: `src/erasmus/tools/contracts.py`
- Create: `opencode/agents/erasmus.md`
- Create: `opencode/opencode.jsonc`
- Create: `tests/tools/test_contracts.py`
- Create: `tests/tools/test_opencode_smoke.py`

**Produces:** A global Erasmus persona template and typed local tool surface for mission status, retrieval, evidence, checkpoints, health, logs, and governed actions.

- [ ] Write failing tests for tool schemas, permission boundaries, unavailable-service failures, and redaction.
- [ ] Implement the smallest local protocol supported by OpenCode without introducing a hosted dependency.
- [ ] Ensure the persona references persistent tools and does not pretend the prompt itself is memory.
- [ ] Add a smoke test proving OpenCode can invoke one read-only Erasmus tool against a temporary local substrate.
- [ ] Commit as `feat: integrate Erasmus with OpenCode`.

### Task 7: Build the command-line entry points

**Files:**
- Create: `src/erasmus/cli.py`
- Modify: `pyproject.toml`
- Create: `tests/test_cli.py`

**Produces:** `erasmus start`, `status`, `doctor`, `stop`, `logs`, `upgrade`, and `rollback` commands with stable exit codes and concise output.

- [ ] Write failing CLI tests for healthy, degraded, blocked, and rollback states.
- [ ] Implement commands as thin calls into typed services.
- [ ] Define machine-readable JSON output behind an explicit flag while keeping default output operator-readable.
- [ ] Run CLI tests and commit as `feat: add Erasmus operational CLI`.

### Task 8: Create the idempotent PowerShell installer and launcher

**Files:**
- Create: `install/Install-Erasmus.ps1`
- Create: `install/Repair-Erasmus.ps1`
- Create: `install/Uninstall-Erasmus.ps1`
- Create: `install/opencode-erasmus.ps1`
- Create: `tests/install/Installer.Tests.ps1`

**Produces:** One-click installation, repair, uninstall, and the normal `opencode-erasmus` launcher.

- [ ] Write failing Pester tests for clean install, repeat install, missing dependency, partial install recovery, PATH registration, persona installation, data preservation, and uninstall.
- [ ] Implement administrative elevation only where required and keep user data under a stable per-user path.
- [ ] Install the launcher into a stable user PATH directory; the launcher must call `erasmus start`, verify readiness, and invoke `opencode --agent erasmus`.
- [ ] Record installation manifest, dependency versions, checksums, previous known-good version, and rollback command.
- [ ] Run Pester tests on Windows and commit as `feat: add one-click Erasmus installer`.

### Task 9: Implement upgrade and rollback packaging

**Files:**
- Create: `src/erasmus/release/manifest.py`
- Create: `scripts/build-release.ps1`
- Create: `tests/release/test_manifest.py`
- Create: `tests/install/UpgradeRollback.Tests.ps1`

**Produces:** A versioned Windows release package with integrity manifest, migrations, persona, configuration, tools, installer, and runbook.

- [ ] Write failing tests for checksum mismatch, failed smoke test, migration failure, and restoration of the previous package.
- [ ] Implement atomic staged installation and promotion only after smoke-test success.
- [ ] Preserve persistent user data and configuration snapshots through rollback.
- [ ] Build a local release ZIP and verify it installs offline from the package.
- [ ] Commit as `feat: add release upgrade and rollback`.

### Task 10: Prove the appliance-style end-to-end workflow

**Files:**
- Create: `tests/e2e/test_local_appliance.py`
- Create: `.github/workflows/windows-local-appliance.yml`
- Create: `docs/runbook-local-install.md`

**Produces:** Exact-head Windows evidence that the installed tool reaches a ready OpenCode Erasmus session from cold and warm starts and remains operable without GitHub.

- [ ] Provision a clean Windows test environment and install from the generated release package.
- [ ] Test cold start, warm reuse, occupied port, stale lock, process crash, index rebuild, interrupted shutdown, upgrade failure, and rollback.
- [ ] Disconnect GitHub/network access after installation and verify local status, retrieval, checkpoint restore, and typed tool calls.
- [ ] Verify no orphan processes or supporting console windows remain after shutdown.
- [ ] Publish structured test evidence and the package integrity manifest as CI artifacts.
- [ ] Commit as `test: prove local Erasmus appliance workflow`.

## Completion gate

The plan is complete only when a clean Windows machine can install the release, run `opencode-erasmus`, restore persistent Erasmus state, use typed local tools and model services, survive the defined failures, shut down cleanly, and repeat the workflow without GitHub connectivity. Unit tests or mocked subprocess tests alone cannot satisfy this gate.
