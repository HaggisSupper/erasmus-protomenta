---
{"type":"Erasmus Capability","title":"Inspect Git repository","description":"Inspect immutable Git repository state.","tags":["capability","deterministic","github-governance"],"okf_version":"0.1","contract":{"id":"inspect_git_repository","version":"1.0.0","purpose":"Inspect immutable Git repository state.","classification":"deterministic","goals":["inspect_repository"],"inputs":[{"name":"repository","schema":{"type":"string"}}],"outputs":[{"name":"repository_state","schema":{"type":"object"}}],"authority_required":["repository:read"],"side_effects":[],"provenance_requirements":["repository","head_sha","tool_version"],"failure_behavior":"Fail closed when the repository or HEAD cannot be resolved.","rollback_behavior":null,"cost":{"units":"invocations","budget":1},"required_evidence":["head_sha","working_tree_status"],"allowed_implementations":["git_inspector"],"tenth_man_triggers":["repository_state_is_ambiguous"]},"implementation":{"id":"git_inspector","version":"1.0.0","capability_id":"inspect_git_repository","capability_version":"1.0.0"},"relationships":[]}
---

# Contract

Produces exact repository and working-tree evidence for downstream inspection.
