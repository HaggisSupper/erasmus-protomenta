"""Headless local-runtime commands, routing, and mistral.rs lifecycle control."""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Callable, Sequence


BACKENDS = frozenset({"lmstudio", "mistralrs", "ollama", "llama_cpp"})


@dataclass(frozen=True, slots=True)
class HeadlessSpec:
    backend: str
    model: str
    executable: str | None = None
    priority: int = 0
    port: int = 1234
    lora: tuple[str, ...] = ()
    xlora: str | None = None
    xlora_order: str | None = None
    target_non_granular_index: int | None = None
    model_format: str | None = None
    quantized_file: str | None = None

    def __post_init__(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(f"unsupported headless backend: {self.backend}")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("headless model must be non-empty")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ValueError("priority must be an integer")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if any(not isinstance(adapter, str) or not adapter.strip() for adapter in self.lora):
            raise ValueError("LoRA adapter paths must be non-empty strings")
        if self.xlora is not None and not self.xlora.strip():
            raise ValueError("XLora adapter path must be non-empty")


@dataclass(frozen=True, slots=True)
class HeadlessResult:
    spec: HeadlessSpec
    content: str
    latency_seconds: float
    stderr: str = ""


def build_command(spec: HeadlessSpec, prompt: str) -> tuple[str, ...]:
    """Build an argv tuple; prompt content is never shell-interpolated."""
    if not isinstance(prompt, str):
        raise ValueError("prompt must be text")
    executable = spec.executable or {"lmstudio": "lms", "mistralrs": "mistralrs", "ollama": "ollama", "llama_cpp": "llama-cli"}[spec.backend]
    if spec.backend == "lmstudio":
        return (executable, "chat", spec.model, "--prompt", prompt,
                "--dont-fetch-catalog", "--yes")
    if spec.backend == "ollama":
        return (executable, "run", spec.model, prompt, "--nowordwrap")
    if spec.backend == "llama_cpp":
        return (executable, "--model", spec.model, "--prompt", prompt, "--no-display-prompt", "--simple-io")
    command = [executable, "run", "auto", "--model-id", spec.model]
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
            input=prompt if spec.backend == "mistralrs" else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"{spec.backend}/{spec.model} timed out") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{spec.backend}/{spec.model} failed: {detail}")
    content = completed.stdout.strip()
    if not content:
        raise RuntimeError(f"{spec.backend}/{spec.model} returned empty output")
    return HeadlessResult(spec, content, time.monotonic() - started, completed.stderr.strip())


class HeadlessRouter:
    """Run candidates concurrently and choose fastest successful output."""

    def __init__(self, runner: Callable[[HeadlessSpec, str, float], HeadlessResult] = run_headless):
        self.runner = runner

    def route(self, specs: Sequence[HeadlessSpec], prompt: str, timeout_seconds: float) -> HeadlessResult:
        if not specs:
            raise ValueError("at least one headless runtime is required")
        results: list[HeadlessResult] = []
        failures: list[str] = []
        pool = ThreadPoolExecutor(max_workers=len(specs), thread_name_prefix="erasmus-headless")
        futures = {pool.submit(self.runner, spec, prompt, timeout_seconds): spec for spec in specs}
        pending = set(futures)
        while pending and not results:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                spec = futures[future]
                try:
                    results.append(future.result())
                except Exception as error:  # one backend cannot poison the router
                    failures.append(f"{spec.backend}/{spec.model}: {error}")
        for future in pending:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        if not results:
            raise RuntimeError("all headless runtimes failed: " + "; ".join(sorted(failures)))
        return min(results, key=lambda result: (
            result.latency_seconds, result.spec.priority, result.spec.backend, result.spec.model
        ))


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
            raise ValueError("mistral.rs lifecycle requires a mistralrs spec")
        self.spec = spec
        self._popen = popen
        self._healthcheck = healthcheck or _healthcheck
        self.capture_stderr = capture_stderr
        self._process: subprocess.Popen | None = None
        self.healthy = False

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, timeout_seconds: float = 600.0) -> None:
        if self.running:
            raise RuntimeError("mistral.rs lifecycle is already running")
        command = [self.spec.executable or "mistralrs", "serve", "auto",
                   "--model-id", self.spec.model, "--port", str(self.spec.port), "--no-ui"]
        if self.spec.model_format:
            command.extend(("--format", self.spec.model_format))
        if self.spec.quantized_file:
            command.extend(("--quantized-file", self.spec.quantized_file))
        _append_adapters(command, self.spec)
        self._process = self._popen(command, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE if self.capture_stderr else subprocess.DEVNULL,
                                    text=True)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                detail = ""
                if self._process.stderr is not None:
                    detail = self._process.stderr.read().strip()
                raise RuntimeError(f"mistral.rs exited before health check: {detail}")
            if self._healthcheck(self.spec, min(2.0, max(0.1, deadline - time.monotonic()))):
                self.healthy = True
                return
            time.sleep(0.2)
        self.stop(timeout_seconds=5)
        raise TimeoutError("mistral.rs did not become healthy before timeout")

    def stop(self, timeout_seconds: float = 30.0) -> None:
        process = self._process
        self.healthy = False
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        finally:
            self._process = None


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
        f"http://127.0.0.1:{spec.port}/v1/models", method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
