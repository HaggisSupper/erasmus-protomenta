# ADR-ROUTING-001: Adaptive Routing as a Deferred Control-Plane Extension

- **Status:** Accepted as a deferred target; implementation not authorized
- **Decision type:** Additive architecture boundary
- **Scope:** Target evolution of the Erasmus control plane; documentation-only in this decision

## Context

Erasmus currently operates as a governed one-process/one-SQLite kernel with bounded missions, typed capabilities, deterministic tools, local-runtime integration, persistent evidence, and repository governance. A broader adaptive routing architecture has now been specified, including provider-neutral resource selection, an in-memory routing knowledge graph, problem-resolution traces, lessons learned, reinforced route values, per-call adaptation, architecture neutrality, and optimization motifs.

Introducing all of these mechanisms into the current critical path would increase coupling and implementation risk.

## Decision

The adaptive routing architecture is accepted as a target evolution of the control plane. This ADR authorizes only its documentation, namespaced experimental schema seeds, and deferred roadmap. Runtime implementation remains unauthorized until a later bounded mission passes the applicable promotion gates.

Immediate repository changes are limited to:

- architecture documentation;
- an ADR;
- namespaced experimental schemas;
- a non-disruptive roadmap;
- optional future telemetry seams.

No existing runtime, bootstrap sequence, contract, or issue priority is replaced.

## Consequences

### Positive

- preserves the current implementation trajectory;
- prevents premature deep-RL or graph-infrastructure work;
- provides a stable target architecture;
- allows current telemetry and deterministic tooling to become future training evidence;
- avoids provider, model, architecture, and hardware lock-in.

### Negative

- adaptive capability arrives incrementally rather than immediately;
- some early telemetry may need later migration;
- duplicate temporary static routing logic may exist before consolidation.

## Guardrails

- new contracts are additive and versioned;
- observation-only mode precedes control authority;
- deterministic tools remain authoritative;
- feature-disabled behavior must equal current behavior;
- no external graph service in the hot path;
- no direct port is implied by analogies such as “akin to TurboQuant.”

## Current implementation compatibility

- The current Python kernel remains authoritative.
- One process and one SQLite database remain mandatory until measurements justify a versioned split.
- Existing runtime, mission, capability, tool, evidence, sleep, immune, skill, MCP and GitHub workflows are unchanged.
- Rust-first refers to preferred future native components when justified; it is not an instruction to rewrite the kernel.
- Every later phase must preserve the current deterministic route as a fallback until replacement behavior is independently validated.
