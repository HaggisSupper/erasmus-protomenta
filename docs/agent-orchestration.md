# Guarded Multi-Agent Orchestration

## Purpose

This protocol coordinates Copilot, Jules, Gemini, Erasmus, deterministic CI, and the Protomentat without allowing authority to emerge implicitly from model consensus.

## Roles

- **Erasmus — governor:** defines missions, validates evidence, reconciles dissent, controls reviews, and authorizes merge only when every gate passes.
- **Worker — implementer:** exactly one write-capable agent owns a branch at a time. Typical workers are Copilot or Jules.
- **Reviewer — adversary:** Gemini, Jules, Copilot, or another model may review a SHA, but review authority is read-only and advisory.
- **CI — executor of record:** deterministic tests, linters, schema checks, and build results are evidence. Model claims are not test evidence.
- **Protomentat — final authority:** resolves consequential ambiguity, contract weakening, destructive change, external publication, and irreversible action.

## Hard guardrails

1. One writer per branch.
2. No self-approval and no self-merge.
3. Every task and review is bound to an exact head SHA.
4. A changed head invalidates prior readiness decisions.
5. Missing CI, missing rollback, ambiguous authority, or conflicting evidence blocks merge.
6. Reviewer agents must not modify the implementation branch.
7. A reviewer may become an implementer only through an explicit handoff onto a separate branch.
8. Multi-agent agreement is not evidence.
9. Model-generated content cannot directly alter canonical belief, skills, training data, immutable contracts, or security policy.
10. Contract weakening, destructive migration, secret access, external publication, and irreversible actions require explicit Protomentat approval.

## Lifecycle

1. Erasmus creates a mission with scope, acceptance criteria, prohibited scope, required tests, rollback, and a 10th-Man countercase.
2. Erasmus assigns one worker and one branch.
3. The worker implements and opens a draft PR.
4. CI produces deterministic evidence.
5. One or more reviewers inspect the exact head SHA.
6. Erasmus reconciles findings into one non-duplicative review.
7. The worker patches the same branch; the new SHA invalidates prior approvals.
8. The loop repeats until all gates pass or the mission is halted.
9. Erasmus merges only when the PR is non-draft, CI is green, required evidence exists, rollback is credible, no blocking review remains, and the 10th-Man objection is answered.

## Conflict handling

- Two agents must never write concurrently to the same branch.
- Competing implementations use separate branches and separate PRs.
- Erasmus compares them against the same mission contract.
- A synthesis branch may be created only after branch ownership is explicitly reassigned.

## Retry and escalation

- Retry only when the failure is plausibly transient or the worker has new corrective instructions.
- Repeated failure on the same invariant triggers escalation rather than infinite retries.
- Three materially similar failed repair cycles require a halt and Protomentat review.
- Any evidence of authority creep, contract weakening, hidden state mutation, or provenance loss halts the loop immediately.

## Fail-closed merge gate

A PR is not mergeable unless all are true:

- exact mission and issue are linked;
- current head SHA is reviewed;
- branch has one declared writer;
- required tests and CI pass;
- acceptance criteria are demonstrated;
- contract and migration changes are explicit;
- scope limits are respected;
- rollback is documented and executable;
- no unresolved blocking review remains;
- the 10th-Man countercase is answered;
- no protected human-approval trigger is present.

## Manual-first bootstrap

Until a native runner exists, GitHub issues, branches, PRs, reviews, and CI are the control plane. Automation may coordinate these artifacts, but it must preserve the same authority and evidence boundaries.