"""Sandboxed, advisory MCP bridge for external worker agents."""
from __future__ import annotations

import json, os, re, shutil, signal, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

_SECRET = re.compile(r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*[^\s,;]+")
OPERATIONS = {"worker_health", "worker_plan", "worker_review", "worker_test"}
@dataclass(frozen=True)
class WorkerProfile:
    """Validated command contract for one local worker executable."""
    name: str
    executable: str
    argv: tuple[str, ...]
    model: str | None = None
    prompt_delivery: str = "argv"
    timeout: int = 600
    output_limit: int = 20_000

    def __post_init__(self) -> None:
        if not self.name or not self.executable or not self.argv:
            raise ValueError("worker profile requires name, executable, and argv")
        if self.prompt_delivery not in {"argv", "stdin"}:
            raise ValueError("prompt_delivery must be argv or stdin")
        if self.timeout <= 0 or self.output_limit <= 0:
            raise ValueError("worker profile limits must be positive")
        try:
            for part in self.argv:
                part.format(root="", prompt="", model="")
        except (KeyError, ValueError) as exc:
            raise ValueError("worker profile argv contains an unknown placeholder") from exc

    def command(self, executable: str, root: Path, prompt: str, operation: str) -> tuple[list[str], str | None]:
        values = {"root": str(root), "prompt": prompt, "model": self.model or ""}
        args = [executable, *(part.format(**values) for part in self.argv)]
        if operation == "worker_health":
            args = [executable, "--help"]
        return args, None if self.prompt_delivery == "argv" else prompt


WORKER_PROFILES = {
    "agy": WorkerProfile("agy", "agy", ("--print", "--mode", "accept-edits", "--sandbox", "danger-full-access", "--project", "{root}", "{prompt}")),
    "opencode": WorkerProfile("opencode", "opencode", ("run", "--pure", "--auto", "--dir", "{root}", "{prompt}")),
    "codex-spark": WorkerProfile("codex-spark", "codex", ("exec", "--model", "{model}", "--sandbox", "danger-full-access", "-a", "never", "-C", "{root}", "{prompt}"), model="gpt-5.3-codex-spark"),
}
WORKER_PROFILES["codex"] = WORKER_PROFILES["codex-spark"]
WORKERS = set(WORKER_PROFILES)

def _redact(value: str) -> str:
    return _SECRET.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)

class WorkerMcpServer:
    def __init__(self, allowed_roots: tuple[str | Path, ...], timeout: int = 600):
        self.allowed_roots = tuple(Path(r).resolve() for r in allowed_roots)
        self.timeout = max(1, min(timeout, 600))

    def _root(self, value: Any) -> Path:
        if not isinstance(value, str) or not value.strip(): raise ValueError("project_root is required")
        root = Path(value).resolve()
        if not any(root == allowed or allowed in root.parents for allowed in self.allowed_roots): raise ValueError("project_root is outside the allowed roots")
        if not root.is_dir(): raise ValueError("project_root does not exist")
        return root

    def _run(self, operation: str, root: Path, prompt: str, command: str) -> dict[str, Any]:
        if command not in WORKERS: raise ValueError("worker must be agy, opencode, or codex-spark")
        if not isinstance(prompt, str) or not prompt.strip(): raise ValueError("prompt is required")
        profile = WORKER_PROFILES[command]
        executable = shutil.which(profile.executable)
        if not executable: raise ValueError(f"worker executable not found: {profile.executable}")
        argv, stdin = profile.command(executable, root, prompt, operation)
        kwargs = dict(cwd=root, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **kwargs)
        try:
            if stdin is None:
                stdout, stderr = process.communicate(timeout=min(self.timeout, profile.timeout))
            else:
                stdout, stderr = process.communicate(input=stdin, timeout=min(self.timeout, profile.timeout))
        except subprocess.TimeoutExpired as error:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.kill(); process.wait()
            raise ValueError(f"worker timed out after {self.timeout}s") from error
        output = _redact((stdout or "") + ("\n" + stderr if stderr else ""))
        status = "ok" if process.returncode == 0 else "failed"
        return {
            "operation": operation,
            "worker": command,
            "status": status,
            "returncode": process.returncode,
            "advisory": status != "ok",
            "authorization": "local-write" if status == "ok" else "none",
            "provenance": {
                "worker": command,
                "profile": profile.name,
                "executable": profile.executable,
                "project_root": str(root),
                "operation": operation,
            },
            "output": output[:profile.output_limit],
        }

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in OPERATIONS: raise ValueError(f"unknown tool: {name}")
        return self._run(name, self._root(arguments.get("project_root")), arguments.get("prompt", "health check"), arguments.get("worker", "agy"))

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        try:
            method = request.get("method")
            if method == "initialize": return {"jsonrpc":"2.0","id":request_id,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"erasmus-worker","version":"0.1.0"}}}
            if method == "notifications/initialized": return None
            if method == "tools/list": return {"jsonrpc":"2.0","id":request_id,"result":{"tools":[{"name":n,"description":"Sandboxed advisory worker operation.","inputSchema":{"type":"object","required":["project_root"],"properties":{"project_root":{"type":"string"},"prompt":{"type":"string"},"worker":{"enum":sorted(WORKERS)}}}} for n in sorted(OPERATIONS)]}}
            if method == "tools/call":
                params=request.get("params",{}); value=self.call(params.get("name"),params.get("arguments",{})); return {"jsonrpc":"2.0","id":request_id,"result":{"content":[{"type":"text","text":json.dumps(value)}]}}
            raise ValueError("unsupported MCP method")
        except Exception as error: return {"jsonrpc":"2.0","id":request_id,"error":{"code":-32600,"message":str(error)}}

    def serve(self, input_stream: TextIO=sys.stdin, output_stream: TextIO=sys.stdout) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
            else:
                response = self.handle(request)
            if response is not None:
                output_stream.write(json.dumps(response)+"\n")
                output_stream.flush()

def main() -> None: WorkerMcpServer((Path.cwd(),)).serve()
if __name__ == "__main__": main()
