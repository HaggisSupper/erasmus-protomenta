---
name: erasmus-handoff
description: Capture objective continuation state so another session or agent can resume without invented context
compatibility: OpenCode native skill tool and repository Markdown artifacts
---

# Erasmus Handoff

## Trigger

Use when work must cross sessions, agents, devices, rate limits, or a planned interruption before the mission is complete.

## Authority boundary

The Erasmus runtime remains authoritative. A handoff is an observation and navigation artifact; it is not canonical memory, approval, belief, mission completion, or hidden reasoning.

## Deterministic evidence

Inspect the exact repository status, branch, base/head SHAs, issue/spec/plan, changed paths, test results, logs, review findings, active blockers, rollback point, and uncommitted state. Do not rely on conversational recollection when repository evidence exists.

## Workflow

1. State the bounded mission and current disposition.
2. Record exact repository, branch, base, head, and dirty/untracked state.
3. List completed work with paths and objective evidence.
4. List tests and commands actually run, with results and timestamps where relevant.
5. List unresolved blockers, failed approaches, review findings, and uncertainty.
6. State the next single bounded action and the evidence required to complete it.
7. Record authority needed, prohibited scope, rollback point, and stop condition.
8. Save under the repository's handoff path or return a copyable Markdown artifact.
9. Do not include hidden chain-of-thought; preserve decisions, rationale summaries, evidence, and alternatives that matter operationally.

## Output artifact

A compact handoff containing mission, exact state, completed work, evidence, blockers, next action, authority, prohibited scope, rollback, uncertainty, and stop condition.

## Stop condition

Stop when a fresh agent can identify the exact next action without guessing, or stop as blocked when repository state cannot be inspected or differs from the claimed mission state.
