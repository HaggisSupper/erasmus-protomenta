import io
import json
import sqlite3

from erasmus.mcp_server import ErasmusMcpServer


def test_mcp_initialize_and_tool_discovery():
    server = ErasmusMcpServer(("state",))
    assert server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["serverInfo"]["name"] == "erasmus"
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"erasmus_status", "retrieve_ieee_evidence"}


def test_mcp_status_is_read_only_and_unknown_tool_fails():
    server = ErasmusMcpServer(("state",))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "erasmus_status"}})
    assert '"read_only": true' in response["result"]["content"][0]["text"]
    error = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nope"}})
    assert error["error"]["message"] == "unknown tool: nope"


def test_mcp_ieee_retrieval_is_path_bound_and_provenance_bearing(tmp_path):
    db = tmp_path / "ieee.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE VIRTUAL TABLE documents USING fts5(source_ref UNINDEXED, content)")
        connection.execute("INSERT INTO documents(source_ref, content) VALUES (?, ?)", ("IEEE-450:p1", "battery maintenance"))
    server = ErasmusMcpServer((tmp_path,))
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "retrieve_ieee_evidence", "arguments": {"database": str(db), "table": "documents", "query": "battery"}}})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["source_kind"] == "ieee_retrieval"
    assert payload["rows"][0]["source_ref"] == "IEEE-450:p1"


def test_mcp_stdio_framing_and_notification_suppression():
    server = ErasmusMcpServer(("state",))
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "notifications/initialized"}) + "\n" + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize"}) + "\n")
    output_stream = io.StringIO()
    server.serve(input_stream, output_stream)
    lines = output_stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == 2
