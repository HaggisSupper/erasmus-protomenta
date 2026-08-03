---
name: erasmus-doctor
description: Inspect OpenCode discovery, Erasmus CLI and MCP availability, database integrity, and configured runtime health without mutation
compatibility: OpenCode native skill tool and existing Erasmus diagnostic commands
---

# Erasmus Doctor

## Trigger

Use when Erasmus or its OpenCode layer appears unavailable, misconfigured, stale, unhealthy, or inconsistent with the installed repository version.

## Authority boundary

The Erasmus runtime remains authoritative. Doctor is read-only: it may inspect and recommend repair but must not migrate, restore, delete, restart, install, or rewrite state without separate approval.

## Deterministic evidence

Inspect executable discovery and versions, repository root, OpenCode agent/command/skill paths, `opencode.json`, validator output, `erasmus status`, `erasmus integrity`, MCP initialize/tools-list responses, configured runtime validation, process/port evidence, and relevant logs with secrets redacted.

## Workflow

1. Confirm the repository and installed package versions.
2. Run `python scripts/validate_opencode_layer.py` when the repository validator exists.
3. Confirm OpenCode can discover the `erasmus` agent, expected commands, and expected skill names.
4. Run `erasmus status` and `erasmus integrity` against the explicitly selected database.
5. Initialize the read-only MCP protocol and list tools without invoking mutations.
6. Validate configured local runtime files; perform a smoke call only when the operator authorizes model execution.
7. Check stale locks, occupied ports, missing executables, process exits, and logs through deterministic platform tools.
8. Classify each component as healthy, degraded, blocked, or not configured.
9. Propose the smallest repair with impact and rollback; do not execute it in this workflow.

## Output artifact

A redacted diagnostic report containing component, version, evidence, health state, failure cause, recommended repair, and rollback.

## Stop condition

Stop when every required component has an evidence-backed health state and the next repair is clear, or stop as blocked when inspection itself requires unavailable authority or would expose secrets.
