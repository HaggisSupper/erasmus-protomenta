"""Minimal read-only MCP server for local Erasmus governance access."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TextIO

from erasmus.capability_runtime import query_sqlite_fts


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    database: str
    table: str
    query: str
    limit: int = 5

    @classmethod
    def from_arguments(cls, arguments: dict[str, Any]) -> "EvidenceRequest":
        database, table, query = (arguments.get(key) for key in ("database", "table", "query"))
        if not all(isinstance(value, str) and value.strip() for value in (database, table, query)):
            raise ValueError("database, table, and query are required strings")
        limit = arguments.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer from 1 to 50")
        return cls(database, table, query, limit)


class ErasmusMcpServer:
    """Serve only read-only, provenance-bearing Erasmus tools over JSON lines."""

    def __init__(self, allowed_roots: tuple[str | Path, ...]):
        self.allowed_roots = allowed_roots

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return self._error(None, "request must be an object")
        request_id = request.get("id")
        method = request.get("method")
        try:
            if method == "initialize":
                return self._result(request_id, {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "erasmus", "version": "0.2.0"},
                })
            if method == "notifications/initialized":
                return None
            if method == "tools/list":
                return self._result(request_id, {"tools": [
                    {"name": "erasmus_status", "description": "Read-only Erasmus governance status.", "inputSchema": {"type": "object", "properties": {}}},
                    {"name": "retrieve_ieee_evidence", "description": "Read licensed IEEE evidence from an allowed SQLite FTS index.", "inputSchema": {"type": "object", "required": ["database", "table", "query"], "properties": {"database": {"type": "string"}, "table": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}}},
                ]})
            if method == "tools/call":
                return self._result(request_id, self._call_tool(request.get("params", {})))
            raise ValueError(f"unsupported MCP method: {method}")
        except Exception as error:
            return self._error(request_id, str(error))

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        if name == "erasmus_status":
            return {"content": [{"type": "text", "text": json.dumps({"state": "ready", "authority": "erasmus", "read_only": True})}]}
        if name == "retrieve_ieee_evidence":
            request = EvidenceRequest.from_arguments(arguments)
            rows = query_sqlite_fts(self.allowed_roots)(asdict(request))["rows"]
            payload = {"source_kind": "ieee_retrieval", "authorized": False, "rows": rows}
            return {"content": [{"type": "text", "text": json.dumps(payload)}]}
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def _result(request_id: Any, value: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    @staticmethod
    def _error(request_id: Any, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": message}}

    def serve(self, input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as error:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"parse error: {error.msg}"}}
            else:
                response = self.handle(request)
            if response is not None:
                output_stream.write(json.dumps(response) + "\n")
                output_stream.flush()


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "state").resolve()
    ErasmusMcpServer((root,)).serve()


if __name__ == "__main__":
    main()
