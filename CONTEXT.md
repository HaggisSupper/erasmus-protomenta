# Erasmus Shared Language

This document is a concise vocabulary map for humans and agents. It does not override contracts, code, migrations, or the immutable constitution.

## Terms

- **Observation:** Source material the system has seen. It is not automatically memory, evidence, or truth.
- **Retrieval memory:** Indexed material used to recover context. Retrieval relevance does not grant epistemic authority.
- **Proposition:** A versioned claim tracked by the epistemic ledger.
- **Evidence:** Provenance-bearing support, contradiction, test result, or tangible wrongness linked to a proposition or decision.
- **Mission:** A bounded objective with scope, authority, evidence, tests, rollback, stop condition, and countercase.
- **Capability:** A declared typed action with explicit authority, side effects, failure behavior, provenance, and rollback.
- **Tool:** The exact deterministic implementation of a capability, resolved by identity and version rather than ambient PATH trust.
- **Authority:** Explicit permission to inspect, propose, write, approve, execute, or merge. Authority is never inferred from confidence or agreement.
- **Checkpoint:** A durable index of the current cognitive or mission frontier with source references.
- **Immune incident:** An auditable divergence, contamination, sycophancy, authority, or provenance concern handled by bounded investigators.
- **Experience candidate:** A repeated observed behavior that may later be evaluated for promotion. It is not yet a skill.
- **Skill artifact:** A versioned inspectable behavior that passed declared promotion and held-out evaluation gates.
- **Sleep consolidation:** Recoverable classification and reconciliation of session events. It does not silently create belief or training data.
- **10th-Man countercase:** The strongest credible reason a preferred conclusion, implementation, or process may still be wrong.
- **Authoritative state:** State owned by typed Erasmus runtime modules and durable stores, not by prompts, chat summaries, or model agreement.
- **Interaction layer:** OpenCode agents, commands, and skills that select workflows and call typed interfaces without becoming authoritative state.

## Governing references

Read these when the task touches their boundary:

- `constitution/immutable-contract.md` — immutable constraints.
- `AGENTS.md` — repository execution contract.
- `docs/architecture.md` — current runtime architecture.
- `docs/DEVELOPMENT_TRACK.md` — phase and scope boundaries.
- `TOOLCHAIN.md` — governed deterministic tool implementations.
- `docs/adr/` — accepted architectural decisions.
- `contracts/` — machine-readable mission, capability, governance, immune, and routing contracts.

## Usage rule

Use these terms consistently in code, tests, issues, specifications, and handoffs. When a term is ambiguous, test it against a concrete scenario and record any consequential decision in an ADR. Do not expand this glossary merely to sound precise; add only terms that reduce repeated misunderstanding.