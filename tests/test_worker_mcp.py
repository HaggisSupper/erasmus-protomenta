from pathlib import Path
from unittest.mock import patch
import subprocess
import os
from erasmus.worker_mcp import WorkerMcpServer, WorkerProfile


def test_typed_profile_delivers_prompt_as_argv_and_preserves_spaced_root(tmp_path):
    root = tmp_path / "project with spaces"
    root.mkdir()
    profile = WorkerProfile("fixture", "fixture", ("--project", "{root}", "{prompt}"))
    argv, stdin = profile.command(r"C:\Tools With Spaces\fixture.exe", root, "inspect this", "worker_plan")
    assert argv == [r"C:\Tools With Spaces\fixture.exe", "--project", str(root), "inspect this"]
    assert stdin is None


def test_typed_profile_delivers_prompt_on_stdin():
    profile = WorkerProfile("fixture", "fixture", ("--json",), prompt_delivery="stdin")
    argv, stdin = profile.command("fixture", Path("."), "a prompt", "worker_plan")
    assert argv == ["fixture", "--json"]
    assert stdin == "a prompt"


def test_typed_profile_rejects_invalid_limits_and_delivery():
    with __import__("pytest").raises(ValueError):
        WorkerProfile("fixture", "fixture", ("--help",), output_limit=0)
    with __import__("pytest").raises(ValueError):
        WorkerProfile("fixture", "fixture", ("--help",), prompt_delivery="shell")
    with __import__("pytest").raises(ValueError):
        WorkerProfile("fixture", "fixture", ("{unknown}",))


def test_missing_profile_executable_fails_closed(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.shutil.which", return_value=None):
        response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_plan", "arguments": {"project_root": str(tmp_path), "worker": "agy", "prompt": "x"}}})
    assert "worker executable not found" in response["error"]["message"]

def test_windows_safe_argv_and_redaction(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    process = type("P", (), {"pid": 1, "returncode": 0, "communicate": lambda self, **kwargs: ("token=abc", ""), "wait": lambda self: None})()
    with patch("erasmus.worker_mcp.shutil.which", return_value=r"C:\\Tools\\agy.cmd"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process) as popen:
        result = server.call("worker_health", {"project_root": str(tmp_path), "worker": "agy"})
    assert popen.call_args.args[0][0].endswith("agy.cmd")
    assert "REDACTED" in result["output"]

def test_worker_result_contains_structured_provenance(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    process = type("P", (), {"pid": 1, "returncode": 0, "communicate": lambda self, **kwargs: ("ok", "")})()
    with patch("erasmus.worker_mcp.shutil.which", return_value="agy"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process):
        result = server.call("worker_plan", {"project_root": str(tmp_path), "worker": "agy", "prompt": "inspect"})
    assert result["provenance"] == {
        "worker": "agy", "profile": "agy", "executable": "agy",
        "project_root": str(tmp_path.resolve()), "operation": "worker_plan",
    }

def test_timeout_kills_process_tree(tmp_path):
    server = WorkerMcpServer((tmp_path,), timeout=1)
    process = type("P", (), {"pid": 42, "communicate": lambda self, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("agy", 1)), "kill": lambda self: None, "wait": lambda self: None})()
    if os.name == "nt":
        with patch("erasmus.worker_mcp.shutil.which", return_value="agy"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process), patch(
            "erasmus.worker_mcp.subprocess.run"
        ) as task_kill:
            response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_test", "arguments": {"project_root": str(tmp_path)}}})
            assert task_kill.called
    else:
        with patch("erasmus.worker_mcp.shutil.which", return_value="agy"), patch("erasmus.worker_mcp.subprocess.Popen", return_value=process), patch("erasmus.worker_mcp.os.killpg") as killpg:
            response = server.handle({"id": 1, "method": "tools/call", "params": {"name": "worker_test", "arguments": {"project_root": str(tmp_path)}}})
            killpg.assert_called_once()
    assert "timed out" in response["error"]["message"]
