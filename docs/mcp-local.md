# Local Erasmus MCP server

Start the read-only stdio server from the repository root:

```powershell
erasmus-mcp state
```

The first argument is the only filesystem root exposed to the server. The initial tool set is:

- `erasmus_status` — reports governed, read-only state.
- `retrieve_ieee_evidence` — queries an SQLite FTS table beneath the allowed root and returns source references.

The server does not execute shell commands, mutate SQLite, make approvals, or ingest training data. OKF and coding agents remain clients; Erasmus remains the governance boundary.
