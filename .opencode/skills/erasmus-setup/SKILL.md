---
name: erasmus-setup
description: Configure a repository for the Erasmus OpenCode interaction layer without overwriting local decisions
compatibility: OpenCode native skills, commands, AGENTS.md, CONTEXT.md, and ADR files
---

# Erasmus Repository Setup

## Trigger

Use once when enabling Erasmus workflows in a repository, or when the operator explicitly requests setup or repair of repository integration.

## Authority boundary

The Erasmus runtime remains authoritative. Setup configures interaction files only; it may not initialize or mutate canonical memory, belief, mission, immune, skill, or runtime state without a separately authorized typed command.

## Deterministic evidence

Inspect repository root, Git remotes, `AGENTS.md` or `CLAUDE.md`, `CONTEXT.md`, `opencode.json`, `.opencode/`, `docs/adr/`, build/test commands, issue-tracker evidence, and existing instruction files. Report what exists and what is missing before proposing edits.

## Workflow

1. Identify the repository root and whether it is a single project or a genuine multi-context repository.
2. Preserve the existing instruction source:
   - update `AGENTS.md` when it exists;
   - otherwise preserve `CLAUDE.md` if that is the established source;
   - never create a competing instruction file without operator approval.
3. Recommend the observed issue tracker: GitHub when a GitHub remote exists, local Markdown when no tracker exists, or the explicitly documented alternative.
4. Recommend one root `CONTEXT.md` and `docs/adr/` unless concrete monorepo boundaries require a context map.
5. Show the exact proposed files and edits before writing.
6. On approval, add only the missing minimum and record issue-tracker/domain conventions under `docs/agents/` when useful.
7. Run repository-specific validation plus `python scripts/validate_opencode_layer.py` when available.
8. Report unchanged files, created files, verification, rollback, and any unresolved decision.

## Output artifact

A setup report and the smallest approved set of repository-local instruction, context, ADR, OpenCode config, and verification files.

## Stop condition

Stop after the approved integration validates, or stop before writing when existing instructions conflict, the repository root is uncertain, or the operator has not approved consequential file choices.
