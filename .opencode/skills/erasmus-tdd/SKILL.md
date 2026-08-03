---
name: erasmus-tdd
description: Develop one behavior at a time through agreed public seams and red-green vertical slices
compatibility: OpenCode native skill tool and repository-native test frameworks
---

# Erasmus Test-Driven Development

## Trigger

Use for a feature or bug fix that changes externally observable behavior and has an identifiable public interface.

## Authority boundary

The Erasmus runtime remains authoritative. Tests specify authorized behavior at public seams; they do not grant new authority, canonize an imagined design, or justify unrelated refactoring.

## Deterministic evidence

Identify the originating acceptance criterion, exact public seam, current behavior, repository test command, and an independently known expected result before writing the test.

## Workflow

1. Name the public seam and obtain agreement that it is the correct observation boundary.
2. Choose one smallest vertical behavior slice.
3. Write one test that fails for the expected behavioral reason.
4. Run that exact test and record the failure.
5. Implement only enough production code to make the test pass.
6. Run the focused test, then affected tests.
7. Repeat for the next behavior learned from the previous slice.
8. After behavior is complete, refactor only while the public tests remain green.
9. Run the full required suite and inspect whether tests would fail under a plausible broken implementation.

Avoid:

- tests against private implementation details;
- tautological assertions that reproduce the implementation;
- snapshots without an independent expected source;
- all-tests-first horizontal slicing;
- mocks that bypass the actual public contract;
- changing production behavior to satisfy a mistaken test without revisiting the seam.

## Output artifact

A sequence of behavior-focused tests and minimal implementation changes, with recorded red and green commands at each agreed seam.

## Stop condition

Stop when the authorized behavior is covered at the agreed seams and all required tests pass, or stop when no trustworthy public seam or independent expected result can be established.
