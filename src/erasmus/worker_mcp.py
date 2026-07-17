"""Sandboxed, advisory MCP bridge for external OpenCode/agy workers."""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
_SECRET = re.compile(r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*[^\s,;]+")
OPERATIONS = {"worker_health", "worker_plan", "worker_review", "worker_test"}
WORKERS = {"agy", "opencode", "codex"}
@dataclass(frozen=True)
class WorkerProfile:
    id: str
    executable: str
    args: tuple[str, ...]
    prompt_delivery: str = "arg"
    output_limit: int = 20000
    def __post_init__(self):
        if self.prompt_delivery not in {"arg", "stdin"}: raise ValueError("prompt_delivery must be arg or stdin")
        if self.output_limit < 1: raise ValueError("output_limit must be positive")
    def command(self, executable: str, root: Path, prompt: str, operation: str) -> tuple[list[str], str | None]:
        values = {"root": str(root), "prompt": prompt, "operation": operation, "model": self.id}
        argv = [executable] + [item.format(**values) for item in self.args]
        if self.prompt_delivery == "arg" and "{prompt}" not in self.args: argv.append(prompt)
        return argv, None if self.prompt_delivery == "arg" else prompt
def _redact(value: str) -> str: return _SECRET.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
class WorkerMcpServer:
    def __init__(self, allowed_roots: tuple[str | Path, ...], timeout: int = 600):
        self.allowed_roots = tuple(Path(r).resolve() for r in allowed_roots); self.timeout = max(1, min(timeout, 600))
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
        if not executable: raise ValueError("worker executable not found: " + command)
        if command == "codex":
            argv = ["codex", "exec", "--model", "gpt-5.3-codex-spark", "--sandbox", "danger-full-access", "-a", "never", "-C", str(root), prompt]
        elif operation == "worker_health":
            argv = [command, "--help"]
        else:
            argv = ([command, "--print", "--mode", "accept-edits", "--sandbox", "danger-full-access", "--project", str(root), prompt] if command == "agy" else [command, "run", "--pure", "--auto", "--dir", str(root), prompt])
        try: result = subprocess.run(argv, cwd=root, shell=False, capture_output=True, text=True, timeout=self.timeout, env=os.environ.copy())
        except subprocess.TimeoutExpired as error: raise ValueError(f"worker timed out after {self.timeout}s") from error
        output = _redact((result.stdout or "") + ("\n" + result.stderr if result.stderr else ""))
        return {"operation": operation, "worker": command, "status": "ok" if result.returncode == 0 else "failed", "returncode": result.returncode, "advisory": False, "authorization": "local-write", "output": output[:20000]}
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
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as error:
                    response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"parse error: {error.msg}"}}
                else:
                    response = self.handle(request)
                if response is not None: output_stream.write(json.dumps(response)+"\n"); output_stream.flush()
def main() -> None: WorkerMcpServer((Path.cwd(),)).serve()
if __name__ == "__main__": main()
