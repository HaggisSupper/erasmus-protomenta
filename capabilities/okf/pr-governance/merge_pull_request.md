---
{"type":"Erasmus Capability","title":"Merge pull request","description":"Merge only a governance-ready pull request at its validated head SHA.","tags":["capability","deterministic","github-governance"],"okf_version":"0.1","contract":{"id":"merge_pull_request","version":"1.0.0","purpose":"Merge only a governance-ready pull request at its validated head SHA.","classification":"deterministic","goals":["merge_guarded_pull_request"],"inputs":[],"outputs":[{"name":"merge_result","schema":{"type":"object"}}],"authority_required":["repository:merge"],"side_effects":["mutates_default_branch"],"provenance_requirements":["pull_request_number","head_sha","ci_result","review_result","approval"],"failure_behavior":"Fail closed on stale SHA, missing evidence, missing authority, or ambiguity.","rollback_behavior":"Revert the merge commit through a governed pull request.","cost":{"units":"merges","budget":1},"required_evidence":["ci_result","review_result","rollback_declaration","head_sha"],"allowed_implementations":["github_guarded_merge"],"tenth_man_triggers":["unresolved_countercase","scope_drift","stale_evidence"]},"implementation":{"id":"github_guarded_merge","version":"1.0.0","capability_id":"merge_pull_request","capability_version":"1.0.0"},"relationships":[{"type":"requires","to":"inspect_pull_request@1.0.0"},{"type":"requires","to":"run_tests@1.0.0"},{"type":"requires","to":"invoke_tenth_man_review@1.0.0"},{"type":"requires","to":"request_human_approval@1.0.0"},{"type":"can_rollback","to":"inspect_git_repository@1.0.0"},{"type":"authorized_by","to":"request_human_approval@1.0.0"}]}
---

# Relationships

Requires [pull-request inspection](/inspect_pull_request.md), [tests](/run_tests.md),
[10th-Man review](/invoke_tenth_man_review.md), and
[human approval](/request_human_approval.md).

# Rollback

Revert the merge commit through a governed pull request.
