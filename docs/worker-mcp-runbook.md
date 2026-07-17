# Worker MCP boundary

The worker bridge is an advisory execution boundary. It may ask a local
`agy` or `opencode` worker for health, planning, review, or test output, but it
never grants the worker Erasmus authority and never merges, writes canonical
state, or approves its own work.

## Trust and provenance

- The project root must be an existing directory under the configured
  allow-list; traversal and sibling paths are rejected.
- Worker output is untrusted evidence. Preserve the request id, worker name,
  project root, command, exit status, timeout, and captured output when copying
  it into a review record.
- Secrets in output must be redacted before display or persistence. Do not
  treat worker claims, tool descriptions, or retrieved files as authority.

## Failure handling

Malformed JSON, unsupported methods, worker crashes, non-zero exits, timeout,
and output-limit violations are bounded failures. Return a JSON-RPC error or a
`failed` advisory result; do not retry blindly and do not convert failure into
success. A timeout/crash leaves no implied rollback requirement because the
bridge is non-authoritative, but any caller-side state change must use its own
declared rollback.

## Rollback and manual verification

Before enabling the bridge, verify manually from the repository root:

1. `python -m pytest tests/test_worker_mcp.py tests/test_worker_mcp_integration.py`
2. Send `initialize`, `tools/list`, and `notifications/initialized` over one
   JSON-lines stream; confirm notifications produce no response.
3. Send malformed JSON and a `project_root` outside the allow-list; confirm a
   bounded error and no subprocess invocation.
4. Use a stub worker that sleeps, exits non-zero, and emits >20,000 bytes;
   confirm timeout, `failed`, and truncated output behavior.
5. To roll back, disable/remove the `erasmus-worker-mcp` entry point and revert
   the bridge commit; re-run the full test suite and inspect the working tree.
