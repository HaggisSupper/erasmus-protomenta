"""Headless local-runtime commands, routing, and mistral.rs lifecycle control."""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from threading import Thread
from typing import Callable, Sequence


BACKENDS = frozenset({"lmstudio", "mistralrs", "ollama", "llama_cpp"})
TAIL_LIMIT = 2048


class HeadlessConfigurationError(ValueError):
    """Invalid local runtime configuration."""


class HeadlessExecutionError(RuntimeError):
    """Typed local runtime execution failure."""

    def __init__(self, message: str, evidence: "HeadlessProcessEvidence | None" = None):
        super().__init__(message)
        self.evidence = evidence


class LifecycleState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class HeadlessProcessEvidence:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout_tail: str = ""
    stderr_tail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(_redact_arg(arg) for arg in self.argv))
        object.__setattr__(self, "stdout_tail", _tail(self.stdout_tail))
        object.__setattr__(self, "stderr_tail", _tail(self.stderr_tail))

    @property
    def redacted_argv(self) -> tuple[str, ...]:
        return self.argv


@dataclass(frozen=True, slots=True)
class HeadlessSpec:
    backend: str
    model: str
    executable: str | None = None
    priority: int = 0
    host: str = "127.0.0.1"
    port: int = 1234
    lora: tuple[str, ...] = ()
    xlora: str | None = None
    xlora_order: str | None = None
    target_non_granular_index: int | None = None
    model_format: str | None = None
    quantized_file: str | None = None

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise HeadlessConfigurationError(f"unsupported headless backend: {self.backend}")
        if not isinstance(self.model, str) or not self.model.strip():
            raise HeadlessConfigurationError("headless model must be non-empty")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise HeadlessConfigurationError("priority must be an integer")
        if not isinstance(self.host, str) or not self.host.strip():
            raise HeadlessConfigurationError("host must be non-empty")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not 1 <= self.port <= 65535:
            raise HeadlessConfigurationError("port must be between 1 and 65535")
        if any(not isinstance(adapter, str) or not adapter.strip() for adapter in self.lora):
            raise HeadlessConfigurationError("LoRA adapter paths must be non-empty strings")
        if self.xlora is not None and not self.xlora.strip():
            raise HeadlessConfigurationError("XLora adapter path must be non-empty")
        if self.lora and self.xlora:
            raise HeadlessConfigurationError("LoRA and X-LoRA cannot be combined without real CLI evidence")


@dataclass(frozen=True, slots=True)
class HeadlessResult:
    spec: HeadlessSpec
    content: str
    latency_seconds: float
    stderr: str = ""


def build_command(spec: HeadlessSpec, prompt: str) -> tuple[str, ...]:
    """Build an argv tuple; prompt content is never shell-interpolated."""
    if not isinstance(prompt, str):
        raise HeadlessConfigurationError("prompt must be text")
    executable = spec.executable or {"lmstudio": "lms", "mistralrs": "mistralrs", "ollama": "ollama", "llama_cpp": "llama-cli"}[spec.backend]
    if spec.backend == "lmstudio":
        return (executable, "chat", spec.model, "--prompt", prompt,
                "--dont-fetch-catalog", "--yes")
    if spec.backend == "ollama":
        return (executable, "run", spec.model, prompt, "--nowordwrap")
    if spec.backend == "llama_cpp":
        return (
            executable, "--model", spec.model, "--prompt", prompt,
            "--no-display-prompt", "--simple-io", "--single-turn", "--no-conversation",
        )
    command = [executable, "run", "-i", prompt, "auto", "--model-id", spec.model]
    if spec.model_format:
        command.extend(("--format", spec.model_format))
    if spec.quantized_file:
        command.extend(("--quantized-file", spec.quantized_file))
    _append_adapters(command, spec)
    return tuple(command)


def build_server_command(spec: HeadlessSpec) -> tuple[str, ...]:
    if spec.backend != "mistralrs":
        raise HeadlessConfigurationError("server lifecycle currently supports mistral.rs only")
    command = [
        spec.executable or "mistralrs", "serve",
        "--host", spec.host, "--port", str(spec.port), "--no-ui",
        "auto", "--model-id", spec.model,
    ]
    if spec.model_format:
        command.extend(("--format", spec.model_format))
    if spec.quantized_file:
        command.extend(("--quantized-file", spec.quantized_file))
    _append_adapters(command, spec)
    return tuple(command)


