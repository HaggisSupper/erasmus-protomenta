from pathlib import Path
from unittest.mock import patch
import subprocess
from erasmus.worker_mcp import WorkerMcpServer, WorkerProfile

def test_typed_profile_delivers_prompt_as_argv_and_preserves_spaced_root(tmp_path):
    root = tmp_path / "project with spaces"; root.mkdir()
    profile = WorkerProfile("fixture", "fixture", ("--project", "{root}", "{prompt}"))
    argv, stdin = profile.command(r"C:\Tools With Spaces\fixture.exe", root, "inspect this", "worker_plan")
    assert argv == [r"C:\Tools With Spaces\fixture.exe", "--project", str(root), "inspect this"]
    assert stdin is None

def test_typed_profile_delivers_prompt_on_stdin():
    profile = WorkerProfile("fixture", "fixture", ("--json",), prompt_delivery="stdin")
    argv, stdin = profile.command("fixture", Path("."), "a prompt", "worker_plan")
    assert argv == ["fixture", "--json"] and stdin == "a prompt"

def test_typed_profile_rejects_invalid_limits_and_delivery():
    import pytest
    with pytest.raises(ValueError): WorkerProfile("fixture", "fixture", ("--help",), output_limit=0)
    with pytest.raises(ValueError): WorkerProfile("fixture", "fixture", ("--help",), prompt_delivery="shell")

def test_missing_profile_executable_fails_closed(tmp_path):
    server = WorkerMcpServer((tmp_path,), require_executable=True)
    with patch("erasmus.worker_mcp.shutil.which", return_value=None):
        response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_plan", "arguments": {"project_root": str(tmp_path), "worker": "agy", "prompt": "x"}}})
    assert "worker executable not found" in response["error"]["message"]

def test_root_allowlist_and_redaction():
    tmp_path = Path.cwd()
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "token=abc123", "")
        result = server.call("worker_health", {"project_root": str(tmp_path), "worker": "agy"})
    assert not result["advisory"] and result["authorization"] == "local-write" and "REDACTED" in result["output"]

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

def test_codex_spark_command():
    tmp_path = Path.cwd()
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        server.call("worker_review", {"project_root": str(tmp_path), "worker": "codex", "prompt": "review"})
    assert run.call_args.args[0][:4] == ["codex", "exec", "--model", "gpt-5.3-codex-spark"]
