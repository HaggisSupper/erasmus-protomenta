# ADR-BOOTSTRAP-001: Deterministic Bootstrap Contracts Before Runtime Supervisor

- **Status:** Accepted as governing contract baseline
- **Date:** 2026-08-11
- **Decision scope:** Bootstrap control plane, issue #67
- **Related requirements:** [`ERASMUS_IMPLEMENTATION_ROADMAP.md`](../roadmap/ERASMUS_IMPLEMENTATION_ROADMAP.md#track-a-bootstrap-control-plane)

## Context

Erasmus cannot safely evolve a supervisor implementation until the bootstrap control
surface is bounded by machine-checked contracts for:

- startup dependency ordering
- readiness/health observability
- process-supervision and lifecycle transitions
- recovery and rollback outcomes
- reproducible result recording

Without these contracts, runtime behavior cannot be validated independently of model
assumptions, and recovery behavior becomes ambiguous across components.

## Decision

Adopt a contract-first bootstrap control plane with immutable schema seeds and a
single deterministic validator before any implementation of a production supervisor path.

### Enforced contract bundle

- `contracts/bootstrap/component-spec.schema.json`
- `contracts/bootstrap/bootstrap-plan.schema.json`
- `contracts/bootstrap/service-observation.schema.json`
- `contracts/bootstrap/recovery-decision.schema.json`
- `contracts/bootstrap/bootstrap-result.schema.json`

### Governance rules

1. All bootstrap artifacts must validate against these schemas.
2. Dependency order is deterministic and detected from declared `components[].dependencies`.
3. Duplicate `component_id` is rejected.
4. Recovery actions must respect ownership and authority boundaries.
5. `ordered_component_transitions` uses bounded lifecycle state transitions.
6. Runtime policy must keep mistral.rs as `primary_runtime` unless explicitly authorized otherwise.
7. Validation artifacts must be scriptable for local CI and human review.

### Consequence

Runtime implementation work remains blocked until this contract baseline remains green and
issue-referenced negative-path validation (duplicate component IDs, dependency cycles, and
ownership-bound recovery paths) is present.
