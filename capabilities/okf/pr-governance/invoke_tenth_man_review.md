---
{"type":"Erasmus Capability","title":"Invoke 10th-Man review","description":"Request an explicit strongest countercase before merge.","tags":["capability","semantic","review"],"okf_version":"0.1","contract":{"id":"invoke_tenth_man_review","version":"1.0.0","purpose":"Request an explicit strongest countercase before merge.","classification":"semantic","goals":["obtain_countercase"],"inputs":[{"name":"pull_request_state","schema":{"type":"object"}}],"outputs":[{"name":"countercase","schema":{"type":"object"}}],"authority_required":["review:request"],"side_effects":[],"provenance_requirements":["reviewer_identity","head_sha","prompt_version"],"failure_behavior":"Escalate when no independent countercase is available.","rollback_behavior":null,"cost":{"units":"reviews","budget":1},"required_evidence":["countercase","reviewer_identity","head_sha"],"allowed_implementations":["tenth_man_prompt"],"tenth_man_triggers":["always_before_merge"]},"implementation":{"id":"tenth_man_prompt","version":"1.0.0","capability_id":"invoke_tenth_man_review","capability_version":"1.0.0"},"relationships":[{"type":"may_follow","to":"inspect_pull_request@1.0.0"}]}
---

# Relationships

May follow [pull-request inspection](/inspect_pull_request.md).
