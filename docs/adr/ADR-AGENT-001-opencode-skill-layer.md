# ADR-AGENT-001: OpenCode Commands and Skills as a Thin Erasmus Interaction Layer

- **Status:** Accepted
- **Date:** 2026-08-03
- **Decision type:** Additive interaction architecture
- **Scope:** OpenCode integration only; no runtime or persistence migration

## Context

Erasmus already contains typed runtime behavior, durable SQLite state, mission execution, epistemic governance, cognitive immunity, sleep consolidation, local model control, and skill promotion. The missing operator surface is a small set of reusable workflows that OpenCode can discover and invoke without requiring the operator to restate engineering discipline each session.

A skill-only repository demonstrates useful principles: small composable workflows, explicit human entry points, shared domain language, TDD, disciplined diagnosis, research, review, and objective handoff. Copying that repository or treating Markdown as the Erasmus runtime would violate the existing authority and persistence boundaries.

OpenCode natively distinguishes:

- project/global agents;
- explicit slash commands;
- on-demand agent skills;
- project rule and instruction files.

## Decision

1. Use `.opencode/commands/*.md` for workflows that begin only through explicit operator invocation.
2. Use `.opencode/skills/<name>/SKILL.md` for reusable disciplines that the Erasmus agent may load when the request fits.
3. Use `.opencode/agents/erasmus.md` as a provider-neutral primary agent. Model selection remains operator configuration.
4. Use root `CONTEXT.md` for concise shared vocabulary and links, not duplicated contracts.
5. Keep every interaction artifact thin. The existing Erasmus CLI, MCP server, modules, contracts, and SQLite stores remain authoritative.
6. Validate discovery, frontmatter, references, boundaries, and provider neutrality deterministically in repository tests.
7. Provide a PowerShell installer that copies versioned interaction artifacts into the operator's global OpenCode configuration with backup and rollback.

## Consequences

### Positive

- The operator gains predictable commands and reusable workflows.
- Engineering discipline is discoverable without a monolithic system prompt.
- Persistent memory and authority remain behind typed interfaces.
- The repository can test skill discovery and references deterministically.
- Provider/model choice remains portable.

### Negative

- Markdown workflows can drift from runtime interfaces unless validation and review remain active.
- Global installation adds a file-copy lifecycle that requires backup and rollback.
- Some workflow instructions remain semantic and cannot prove their own correctness.

## Rejected alternatives

### Replace Erasmus with a skills repository

Rejected because skills do not provide durable memory, mission recovery, epistemic state, runtime supervision, or authority enforcement.

### One enormous Erasmus prompt

Rejected because it is hard to select, test, update, and reason about. It also encourages prompt text to masquerade as state.

### Unsupported user-only skill frontmatter

Rejected because OpenCode recognizes a bounded skill frontmatter schema. Human-only entry points are represented as commands instead of relying on ignored metadata.

### Pin a model in the project agent

Rejected because runtime/provider choice is operator-owned and may change independently of the interaction layer.

## Verification

- deterministic OpenCode-layer validator;
- command-to-skill reference tests;
- provider/model pin rejection;
- installer dry-run, idempotency, backup, and rollback tests;
- full Windows and Ubuntu repository CI.

## Rollback

Revert the additive files and use the installer rollback action to restore prior global OpenCode files. No persistent Erasmus database state is changed.

## 10th-Man countercase

The interaction layer may become procedural theater: agents can follow polished steps while using weak evidence or bypassing typed runtime boundaries. Keep the catalogue small, require objective artifacts and stop conditions, and remove workflows that do not prevent an observed repeated failure.