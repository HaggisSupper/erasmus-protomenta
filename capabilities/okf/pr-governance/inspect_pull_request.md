---
{"type":"Erasmus Capability","title":"Inspect pull request","description":"Inspect a pull request diff and metadata at an exact head SHA.","tags":["capability","deterministic","github-governance"],"okf_version":"0.1","contract":{"id":"inspect_pull_request","version":"1.0.0","purpose":"Inspect a pull request diff and metadata at an exact head SHA.","classification":"deterministic","goals":["inspect_pull_request"],"inputs":[{"name":"repository_state","schema":{"type":"object"}}],"outputs":[{"name":"pull_request_state","schema":{"type":"object"}}],"authority_required":["repository:read"],"side_effects":[],"provenance_requirements":["pull_request_number","head_sha","base_sha"],"failure_behavior":"Reject stale or incomplete pull request evidence.","rollback_behavior":null,"cost":{"units":"invocations","budget":1},"required_evidence":["diff","head_sha","base_sha"],"allowed_implementations":["github_pr_inspector"],"tenth_man_triggers":["diff_exceeds_mission_scope"]},"implementation":{"id":"github_pr_inspector","version":"1.0.0","capability_id":"inspect_pull_request","capability_version":"1.0.0"},"relationships":[{"type":"requires","to":"inspect_git_repository@1.0.0"}]}
---

# Relationships

Requires [Git repository inspection](/inspect_git_repository.md).
