# Local-First OpenCode Erasmus Deployment Specification

Status: Approved architectural direction

## Purpose

The repository is the development, test, review, and release source for Erasmus. The deployed product is a local-first tool installed on the operator's Windows laptop and invoked from OpenCode with one command.

Target invocation:

```powershell
opencode-erasmus
```

The command must launch OpenCode in the Erasmus persona and make the complete local Erasmus substrate available without requiring the operator to manually start databases, model servers, retrieval services, tool servers, or background processes.

## Required user experience

From a normal PowerShell terminal, the operator runs `opencode-erasmus` and receives a ready Erasmus session. Startup is silent except for one concise status line or one actionable failure. No supporting console windows remain open.

Erasmus must restore relevant local state, connect to healthy existing services where safe, start missing services in dependency order, validate them with health checks, and expose typed local tools to OpenCode.

GitHub is not required for normal operation after installation. It remains the development, audit, CI, and release surface.

## Installer and launcher

Provide one idempotent PowerShell installer that:

- checks Windows and PowerShell prerequisites;
- installs or verifies OpenCode and the approved local runtime dependencies;
- creates the global OpenCode `erasmus` persona;
- installs the `opencode-erasmus` launcher into a stable user PATH location;
- creates the local data, log, cache, configuration, model, and runtime directories;
- installs the Erasmus package and database migrations;
- validates the installation with an end-to-end smoke test;
- records installed versions and rollback information;
- can safely repair or upgrade an existing installation.

The launcher must not contain business logic. It must call a versioned Erasmus bootstrap command and then start OpenCode with the `erasmus` persona.

## Local service supervisor

Erasmus requires one strongly typed local supervisor responsible for dependency ordering and process lifecycle. It may be implemented in Rust or strongly typed Python, but it must use argv-safe subprocess invocation and explicit contracts.

The supervisor must:

- acquire a single-instance lock without leaving unrecoverable stale locks;
- load one typed configuration source;
- detect healthy existing services and reuse them;
- detect stale, dead, incompatible, or partially started services;
- start required services in declared dependency order;
- use bounded retries, exponential backoff, timeouts, and cancellation;
- continuously drain stdout and stderr where pipes are used;
- prevent orphaned processes and VRAM leaks;
- terminate the process tree cleanly on Windows;
- fail closed and roll back partial startup when a required service cannot become healthy;
- preserve structured startup, process, health, and shutdown evidence;
- expose `start`, `status`, `doctor`, `stop`, and `logs` commands.

No scattered startup scripts, shell interpolation, ambient PATH assumptions, or untyped dictionary plumbing are permitted across public boundaries.

## Required local components

The bootstrap must support these component roles through typed adapters:

1. OpenCode persona and command integration.
2. Erasmus mission, policy, capability, evidence, immune, skill, checkpoint, and approval services.
3. SQLite canonical persistence with versioned migrations.
4. Retrieval and indexing for approved local documents, conversations, notes, and repository context.
5. Local embedding runtime and persistent vector/index storage.
6. Headless model runtime control, with `mistral.rs` primary and explicitly configured fallbacks only.
7. Typed local tool interfaces used by OpenCode.
8. Structured logs, diagnostics, and forensic evidence.

A component may run in-process when isolation is unnecessary. A separate server is justified only by a concrete lifecycle, isolation, reuse, or protocol requirement.

## Persistent state separation

The implementation must preserve explicit separation between:

- observations and source material;
- retrieval chunks and indexes;
- propositions, evidence, contradictions, confidence, and supersession;
- mission state and checkpoints;
- immune incidents and known failure patterns;
- experience candidates and promoted skills;
- approvals, authority decisions, and rollback points;
- runtime sessions, process evidence, and health history.

Retrieval content is not automatically truth. Observations are not automatically beliefs. Repeated behavior is not automatically a skill. Promotion between layers requires declared rules and evidence.

## OpenCode integration

