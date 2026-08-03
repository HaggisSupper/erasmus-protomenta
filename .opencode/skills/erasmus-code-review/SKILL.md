---
name: erasmus-code-review
description: Review an exact diff independently against repository standards and the originating specification
compatibility: OpenCode native skill tool, git diff, repository tests, and governance contracts
---

# Erasmus Code Review

## Trigger

Use after implementation reaches a stable exact head, before merge, or when the operator requests an independent assessment of a branch or pull request.

## Authority boundary

The Erasmus runtime remains authoritative. Review may inspect, challenge, and request repair; it may not rewrite canonical state, approve its own implementation, or treat model agreement as merge evidence.

## Deterministic evidence

Bind the review to an exact base and head SHA. Inspect changed files, originating issue/specification, tests, CI, public contracts, migrations, authority, provenance, rollback, unresolved threads, and repository instructions.

## Workflow

Run two independent passes before synthesis:

1. **Standards pass**
   - correctness and failure behavior;
   - security, authority, provenance, and secret boundaries;
   - maintainability, duplication, coupling, and contract clarity;
   - test quality and sensitivity;
   - Windows-first and no-Docker constraints.
2. **Specification pass**
   - acceptance-criteria coverage;
   - missing required tests or evidence;
   - unauthorized files, dependencies, behavior, or future scope;
   - credible rollback and migration behavior;
   - strongest unresolved 10th-Man countercase.
3. Reconcile findings by evidence and severity, not by reviewer agreement.
4. Confirm the head SHA is unchanged after review evidence was produced.
5. Report blocking findings first, then non-blocking improvements, then what was verified and what remains unproven.

## Output artifact

A SHA-bound review containing blocking findings with exact paths/evidence, standards assessment, specification assessment, test/CI status, rollback assessment, unresolved uncertainty, and merge disposition.

## Stop condition

Stop with `ready`, `repair_required`, `blocked`, `awaiting_human`, or `abandoned`. Never return `ready` while required checks are absent, the head moved, blocking findings remain, or rollback is not credible.
