"""Sandboxed, advisory MCP bridge for external worker agents."""
from __future__ import annotations

import json, os, re, shutil, signal, subprocess, sys
from pathlib import Path
from typing import Any, TextIO

_SECRET = re.compile(r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*[^\s,;]+")
OPERATIONS = {"worker_health", "worker_plan", "worker_review", "worker_test"}
WORKERS = {"agy", "opencode", "codex"}

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
        if command not in WORKERS: raise ValueError("worker must be agy, opencode, or codex")
        if not isinstance(prompt, str) or not prompt.strip(): raise ValueError("prompt is required")
        executable = shutil.which(command)
        if not executable: raise ValueError(f"worker executable not found: {command}")
        if command == "codex": argv = [executable, "exec", "--model", "gpt-5.3-codex-spark", "--sandbox", "danger-full-access", "-a", "never", "-C", str(root), prompt]
        elif operation == "worker_health": argv = [executable, "--help"]
        elif command == "agy": argv = [executable, "--print", "--mode", "accept-edits", "--sandbox", "danger-full-access", "--project", str(root), prompt]
        else: argv = [executable, "run", "--pure", "--auto", "--dir", str(root), prompt]
        kwargs = dict(cwd=root, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
        if os.name == "nt": kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(argv, **kwargs)
        try: stdout, stderr = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            if os.name == "nt": subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else: os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.kill(); process.wait()
            raise ValueError(f"worker timed out after {self.timeout}s") from error
        output = _redact((stdout or "") + ("\n" + stderr if stderr else ""))
        return {"operation": operation, "worker": command, "status": "ok" if process.returncode == 0 else "failed", "returncode": process.returncode, "advisory": False, "authorization": "local-write", "output": output[:20000]}

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
            if line.strip():
                response=self.handle(json.loads(line))
                if response is not None: output_stream.write(json.dumps(response)+"\n"); output_stream.flush()

def main() -> None: WorkerMcpServer((Path.cwd(),)).serve()
if __name__ == "__main__": main()
