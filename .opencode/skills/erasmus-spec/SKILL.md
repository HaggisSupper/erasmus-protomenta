---
name: erasmus-spec
description: Convert an approved discussion into a bounded implementable mission specification without writing implementation code
compatibility: OpenCode native skill tool and Erasmus mission/governance contracts
---

# Erasmus Specification

## Trigger

Use when the desired outcome is sufficiently understood to formalize, but implementation has not yet been authorized or decomposed.

## Authority boundary

The Erasmus runtime remains authoritative. A specification proposes work; it does not authorize execution, mutate persistent state, or prove that the requested outcome is wise.

## Deterministic evidence

Inspect the current repository, relevant public interfaces, existing contracts, tests, ADRs, active issues, and prior decisions. Resolve contradictions against authoritative files rather than conversation summaries.

## Workflow

1. State the objective and observable user or system outcome.
2. Define current evidence, assumptions, and unresolved uncertainty.
3. Identify exact boundaries, existing interfaces, and files likely to change.
4. Specify:
   - scope and explicit non-goals;
   - typed inputs, outputs, states, errors, authority, side effects, and provenance;
   - acceptance criteria;
   - deterministic, negative, recovery, and integration tests;
   - migration and rollback where persistence changes;
   - stop condition and strongest 10th-Man countercase.
5. Decompose independent subsystems into separate missions rather than one oversized specification.
6. Present the design and obtain operator approval before publishing or handing off to implementation.
7. Save the approved artifact under the repository's documented specification path and link it to the issue tracker.

## Output artifact

A complete specification with no placeholders, ambiguous authority, hidden dependencies, or implied future scope.

## Stop condition

Stop after the operator approves the written specification, or stop earlier when repository evidence exposes an unresolved product decision or scope too broad for one bounded mission.