def run_headless(spec: HeadlessSpec, prompt: str, timeout_seconds: float) -> HeadlessResult:
    """Run one CLI prompt without a shell and return bounded output."""
    started = time.monotonic()
    command = build_command(spec, prompt)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"{spec.backend}/{spec.model} timed out") from error
    if completed.returncode != 0:
        evidence = HeadlessProcessEvidence(
            tuple("<redacted>" if arg == prompt else arg for arg in command),
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
        detail = (evidence.stderr_tail or evidence.stdout_tail).strip()
        raise HeadlessExecutionError(f"{spec.backend}/{spec.model} failed: {detail}", evidence)
    content = completed.stdout.strip()
    if not content:
        raise RuntimeError(f"{spec.backend}/{spec.model} returned empty output")
    return HeadlessResult(spec, content, time.monotonic() - started, completed.stderr.strip())


class HeadlessRouter:
    """Run candidates by deterministic priority order until one succeeds."""

    def __init__(self, runner: Callable[[HeadlessSpec, str, float], HeadlessResult] = run_headless):
        self.runner = runner

    def route(self, specs: Sequence[HeadlessSpec], prompt: str, timeout_seconds: float) -> HeadlessResult:
        if not specs:
            raise HeadlessConfigurationError("at least one headless runtime is required")
        failures: list[str] = []
        ordered = sorted(specs, key=lambda spec: (spec.priority, spec.backend, spec.model))
        deadline = time.monotonic() + timeout_seconds
        for spec in ordered:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return self.runner(spec, prompt, remaining)
            except Exception as error:  # one backend cannot poison the router
                failures.append(f"{spec.backend}/{spec.model}: {error}")
        raise HeadlessExecutionError("all headless runtimes failed: " + "; ".join(failures))


class MistralRsLifecycle:
    """Own a mistral.rs server process and unload it by terminating that process."""

    def __init__(
        self,
        spec: HeadlessSpec,
        *,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        healthcheck: Callable[[HeadlessSpec, float], bool] | None = None,
        capture_stderr: bool = False,
    ):
        if spec.backend != "mistralrs":
            raise HeadlessConfigurationError("mistral.rs lifecycle requires a mistralrs spec")
        self.spec = spec
        self._popen = popen
        self._healthcheck = healthcheck or _healthcheck
        self.capture_stderr = capture_stderr
        self._process: subprocess.Popen | None = None
        self.healthy = False
        self.state = LifecycleState.STOPPED
        self.evidence: HeadlessProcessEvidence | None = None
        self._stderr_tail = ""
        self._stderr_thread: Thread | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, timeout_seconds: float = 600.0) -> None:
        if self.running:
            raise HeadlessExecutionError("mistral.rs lifecycle is already running")
        self.state = LifecycleState.STARTING
        command = build_server_command(self.spec)
        self.evidence = HeadlessProcessEvidence(command, None)
        try:
            self._process = self._popen(command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE if self.capture_stderr else subprocess.DEVNULL,
                                        text=True)
        except OSError as error:
            self.state = LifecycleState.ERROR
            raise HeadlessExecutionError(f"mistral.rs failed to start: {error}", self.evidence) from error
        self._start_stderr_drain()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.state = LifecycleState.ERROR
                self._join_stderr_drain()
                self.evidence = HeadlessProcessEvidence(command, self._process.poll(), "", self._stderr_tail)
                raise HeadlessExecutionError(
                    f"mistral.rs exited before health check: {self.evidence.stderr_tail}",
                    self.evidence,
                )
            if self._healthcheck(self.spec, min(2.0, max(0.1, deadline - time.monotonic()))):
                self.healthy = True
                self.state = LifecycleState.RUNNING
                return
            time.sleep(0.2)
        self.stop(timeout_seconds=5)
        self.state = LifecycleState.ERROR
        raise TimeoutError("mistral.rs did not become healthy before timeout")

    def stop(self, timeout_seconds: float = 30.0) -> None:
        process = self._process
        self.healthy = False
        if process is None or process.poll() is not None:
            self.state = LifecycleState.STOPPED if self.state is not LifecycleState.ERROR else self.state
            return
        self.state = LifecycleState.STOPPING
        process.terminate()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        finally:
            self._process = None
            self._join_stderr_drain()
            self.state = LifecycleState.STOPPED

    def _start_stderr_drain(self) -> None:
        process = self._process
        if process is None or getattr(process, "stderr", None) is None:
            return

        def drain() -> None:
            while True:
                chunk = process.stderr.read(1024)
                if not chunk:
                    break
                self._stderr_tail = _tail(self._stderr_tail + chunk)

        self._stderr_thread = Thread(target=drain, daemon=True, name="erasmus-mistralrs-stderr")
        self._stderr_thread.start()

    def _join_stderr_drain(self) -> None:
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1)
            self._stderr_thread = None


def _append_adapters(command: list[str], spec: HeadlessSpec) -> None:
    if spec.lora:
        command.extend(("--lora", ";".join(spec.lora)))
    if spec.xlora:
        command.extend(("--xlora", spec.xlora))
    if spec.xlora_order:
        command.extend(("--xlora-order", spec.xlora_order))
    if spec.target_non_granular_index is not None:
        command.extend(("--tgt-non-granular-index", str(spec.target_non_granular_index)))


def _healthcheck(spec: HeadlessSpec, timeout_seconds: float) -> bool:
    request = urllib.request.Request(
        f"http://{spec.host}:{spec.port}/v1/models", method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _tail(text: str) -> str:
    return text[-TAIL_LIMIT:]


def _redact_arg(arg: str) -> str:
    if arg.startswith("literal:"):
        return "literal:<redacted>"
    return arg
