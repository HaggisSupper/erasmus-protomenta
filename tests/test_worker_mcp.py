from pathlib import Path
from unittest.mock import patch
import subprocess
from erasmus.worker_mcp import WorkerMcpServer

def test_windows_safe_argv_and_redaction(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    process = type("P", (), {"pid": 1, "returncode": 0, "communicate": lambda self, **kwargs: ("token=abc", ""), "wait": lambda self: None})()
    with patch("erasmus.worker_mcp.shutil.which", return_value=r"C:\\Tools\\agy.cmd"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process) as popen:
        result = server.call("worker_health", {"project_root": str(tmp_path), "worker": "agy"})
    assert popen.call_args.args[0][0].endswith("agy.cmd")
    assert "REDACTED" in result["output"]

def test_timeout_kills_process_tree(tmp_path):
    server = WorkerMcpServer((tmp_path,), timeout=1)
    process = type("P", (), {"pid": 42, "communicate": lambda self, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("agy", 1)), "kill": lambda self: None, "wait": lambda self: None})()
    with patch("erasmus.worker_mcp.shutil.which", return_value="agy"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process), patch("erasmus.worker_mcp.os.killpg") as killpg:
        response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_test", "arguments": {"project_root": str(tmp_path)}}})
    assert "timed out" in response["error"]["message"]
    if __import__("os").name != "nt": killpg.assert_called_once()