The global OpenCode `erasmus` persona must define the stable operating role and permissions. Repository `AGENTS.md` files remain project-local instructions and must not replace the persistent Erasmus substrate.

OpenCode must access Erasmus through typed local commands or tool endpoints. The persona prompt alone is insufficient and must not be treated as memory or state.

At session startup Erasmus must provide, when relevant:

- active mission and last checkpoint;
- current blockers and pending approvals;
- applicable repository rules;
- relevant retrieved context;
- known immune incidents and countercases;
- available capabilities and tool health.

At session end, Erasmus must persist objective session evidence and checkpoint state. Consolidation or promotion must be bounded, inspectable, and must not silently mutate canonical beliefs, skills, or authority.

## Configuration

Use one versioned, strongly typed local configuration contract for:

- installation and data paths;
- executable identities and pinned versions;
- ports and endpoint addresses;
- model and embedding selections;
- resource limits and timeouts;
- service dependency graph;
- resident-versus-session service policy;
- log retention and redaction;
- enabled capabilities and permissions.

Secrets must not be committed to the repository or written to normal logs. Local configuration overrides must be separated from versioned defaults.

## Reliability requirements

The system must tolerate and deterministically report:

- already-running healthy services;
- occupied ports;
- stale PID or lock files;
- missing or incompatible executables;
- failed database migrations;
- corrupt or unavailable indexes;
- model runtime startup failure;
- stderr-heavy processes;
- startup timeout and cancellation;
- unexpected process exit;
- interrupted shutdown;
- partial installation or upgrade.

A failure must leave the previous known-good installation and persistent data recoverable.

## Commands

The installed tool must provide at least:

```powershell
opencode-erasmus

erasmus status
erasmus doctor
erasmus start
erasmus stop
erasmus logs
erasmus upgrade
erasmus rollback
```

`opencode-erasmus` is the normal entry point. The other commands are diagnostic and operational controls.

## Packaging and release

The repository must produce a versioned Windows-first release package containing:

- the Erasmus application;
- PowerShell installer, repair, upgrade, and uninstall entry points;
- OpenCode persona template;
- default typed configuration;
- database migrations;
- required local tool definitions;
- integrity manifest and version metadata;
- operator runbook.

Large model files are not bundled unless a release explicitly declares them. The installer may discover or install approved dependencies through deterministic, version-aware methods and must verify the result.

## Verification gates

A release is not usable until automated tests prove:

- clean installation on a representative Windows environment;
- repeat installation is idempotent;
- `opencode-erasmus` reaches a ready session from a cold start;
- a warm start reuses healthy services;
- partial startup is rolled back;
- stale locks and dead processes recover safely;
- SQLite migrations preserve existing data;
- retrieval state survives restart;
- stdout and stderr cannot deadlock startup;
- process trees shut down without orphans;
- OpenCode can call typed Erasmus tools;
- the system operates without GitHub connectivity after installation;
- upgrade and rollback preserve the previous known-good state.

Windows exact-head CI is mandatory. Ubuntu CI may validate platform-independent modules but does not substitute for Windows lifecycle evidence.

## Scope limits

This specification does not authorize:

- Docker;
- Electron;
- cloud-first runtime state;
- mandatory GitHub connectivity during normal use;
- new OAuth or hosted provider dependencies;
- automatic model or adapter training;
- silent memory, belief, or skill promotion;
- a distributed service mesh;
- multiple competing configuration sources;
- a decorative UI before the command-line installation path is reliable.

## Rollback

Every installation or upgrade must preserve the previous executable package, configuration snapshot, schema version, and integrity manifest until the new version passes its smoke test. On failure, the installer must restore the last known-good package without deleting persistent user data.

## 10th-Man countercase

A polished launcher can conceal a brittle pile of loosely coupled scripts. Passing unit tests around mocks can also validate an invented environment rather than a real Windows machine. Acceptance therefore depends on destructive and recovery-oriented end-to-end tests using real processes, occupied ports, stale locks, migration failures, runtime crashes, and offline operation.