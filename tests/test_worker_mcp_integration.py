"""Contract tests for the worker MCP boundary."""
import io
import json
import subprocess
from unittest.mock import patch

from erasmus.worker_mcp import WorkerMcpServer


def _request(name="worker_test", **arguments):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def test_json_line_framing_and_notification_suppression(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
                         + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    output = io.StringIO(); server.serve(stream, output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [message["id"] for message in messages] == [1]


def test_malformed_message_returns_jsonrpc_error(tmp_path):
    output = io.StringIO()
    WorkerMcpServer((tmp_path,)).serve(io.StringIO("not-json\n"), output)
    assert json.loads(output.getvalue())["error"]["code"] == -32700


def test_worker_crash_is_failed_and_advisory(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run", return_value=subprocess.CompletedProcess([], 7, "", "boom")):
        response = server.handle(_request(project_root=str(tmp_path), worker="agy"))
    value = json.loads(response["result"]["content"][0]["text"])
    assert value["status"] == "failed" and not value["advisory"] and value["authorization"] == "local-write" and "boom" in value["output"]


def test_worker_output_is_bounded(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "x" * 100_000, "")):
        response = server.handle(_request(project_root=str(tmp_path), worker="agy"))
    value = json.loads(response["result"]["content"][0]["text"])
    assert len(value["output"]) <= 20_000
