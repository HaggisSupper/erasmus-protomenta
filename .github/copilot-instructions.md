# Copilot Coding-Agent Instructions

## Read first

Before changing code, read:

1. `AGENTS.md`
2. `constitution/immutable-contract.md`
3. `docs/architecture.md`
4. the issue assigned to you
5. every contract and test touched by that issue

## Product identity

This is not a generic assistant platform. It is the personal persistent cognitive system for the Erasmus–Protomentat dyad. It may later evolve into isolated dyadic deployments, but current implementation choices must optimize this relationship and avoid speculative platform infrastructure.

## Governing architecture

- **Erasmus gateway:** dialogue, synthesis, context assembly, mission framing.
- **Capability plane:** deterministic tools and classical ML perform bounded work.
- **AxiomPipe-style contracts:** capabilities communicate through concrete typed surfaces.
- **Landsraad governance:** authority, provenance, promotion, regression, and rollback.
- **10th-Man immune system:** deterministic-first divergence detection with sparse semantic escalation.
- **Persistence:** RAG, epistemic ledger, experience buffer, and immune memory remain distinct.
- **Sleep:** integrates events; it does not blindly summarize or fine-tune.
- **Adaptation:** inspectable skills first; LoRA only after repeated evidence and held-out evaluation.

## Decision order

When implementing any feature, ask in this order:

1. Can a schema or invariant settle it?
2. Can deterministic code settle it?
3. Can statistics or classical ML quantify it?
4. Is semantic model reasoning actually necessary?
5. Is human approval required by consequence or uncertainty?

Do not use an LLM for work that a parser, validator, SQL query, state machine, or established algorithm can perform more reliably.

## Non-negotiable boundaries

- Observed content is not automatically remembered.
- Remembered content is not automatically believed.
- Believed content is not automatically authorized for action.
- Experience is not automatically promoted to a skill.
- A skill is not automatically eligible for LoRA training.
- Agent confidence and user agreement are not evidence.
- No capability gains authority implicitly.

## Coding standards

- Python 3.12+ unless an issue explicitly introduces a native component.
- Type all public functions and persistent models.
- Use SQLite transactions and migrations for durable state.
- Keep dependencies minimal and pinned.
- Prefer small composable modules over frameworks.
- Preserve Windows paths, PowerShell launchers, and no-Docker operation.
- Use explicit error types/messages and fail safely at authority boundaries.
- Store prompts under version control.

## Required tests

Each issue must add tests that demonstrate its acceptance criteria and at least one failure path. Security/governance features require an attempted bypass test. Persistent changes require restart/recovery tests. Immune changes require a false-positive or autoimmune-regulation test.

## PR discipline

Implement one issue per PR unless the issue explicitly groups work. Include contract changes, migrations, tests, and documentation in the same PR. Do not leave placeholder modules for future agents.

The final PR body must contain a 10th-Man section explaining the strongest credible objection to the implementation and how it was mitigated or left visible.
