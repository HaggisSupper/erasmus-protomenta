---
{"type":"Erasmus Capability","title":"Query SQLite","description":"Run a read-only query against the operational SQLite database.","tags":["capability","deterministic","sqlite"],"okf_version":"0.1","contract":{"id":"query_sqlite","version":"1.0.0","purpose":"Run a read-only query against the operational SQLite database.","classification":"deterministic","goals":["query_operational_state"],"inputs":[{"name":"query","schema":{"type":"string"}}],"outputs":[{"name":"rows","schema":{"type":"array"}}],"authority_required":["database:read"],"side_effects":[],"provenance_requirements":["database_identity","query","tool_version"],"failure_behavior":"Reject non-read-only statements and surface SQLite errors.","rollback_behavior":null,"cost":{"units":"rows","budget":1000},"required_evidence":["query","row_count"],"allowed_implementations":["sqlite_reader"],"tenth_man_triggers":["query_result_conflicts_with_other_evidence"]},"implementation":{"id":"sqlite_reader","version":"1.0.0","capability_id":"query_sqlite","capability_version":"1.0.0"},"relationships":[]}
---

# Contract

Read-only operational query capability; mutation statements fail closed.
