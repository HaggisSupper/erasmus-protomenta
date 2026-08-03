---
name: erasmus-router
description: Select the smallest governed Erasmus workflow for a request before work begins
compatibility: OpenCode native skill tool and Erasmus repository contracts
---

# Erasmus Workflow Router

## Trigger

Use when a request spans more than one possible workflow, the correct starting discipline is unclear, or the operator invokes `/erasmus`.

## Authority boundary

The Erasmus runtime remains authoritative. Routing selects a procedure; it does not grant authority, create mission state, alter memory, or prove completion.

## Deterministic evidence

Inspect the current directory, repository status, active issue/spec/plan, `AGENTS.md`, `CONTEXT.md`, and available OpenCode skills before choosing. Do not infer that a workflow exists when discovery cannot confirm it.

## Workflow

1. Restate the requested outcome in one sentence.
2. Classify the immediate need:
   - repository integration or first use → `erasmus-setup`;
   - terminology or boundary ambiguity → `erasmus-domain-model`;
   - bounded design/specification → `erasmus-spec`;
   - approved planned implementation → `erasmus-implement`;
   - behavioral code change at a public seam → `erasmus-tdd`;
   - unexplained defect or regression → `erasmus-diagnose`;
   - external technical uncertainty → `erasmus-research`;
   - independent diff assessment → `erasmus-code-review`;
   - continuation across sessions or agents → `erasmus-handoff`.
3. Choose one primary workflow. Name supporting skills only when the primary workflow explicitly requires them.
4. State the evidence used, authority needed, expected artifact, and stop condition.
5. Load the chosen skill and follow it. Do not duplicate its procedure here.

## Output artifact

A compact routing decision containing outcome, selected skill, supporting evidence, required authority, expected artifact, and stop condition.

## Stop condition

Stop after selecting and loading one primary workflow, or stop as blocked when repository state, authority, or the requested outcome is too ambiguous to route safely.
