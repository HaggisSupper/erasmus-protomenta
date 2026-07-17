# Worker MCP boundary

The worker bridge is advisory: it never grants Erasmus authority, merges, or
writes canonical state. Worker output is untrusted evidence.

- Restrict project roots to the configured allow-list; reject traversal.
- Preserve request id, worker, root, command, exit status, timeout, and output
  as provenance. Redact secrets before display or persistence.
- Treat malformed JSON, unsupported methods, crashes, non-zero exits, timeout,
  and output-limit violations as bounded failures; never convert them to
  success or retry blindly.

Manual verification:

1. Run `python -m pytest tests/test_worker_mcp.py tests/test_worker_mcp_integration.py`.
2. Exercise initialize, tools/list, and notifications/initialized on one stream.
3. Exercise malformed JSON and an outside-root path; confirm bounded errors.
4. Stub timeout, non-zero exit, and >20,000-byte output; confirm safe results.
5. Roll back by disabling the entry point/reverting the bridge, then rerun all tests.
