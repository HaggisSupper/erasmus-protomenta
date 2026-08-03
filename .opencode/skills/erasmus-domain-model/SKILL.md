---
name: erasmus-domain-model
description: Sharpen shared project vocabulary and record consequential domain decisions through concrete scenarios
compatibility: OpenCode native skill tool, CONTEXT.md, and repository ADR conventions
---

# Erasmus Domain Modeling

## Trigger

Use when repeated ambiguity, inconsistent naming, unclear boundaries, or overloaded terminology is slowing design, tests, or review.

## Authority boundary

The Erasmus runtime remains authoritative. A glossary or ADR can describe a boundary but cannot change a runtime contract, database schema, authority rule, or canonical belief by implication.

## Deterministic evidence

Read current `CONTEXT.md`, relevant code interfaces, schemas, tests, issues, and ADRs. Gather at least two concrete scenarios that exercise the disputed term or boundary.

## Workflow

1. Name the ambiguous terms and the concrete decision they affect.
2. Test each term against normal, boundary, and failure scenarios.
3. Reject synonyms that hide materially different states or authorities.
4. Propose the smallest vocabulary update with examples and non-examples.
5. Separate:
   - wording-only clarification;
   - implementation naming change;
   - contract or persistence change requiring a bounded mission.
6. Ask for operator approval before changing shared vocabulary or recording a consequential ADR.
7. Update `CONTEXT.md` and an ADR only after approval; update code/tests only under a separately authorized implementation workflow.
8. Verify links and terminology consistency across changed artifacts.

## Output artifact

An approved glossary diff, scenario table, and ADR when the decision is architectural or difficult to reverse.

## Stop condition

Stop when the terms distinguish all tested scenarios without changing authority implicitly, or stop as blocked when the disagreement is actually an unresolved product or contract decision.
