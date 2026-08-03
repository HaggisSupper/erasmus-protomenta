# OpenCode Erasmus Skill Layer Specification

Status: Approved implementation direction for Issue #64

## Purpose

Add a thin, composable OpenCode interaction layer on top of the existing Erasmus runtime. The layer makes the system easier to invoke without relocating memory, mission state, authority, evidence, runtime control, or skill promotion into prompt files.

## Governing boundary

The following remain authoritative:

- `constitution/immutable-contract.md` for immutable constraints;
- `AGENTS.md` and repository-local instructions for development behavior;
- the Erasmus CLI and MCP server for typed operations;
- SQLite and append-only event stores for durable state;
- mission, ledger, immune, sleep, capability, runtime, and skill modules for domain behavior.

OpenCode agents, commands, and skills are interaction artifacts. They may select workflows, collect requirements, invoke typed operations, interpret evidence, and produce reviewable documents. They may not silently promote observations into memory, propositions into belief, candidates into skills, or model agreement into completion evidence.

## Native OpenCode mapping

Use OpenCode-native locations:

- `.opencode/agents/erasmus.md` for the primary project agent;
- `.opencode/skills/<name>/SKILL.md` for reusable model-selected disciplines;
- `.opencode/commands/<name>.md` for explicit user-invoked slash commands;
- `opencode.json` for project instructions and skill permissions;
- `CONTEXT.md` for concise shared domain language.

Do not encode user-only invocation through unsupported skill frontmatter. Explicit human entry points are commands; reusable disciplines are skills.

## Primary agent

The `erasmus` primary agent must:

- load and obey project rules and the shared context;
- use deterministic tools before semantic inference where practical;
- treat the Erasmus runtime as authoritative for persistent state;
- request approval for file edits, shell execution, external access, and subagent dispatch unless a narrower repository rule authorizes them;
- refuse silent scope expansion, memory promotion, authority inference, and unbounded retries;
- surface objective evidence, uncertainty, rollback, and the strongest countercase.

The agent must not pin a provider or model. The operator controls model selection through OpenCode configuration.

## Shared domain language

`CONTEXT.md` must define the stable meanings of at least:

- observation;
- retrieval memory;
- proposition;
- evidence;
- mission;
- capability;
- tool;
- authority;
- checkpoint;
- immune incident;
- experience candidate;
- skill artifact;
- sleep consolidation;
- 10th-Man countercase;
- authoritative state;
- interaction layer.

It must link to authoritative documents instead of duplicating them.

## Initial skill set

Each skill must contain these sections:

- `## Trigger`
- `## Authority boundary`
- `## Deterministic evidence`
- `## Workflow`
- `## Output artifact`
- `## Stop condition`

Every authority section must state that the Erasmus runtime remains authoritative.

### `erasmus-router`

Classify the request and select the smallest applicable workflow. It must not invent a workflow when an existing skill or typed command covers the request.

### `erasmus-setup`

Inspect a target repository and propose the minimum integration: issue-tracker convention, `AGENTS.md` preservation, `CONTEXT.md`, ADR location, OpenCode project config, and local verification commands. It must present proposed edits before writing and preserve existing instructions.

### `erasmus-domain-model`

Build or sharpen shared vocabulary through concrete scenarios, ambiguity tests, and ADR-worthy decisions. It must distinguish terminology changes from runtime contract changes.

### `erasmus-spec`

Turn an approved discussion into a bounded mission specification with objective, scope, exclusions, interfaces, acceptance criteria, tests, rollback, and 10th-Man countercase. It must not implement.

### `erasmus-implement`

Execute an approved specification or plan in bounded vertical slices. It must use TDD where behavior changes, stop on ambiguous authority, and finish with verification and review evidence.

### `erasmus-tdd`

Use red-green vertical slices at agreed public seams. Tests must verify externally observable behavior and avoid implementation-coupled, tautological, or bulk imagined tests.

### `erasmus-diagnose`

Use reproduce, minimize, hypothesize, instrument, isolate, repair, and regression-test. It must not propose a fix before a reproducible or explicitly bounded failure model exists.

