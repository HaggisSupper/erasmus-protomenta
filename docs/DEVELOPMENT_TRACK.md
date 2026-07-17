# Erasmus Development Track

Status: Locked architectural direction

## Governing chain

Intent → Mission → Capability → Tool → Evidence → Review → Merge or Rollback

Everything in Erasmus must justify itself against this chain.

## Phase 1 | Core

Build only what makes bounded agent work safer, observable, verifiable, and reversible.

### Required concepts

- Mission: bounded objective, acceptance criteria, allowed scope, prohibited scope, dependencies, required tests, rollback, stop condition, and 10th-Man countercase.
- Capability: a declared action with versioned typed inputs and outputs, required authority, side effects, evidence, rollback requirements, and implementation reference.
- Tool: the exact deterministic implementation of a capability, resolved by identity, version, platform, provenance, and digest rather than ambient PATH trust.
- Agent: a governed actor with explicit role, permitted capabilities, write authority, branch ownership, retry budget, cost budget, and escalation rules.
- Skill: a minimal versioned reusable procedure that composes declared capabilities. No broad skill ontology is required in Phase 1.
- Evidence: independently inspectable records of what was read, executed, changed, tested, accepted, rejected, or rolled back. Agent assertions are not evidence.
- Policy: compact machine-readable constraints for authority, merge rules, retries, budgets, escalation, prohibited actions, and human approval triggers.

### Minimal OKF profile

Use Google Cloud Open Knowledge Format concepts as the semantic representation for the small capability graph. Model only concepts currently required by real missions. Initial relationships should remain minimal: implements, requires, produces, authorized_by, may_follow, and conflicts_with.

The first vertical slice is the guarded GitHub pull-request loop: create mission → assign worker → inspect repository → modify code → run tests → open PR → inspect diff and CI → review contracts and architecture → invoke 10th-Man → merge, request repair, or rollback.

### Deterministic-first rule

If a claim can be established by an available deterministic tool at reasonable cost, use the tool before relying on model inference. Inference interprets evidence; it does not replace obtainable evidence.

### Evidence and decision provenance

Record a structured forensic trace, not raw hidden chain-of-thought. Consequential steps should preserve objective, declared rationale, evidence consulted, exact tools and versions, action, result, alternatives where material, uncertainty, countercase, authority used, files changed, tests, rollback point, and halt or next-action reason.

Preferred live presentation: PLAN → EVIDENCE → ACTION → RESULT → COUNTERCASE → NEXT.

### User-facing observability

Provide a simple status surface showing what the system knows, plans, changes, verifies, blocks, and can reverse. A future WinTMUX-style command center may expose separate agent panes for plans, evidence, tool actions, results, disagreements, and blockers; Phase 1 requires only the data contracts and minimal status surface, not the elaborate UI.

## Local-first deployment track | Operator-ready Erasmus

The repository is where Erasmus is developed, tested, reviewed, versioned, and packaged. The deployed product runs locally on the operator's Windows machine and must not require GitHub connectivity for normal use.

The operator entry point is:

```powershell
opencode-erasmus
```

That command must invoke the OpenCode Erasmus persona and silently make the complete local substrate ready: persistent SQLite state, retrieval/indexing, typed local tools, mission and checkpoint state, immune and skill services, model-runtime control, logs, and health evidence.

Required delivery sequence:

1. Define one versioned strongly typed configuration contract and installed directory layout.
2. Implement SQLite persistence and migrations for memory, epistemic state, missions, checkpoints, immune incidents, skills, approvals, and runtime evidence.
3. Implement one robust local service supervisor with dependency ordering, health checks, stale-state recovery, bounded retries, process-tree shutdown, and rollback of partial startup.
4. Harden `mistral.rs` and fallback runtime control against the real binary contracts.
5. Expose persistent Erasmus services to OpenCode through typed local tools; the persona prompt is not memory.
6. Provide `erasmus start|status|doctor|stop|logs|upgrade|rollback` commands.
7. Provide an idempotent PowerShell installer and a thin `opencode-erasmus` launcher.
8. Produce a versioned Windows release package with integrity manifest, repair, upgrade, uninstall, and last-known-good rollback.
9. Prove the complete workflow on Windows using cold start, warm reuse, occupied ports, stale locks, runtime crashes, migration failure, interrupted shutdown, offline operation, upgrade failure, and rollback tests.

Canonical specification: [`docs/specs/local-first-opencode-erasmus.md`](specs/local-first-opencode-erasmus.md)

Implementation plan: [`docs/superpowers/plans/2026-07-16-local-first-opencode-erasmus.md`](superpowers/plans/2026-07-16-local-first-opencode-erasmus.md)

The completion gate is appliance-style behavior: a clean Windows installation can run `opencode-erasmus`, restore persistent state, use typed local tools and model services, survive defined failures, and shut down without orphan processes or supporting console windows.

This track is a packaging and operationalization boundary for the existing Erasmus architecture. It does not replace Phase 1 governance and does not authorize Phase 2 or Phase 3 scope by implication.

## Phase 2 | Operational expansion

Add only after Phase 1 is proven by real missions:

- richer agent and skill definitions;
- deeper deterministic toolchain registry;
- TOOLCHAIN.md as a human-readable projection of authoritative manifests and registry state;
- WinTMUX-style multi-agent command center;
- structured decision provenance across multiple agents;
- additional capability families driven by observed need.

TOOLCHAIN.md may use YAML front matter for document identity, bounded TOML blocks for machine-readable operational declarations, and Markdown for explanation. It must not become a competing source of truth.

## Phase 3 | Knowledge system

Add only after operational governance is stable:

- LLM Wiki concepts;
- claims, evidence, contradiction, synthesis, and open questions;
- provisional, reviewed, validated, contested, superseded, rejected, and canonical knowledge states;
- deeper OKF knowledge relationships;
- governed long-term learning and memory promotion.

Knowledge describes. Contracts constrain. Tools execute. Evidence validates. Wiki knowledge must never silently grant authority or mutate immutable contracts.

## Extension seams to preserve now

Phase 1 must remain forward-compatible through stable IDs and versions, namespaced concept/profile types, provenance on consequential records, explicit authority boundaries, extensible event and evidence schemas, migration support, generated-document separation from canonical manifests, and no hard-coded assumption that only one agent, skill, tool, or concept type can exist.

Build the seam now. Build the subsystem only when a real mission needs it.

## Explicit non-goals for Phase 1

Do not build Neo4j, RDF infrastructure, a generic knowledge graph, a semantic reasoner, a visual graph editor, a distributed agent scheduler, a universal ontology, autonomous skill evolution, an agent marketplace, the full LLM Wiki, elaborate PKI without a demonstrated requirement, or a generic plugin framework.

## Constitutional rules

1. No work without a bounded mission.
2. No action without a declared capability.
3. No deterministic claim from raw inference when a tool can establish it.
4. No tool execution without an exact known implementation.
5. No authority by implication or inheritance.
6. No consequential claim without evidence.
7. No endless retries: budget, stop, escalate.
8. No merge without required tests, review, rollback, and countercase.
9. No silent scope expansion.
10. No architecture without a concrete failure it solves.

## Privacy rule for public repositories

Public documentation must not include personal names, private biographical details, account identifiers, credentials, secrets, or other unnecessary identifying information. Use role names such as human operator, protomentat, governor, worker, reviewer, or 10th-Man unless explicit publication is required and approved.

## 10th-Man countercase

The primary risk is elegant over-formalization before Erasmus has proven repeated value. The antidote is strict sequencing: prove the guarded PR loop first; preserve extension seams; refuse broader subsystems until an observed failure or concrete mission justifies them.