---
name: erasmus-diagnose
description: Diagnose defects and performance regressions through reproduction, minimization, instrumentation, and regression proof
compatibility: OpenCode native skill tool and repository-native diagnostic tools
---

# Erasmus Diagnosis

## Trigger

Use when behavior is wrong, intermittent, slow, inconsistent with evidence, or not yet explained well enough to justify a fix.

## Authority boundary

The Erasmus runtime remains authoritative. Diagnosis may observe and instrument within declared scope; it may not mutate canonical state, widen authority, or ship a speculative fix as if the cause were proven.

## Deterministic evidence

Collect the exact failing command, inputs, environment, versions, logs, timestamps, expected behavior, actual behavior, and smallest known reproduction. Distinguish observed facts from hypotheses.

## Workflow

1. Reproduce the failure or define an explicit bounded failure model when reproduction is impossible.
2. Minimize variables, inputs, and components while preserving the failure.
3. List competing hypotheses with predicted observations.
4. Instrument the cheapest discriminating evidence first.
5. Eliminate hypotheses using results; do not select by plausibility alone.
6. Identify root cause, contributing conditions, and uncertainty.
7. Load `erasmus-tdd` and write a regression at the public seam before repairing behavior.
8. Implement the smallest fix, rerun the reproduction and regression, then run the affected and full suites.
9. Record evidence, rejected hypotheses, residual risks, rollback, and recurrence detection.

## Output artifact

A diagnosis record containing reproduction, minimized case, hypotheses, instrumentation, evidence, root cause, regression test, fix verification, and residual uncertainty.

## Stop condition

Stop after the failure is explained and the regression proves the repair, or stop as blocked when required evidence cannot be obtained without new authority, destructive action, or an unbounded environment change.