### `erasmus-research`

Use primary sources for technical questions, record citations and dates, separate findings from inference, and save a reviewable research artifact.

### `erasmus-code-review`

Review the exact diff from a fixed base on two independent axes: repository standards and originating specification. It must report unresolved evidence, scope leakage, rollback weakness, and the strongest countercase.

### `erasmus-handoff`

Produce objective continuation state: mission, exact branch/head, completed work, evidence, unresolved blockers, next bounded action, rollback point, and uncertainty. It must not claim hidden reasoning.

## User-invoked commands

Provide commands:

- `/erasmus` — route the request through `erasmus-router`;
- `/erasmus-setup` — run the setup workflow;
- `/erasmus-spec` — create or refine a bounded specification;
- `/erasmus-implement` — execute an approved plan;
- `/erasmus-review` — run an independent review;
- `/erasmus-research` — run bounded cited research;
- `/erasmus-handoff` — write a continuation artifact;
- `/erasmus-doctor` — inspect repository rules, OpenCode discovery, Erasmus CLI/MCP availability, database integrity, and runtime health without mutating state.

Command files must name the skill they load in a deterministic sentence so references can be validated.

## Deterministic validation

Add a validator that:

- parses bounded YAML frontmatter without a new dependency;
- validates OpenCode skill names against `^[a-z0-9]+(-[a-z0-9]+)*$`;
- checks skill directory/name equality and duplicate names;
- permits only OpenCode-recognized skill frontmatter fields;
- rejects unsupported invocation-control fields rather than allowing OpenCode to ignore them silently;
- enforces required skill sections and authoritative-boundary text;
- validates command frontmatter and every named skill reference;
- validates the Erasmus agent as primary, provider-neutral, and skill-enabled;
- validates `opencode.json` as JSON and rejects embedded provider/model selection;
- returns deterministic explicit errors and a non-zero exit code.

## Installer

Provide `install/Install-ErasmusOpenCode.ps1` with actions `Install`, `Repair`, `Rollback`, and `Uninstall`.

The installer must:

- use `SupportsShouldProcess` so `-WhatIf` is native;
- resolve source and target paths explicitly;
- install agent, skill, and command files into `~/.config/opencode` by default;
- compare SHA-256 digests and skip identical files;
- back up every replaced file before mutation;
- write a machine-readable installation manifest;
- restore replaced files and delete only files created by the installation during rollback;
- avoid editing provider credentials or model configuration;
- fail without partial mutation when source validation fails.

The project `opencode.json` remains project-local and is not copied over a user's global configuration.

## Testing

Required deterministic tests:

- current repository layer validates;
- missing/malformed frontmatter fails;
- skill name mismatch fails;
- duplicate skill name fails;
- unsupported frontmatter fails;
- missing required section fails;
- missing command skill reference fails;
- provider/model pinning in the Erasmus agent or project config fails;
- installer dry-run produces no files;
- first install creates expected files and manifest;
- repeat install is idempotent;
- repair backs up changed targets;
- rollback restores prior files and removes installation-created files;
- full existing repository suite remains green.

## Documentation

Add:

- this specification;
- `docs/adr/ADR-AGENT-001-opencode-skill-layer.md`;
- an implementation plan;
- Windows runbook instructions;
- concise README usage.

## Non-goals

- copying another repository's wording, branding, or package structure;
- depending on npm, Claude Code, a hosted marketplace, or external skill runtime;
- replacing typed Erasmus modules with prompts;
- adding a new database, model router, daemon, UI, OAuth provider, Docker, Electron, training path, or autonomous promotion;
- building a generic skill marketplace.

## Rollback

Revert the additive repository commits. Run the installer with `-Action Rollback` to restore pre-existing global OpenCode files from the recorded manifest. No SQLite migration or persistent Erasmus state mutation is authorized.

## 10th-Man countercase

A disciplined-looking skill catalogue can create procedural theater and false confidence. The mitigation is a deliberately small set, deterministic discovery validation, explicit authority boundaries, typed runtime calls, objective artifacts, and deletion of any skill that does not prevent a repeated concrete failure.