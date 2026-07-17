from pathlib import Path
from unittest.mock import patch
import subprocess
from erasmus.worker_mcp import WorkerMcpServer

def test_root_allowlist_and_redaction():
    tmp_path = Path.cwd()
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "token=abc123", "")
        result = server.call("worker_health", {"project_root": str(tmp_path), "worker": "agy"})
    assert result["advisory"] and "REDACTED" in result["output"]

def test_path_traversal_rejected():
    tmp_path = Path.cwd()
    server = WorkerMcpServer((tmp_path / "src",))
    response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_plan", "arguments": {"project_root": str(tmp_path)}}})
    assert response["error"]["message"] == "project_root is outside the allowed roots"

def test_timeout_is_safe():
    tmp_path = Path.cwd()
    server = WorkerMcpServer((tmp_path,), timeout=1)
    with patch("erasmus.worker_mcp.subprocess.run", side_effect=subprocess.TimeoutExpired("agy", 1)):
        response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_test", "arguments": {"project_root": str(tmp_path)}}})
    assert "timed out" in response["error"]["message"]
