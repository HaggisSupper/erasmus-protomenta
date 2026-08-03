---
name: erasmus-implement
description: Execute an approved Erasmus specification or plan in bounded testable slices with verification and rollback evidence
compatibility: OpenCode native skill tool, repository tests, and typed Erasmus interfaces
---

# Erasmus Implementation

## Trigger

Use only when an approved issue, specification, or implementation plan defines the work and authority to modify the repository is available.

## Authority boundary

The Erasmus runtime remains authoritative. Implementation may change only the authorized repository surfaces; it may not infer additional authority, silently migrate state, promote memory or skills, or merge its own work.

## Deterministic evidence

Verify the exact branch/base, active issue, specification, plan, repository status, public interfaces, tests, and rollback point before editing. Record exact commands and results as work proceeds.

## Workflow

1. Confirm one writer owns the branch and the branch starts from the intended base.
2. Review the approved plan critically; stop on contradictions or missing authority.
3. Break work into independently reviewable vertical slices.
4. For behavioral code changes, load `erasmus-tdd` and agree the public seam before each red-green cycle.
5. Keep each slice within declared files and interfaces; do not build adjacent infrastructure.
6. Run focused verification after each slice and the complete required suite before completion.
7. Load `erasmus-code-review` against the exact fixed base before declaring readiness.
8. Produce the completion report: changes, contracts, tests, dependencies, limitations, exact head, rollback, countercase, and unresolved evidence.
9. Leave merge authority to the independent governed review path.

## Output artifact

A bounded branch and PR-ready completion report backed by exact deterministic test and diff evidence.

## Stop condition

Stop when all acceptance criteria and review gates pass, or halt immediately on ambiguous authority, repeated materially similar failure, stale base/evidence, scope leakage, or non-credible rollback.
