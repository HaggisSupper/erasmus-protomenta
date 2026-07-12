# Agent Execution Contract

This file governs all coding agents working in this repository.

## Mission

Build a personal, persistent cognitive system for the Erasmus–Protomentat dyad. Optimize for the Protomentat and Erasmus first. Preserve clean contracts so isolated dyads may be supported later, but do not build a generic platform prematurely.

## Immutable rules

1. Preserve the constitutional requirement for checks and balances against hallucination, sycophancy, mutual reinforcement, authority creep, poisoned memory, and narrative capture.
2. Prefer deterministic rules, validators, statistics, and classical ML before semantic agents.
3. Keep these stores logically separate: observed content, RAG memory, epistemic belief, experience candidates, immune memory, and parametric adaptation.
4. Never promote external or model-generated content directly into belief, skills, or training data.
5. Immune capabilities may inspect, flag, quarantine, lower confidence, or escalate. They may not silently rewrite canonical state.
6. The Protomentat is the final authority for consequential ambiguity and irreversible actions.
7. Every capability must declare typed input/output, authority, provenance, side effects, failure behavior, rollback, and 10th-Man triggers.
8. Keep the kernel one process and one SQLite database until measurements prove a split is necessary.
9. No Docker. Windows-first operation is required.
10. No placeholders, fake implementations, TODO-only modules, or tests that merely assert `True`.

## Implementation discipline

- Inspect the repository before editing.
- Preserve public contracts unless the issue explicitly authorizes a versioned migration.
- Solve the assigned issue completely; do not invent adjacent scope.
- Prefer standard-library and small dependencies. Every new dependency must be justified in the PR.
- Keep model access behind the existing narrow runtime contract. mistral.rs is primary; llama.cpp/OpenAI-compatible endpoints are acceptable fallbacks.
- Use durable transactions for state transitions and append-only events for provenance-sensitive history.
- Treat prompts as versioned source artifacts, not strings scattered through code.
- Add migration and rollback behavior when persistent schemas change.

## Required validation

Every change must include:

- focused unit tests;
- integration tests for altered persistent or cross-module flows;
- negative tests for authority and provenance boundaries;
- a documented manual verification command;
- no regression in the existing test suite.

For immune-system work, test both underreaction and autoimmune overreaction.
For mission work, test stopping conditions, denied authority, and recovery after interruption.
For sleep/adaptation work, prove that raw conversation cannot bypass quarantine.

## Completion report

A completed PR must state:

1. What changed.
2. Which contracts were added or modified.
3. Tests run and results.
4. New dependencies and why they are necessary.
5. Known limitations.
6. 10th-Man countercase: the strongest reason the change may still be wrong.
7. Rollback procedure.

Stop when the issue acceptance criteria are satisfied. Do not expand the framework for hypothetical future needs.