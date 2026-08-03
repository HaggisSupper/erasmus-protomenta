---
name: erasmus-research
description: Investigate a bounded technical question using primary sources and save a cited reviewable finding
compatibility: OpenCode native skill tool with web or repository research access
---

# Erasmus Research

## Trigger

Use when implementation or design depends on an external technical fact, current interface, standard, upstream source, or unresolved empirical claim.

## Authority boundary

The Erasmus runtime remains authoritative. Research creates evidence and proposals; it does not grant authority, change runtime contracts, promote belief automatically, or substitute citations for local verification.

## Deterministic evidence

Prefer official documentation, source repositories, standards bodies, specifications, release notes, and primary papers. Record access date, version/commit, exact relevant interface, and local reproduction where practical.

## Workflow

1. State one bounded research question and the decision it informs.
2. Define source-quality and freshness requirements before searching.
3. Gather primary sources first; use secondary sources only to locate or contrast primary evidence.
4. Separate direct findings, conflicting evidence, inference, and unknowns.
5. Cross-check unstable CLI/API behavior against the pinned or installed version when the repository will execute it.
6. Capture minimal compliant excerpts and paraphrase the rest.
7. Save a dated Markdown artifact under `docs/research/` with citations, version scope, findings, counterevidence, recommendation, and unresolved questions.
8. Link the artifact from the issue/specification rather than copying its conclusions into authority-bearing contracts.

## Output artifact

A dated cited research note with a precise question, primary sources, version scope, findings, inference labels, recommendation, and unresolved evidence.

## Stop condition

Stop when the decision has enough primary evidence and uncertainty is explicit, or stop as blocked when authoritative sources conflict or the exact deployed version cannot be established.
