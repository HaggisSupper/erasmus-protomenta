---
{"type":"Erasmus Capability","title":"Validate JSON Schema","description":"Validate a JSON value against an explicitly supplied Draft 2020-12 schema.","tags":["capability","deterministic","validation"],"okf_version":"0.1","contract":{"id":"validate_json_schema","version":"1.0.0","purpose":"Validate a JSON value against an explicitly supplied Draft 2020-12 schema.","classification":"deterministic","goals":["validate_schema"],"inputs":[{"name":"schema","schema":{"type":"object"}},{"name":"instance","schema":{}}],"outputs":[{"name":"valid","schema":{"type":"boolean"}},{"name":"errors","schema":{"type":"array","items":{"type":"object","required":["path","message"],"properties":{"path":{"type":"string"},"message":{"type":"string"}},"additionalProperties":false}}}],"authority_required":["schema:validate"],"side_effects":[],"provenance_requirements":["caller","request_id"],"failure_behavior":"Return typed validation errors without changing the supplied value.","rollback_behavior":null,"cost":{"units":"milliseconds","budget":1000},"required_evidence":["schema","validation_result"],"allowed_implementations":["jsonschema_validator"],"tenth_man_triggers":["schema_source_is_untrusted"]},"implementation":{"id":"jsonschema_validator","version":"1.0.0","capability_id":"validate_json_schema","capability_version":"1.0.0"},"relationships":[]}
---

# Rollback

No state is changed.
