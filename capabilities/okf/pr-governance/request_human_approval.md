---
{"type":"Erasmus Capability","title":"Request human approval","description":"Request consequential approval from the final human authority.","tags":["capability","semantic","human-approval"],"okf_version":"0.1","contract":{"id":"request_human_approval","version":"1.0.0","purpose":"Request consequential approval from the final human authority.","classification":"semantic","goals":["obtain_human_approval"],"inputs":[{"name":"pull_request_state","schema":{"type":"object"}}],"outputs":[{"name":"approval","schema":{"type":"object"}}],"authority_required":["approval:request"],"side_effects":["notifies_human"],"provenance_requirements":["requester","approver","head_sha"],"failure_behavior":"Remain awaiting_human until explicit approval is recorded.","rollback_behavior":"Withdraw the pending approval request.","cost":{"units":"requests","budget":1},"required_evidence":["approval_state","approver","head_sha"],"allowed_implementations":["github_approval_request"],"tenth_man_triggers":["approval_is_ambiguous_or_stale"]},"implementation":{"id":"github_approval_request","version":"1.0.0","capability_id":"request_human_approval","capability_version":"1.0.0"},"relationships":[]}
---

# Rollback

Withdraw the pending approval request.
