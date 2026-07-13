---
{"type":"Erasmus Capability","title":"Compile/build","description":"Compile or build the repository at an exact head SHA.","tags":["capability","deterministic","verification"],"okf_version":"0.1","contract":{"id":"compile_build","version":"1.0.0","purpose":"Compile or build the repository at an exact head SHA.","classification":"deterministic","goals":["verify_build"],"inputs":[{"name":"head_sha","schema":{"type":"string"}}],"outputs":[{"name":"build_result","schema":{"type":"object"}}],"authority_required":["process:execute"],"side_effects":["writes_build_artifacts"],"provenance_requirements":["head_sha","command","tool_version"],"failure_behavior":"Return a failing result and retain build logs.","rollback_behavior":"Delete only generated build artifacts.","cost":{"units":"seconds","budget":600},"required_evidence":["exit_code","build_log","head_sha"],"allowed_implementations":["python_builder"],"tenth_man_triggers":["build_output_is_not_reproducible"]},"implementation":{"id":"python_builder","version":"1.0.0","capability_id":"compile_build","capability_version":"1.0.0"},"relationships":[]}
---

# Rollback

Delete only generated build artifacts.
