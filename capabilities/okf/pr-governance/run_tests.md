---
{"type":"Erasmus Capability","title":"Run tests","description":"Run the declared automated test suite.","tags":["capability","deterministic","verification"],"okf_version":"0.1","contract":{"id":"run_tests","version":"1.0.0","purpose":"Run the declared automated test suite.","classification":"deterministic","goals":["verify_tests"],"inputs":[{"name":"head_sha","schema":{"type":"string"}}],"outputs":[{"name":"test_result","schema":{"type":"object"}}],"authority_required":["process:execute"],"side_effects":[],"provenance_requirements":["head_sha","command","tool_version"],"failure_behavior":"Return a failing result and do not claim readiness.","rollback_behavior":null,"cost":{"units":"seconds","budget":600},"required_evidence":["exit_code","test_summary","head_sha"],"allowed_implementations":["pytest_runner"],"tenth_man_triggers":["tests_are_flaky_or_incomplete"]},"implementation":{"id":"pytest_runner","version":"1.0.0","capability_id":"run_tests","capability_version":"1.0.0"},"relationships":[]}
---

# Contract

Produces test evidence bound to an exact head SHA.
