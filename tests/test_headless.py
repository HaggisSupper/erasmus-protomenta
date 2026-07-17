"""Headless multi-runtime routing and mistral.rs lifecycle coverage."""

from __future__ import annotations

import io
import os
import subprocess

import pytest

from erasmus.headless import (
    HeadlessConfigurationError,
    HeadlessExecutionError,
    HeadlessProcessEvidence,
    HeadlessResult,
    HeadlessRouter,
    HeadlessSpec,
    LifecycleState,
    MistralRsLifecycle,
    build_command,
    build_server_command,
)


def test_builds_headless_commands_without_shell_interpolation():
    assert build_command(HeadlessSpec("lmstudio", "gemma/model"), "hello world") == (
        "lms", "chat", "gemma/model", "--prompt", "hello world",
        "--dont-fetch-catalog", "--yes",
    )
    assert build_command(HeadlessSpec("ollama", "qwen3:4b"), "hello world") == (
        "ollama", "run", "qwen3:4b", "hello world", "--nowordwrap",
    )
    assert build_command(HeadlessSpec("llama_cpp", "model.gguf"), "hello world") == (
        "llama-cli", "--model", "model.gguf", "--prompt", "hello world",
        "--no-display-prompt", "--simple-io", "--single-turn", "--no-conversation",
    )
    assert build_command(HeadlessSpec("mistralrs", "Qwen/Qwen3-4B"), "hello world") == (
        "mistralrs", "run", "-i", "hello world", "auto", "--model-id", "Qwen/Qwen3-4B",
    )


def test_mistralrs_command_contains_one_adapter_mode():
    spec = HeadlessSpec(
        "mistralrs", "base-model", xlora="xlora-model",
        xlora_order="order.json", target_non_granular_index=2,
    )
    assert build_command(spec, "prompt") == (
        "mistralrs", "run", "-i", "prompt", "auto", "--model-id", "base-model",
        "--xlora", "xlora-model",
        "--xlora-order", "order.json", "--tgt-non-granular-index", "2",
    )


def test_mistralrs_rejects_unproven_lora_xlora_combination():
    with pytest.raises(HeadlessConfigurationError, match="LoRA and X-LoRA"):
        HeadlessSpec("mistralrs", "base", lora=("adapter",), xlora="xlora")


def test_mistralrs_server_command_places_server_flags_before_subcommand():
    assert build_server_command(HeadlessSpec("mistralrs", "base", host="127.0.0.2", port=4321)) == (
        "mistralrs", "serve", "--host", "127.0.0.2", "--port", "4321",
        "--no-ui", "auto", "--model-id", "base",
    )


def test_router_uses_ordered_fallback_without_starting_losers_after_success():
    called = []

    def runner(spec, prompt, timeout):
        called.append(spec.model)
        return HeadlessResult(spec=spec, content=prompt, latency_seconds=0.03)

    result = HeadlessRouter(runner).route(
        [HeadlessSpec("ollama", "first", priority=10), HeadlessSpec("lmstudio", "second", priority=20)],
        "prompt", timeout_seconds=1,
    )
    assert result.spec.model == "first"
    assert called == ["first"]


def test_router_fails_closed_when_all_candidates_fail():
    def runner(spec, prompt, timeout):
        raise RuntimeError(f"{spec.model} unavailable")

    with pytest.raises(HeadlessExecutionError, match="all headless runtimes failed"):
        HeadlessRouter(runner).route(
            [HeadlessSpec("mistralrs", "missing")], "prompt", timeout_seconds=1
        )


def test_router_passes_the_remaining_budget_to_each_fallback(monkeypatch):
    clock = iter((100.0, 100.0, 100.4))
    budgets = []

    def runner(spec, prompt, timeout):
        budgets.append(timeout)
        if spec.model == "first":
            raise RuntimeError("unavailable")
        return HeadlessResult(spec=spec, content=prompt, latency_seconds=0.03)

    monkeypatch.setattr("erasmus.headless.time.monotonic", lambda: next(clock))
    HeadlessRouter(runner).route(
        [HeadlessSpec("ollama", "first", priority=0), HeadlessSpec("lmstudio", "second", priority=1)],
        "prompt", timeout_seconds=1,
    )
    assert budgets == [1.0, pytest.approx(0.6)]


def test_mistralrs_lifecycle_terminates_process():
    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

        def kill(self):
            self.terminated = True

    process = FakeProcess()
    lifecycle = MistralRsLifecycle(
        HeadlessSpec("mistralrs", "base", lora=("adapter",)),
        popen=lambda *args, **kwargs: process,
        healthcheck=lambda spec, timeout: True,
    )
    lifecycle.start(timeout_seconds=1)
    lifecycle.stop(timeout_seconds=1)
    assert process.terminated
    assert lifecycle.state is LifecycleState.STOPPED


def test_mistralrs_lifecycle_does_not_pipe_stderr_by_default():
    captured = {}

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout):
            return 0

    def popen(*args, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    lifecycle = MistralRsLifecycle(
        HeadlessSpec("mistralrs", "base"), popen=popen,
        healthcheck=lambda spec, timeout: True,
    )
    lifecycle.start(timeout_seconds=1)
    lifecycle.stop()
    assert captured["stderr"] is __import__("subprocess").DEVNULL


def test_mistralrs_lifecycle_drains_bounded_stderr_when_enabled():
    class NoisyProcess:
        def __init__(self):
            self.stderr = io.StringIO("x" * 3000)
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

        def kill(self):
            self.terminated = True

    lifecycle = MistralRsLifecycle(
        HeadlessSpec("mistralrs", "base"),
        popen=lambda *args, **kwargs: NoisyProcess(),
        healthcheck=lambda spec, timeout: True,
        capture_stderr=True,
    )
    lifecycle.start(timeout_seconds=1)
    lifecycle.stop()
    assert len(lifecycle._stderr_tail) <= 2048
    assert lifecycle._stderr_tail


def test_mistralrs_lifecycle_records_startup_failure_evidence():
    class FailedProcess:
        stderr = None

        def poll(self):
            return 7

    lifecycle = MistralRsLifecycle(
        HeadlessSpec("mistralrs", "base"),
        popen=lambda *args, **kwargs: FailedProcess(),
        healthcheck=lambda spec, timeout: False,
    )
    with pytest.raises(HeadlessExecutionError, match="exited before health check"):
        lifecycle.start(timeout_seconds=1)
    assert isinstance(lifecycle.evidence, HeadlessProcessEvidence)
    assert lifecycle.evidence.exit_code == 7
    assert lifecycle.state is LifecycleState.ERROR


def test_mistralrs_lifecycle_records_spawn_failure_as_error():
    def popen(*args, **kwargs):
        raise FileNotFoundError("mistralrs")

    lifecycle = MistralRsLifecycle(HeadlessSpec("mistralrs", "base"), popen=popen)
    with pytest.raises(HeadlessExecutionError, match="failed to start") as error:
        lifecycle.start(timeout_seconds=1)
    assert error.value.evidence is lifecycle.evidence
    assert lifecycle.state is LifecycleState.ERROR


def test_mistralrs_lifecycle_timeout_cleans_up_process():
    class SlowProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False

        def poll(self):
            return None if not self.terminated and not self.killed else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

        def kill(self):
            self.killed = True

    process = SlowProcess()
    lifecycle = MistralRsLifecycle(
        HeadlessSpec("mistralrs", "base"),
        popen=lambda *args, **kwargs: process,
        healthcheck=lambda spec, timeout: False,
    )
    with pytest.raises(TimeoutError, match="did not become healthy"):
        lifecycle.start(timeout_seconds=0.01)
    assert process.terminated
    assert lifecycle.state is LifecycleState.ERROR


def test_stderr_tail_is_bounded_and_redacted():
    evidence = HeadlessProcessEvidence(
        argv=("mistralrs", "--token-source", "literal:secret-token", "serve"),
        exit_code=1,
        stdout_tail="",
        stderr_tail="x" * 3000,
    )
    assert "secret-token" not in evidence.redacted_argv
    assert len(evidence.stderr_tail) <= 2048


def test_run_headless_records_unexpected_exit(monkeypatch):
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 3, "", "boom")

    monkeypatch.setattr("erasmus.headless.subprocess.run", run)
    with pytest.raises(HeadlessExecutionError) as error:
        from erasmus.headless import run_headless

        run_headless(HeadlessSpec("llama_cpp", "model.gguf"), "prompt", timeout_seconds=1)
    assert error.value.evidence.exit_code == 3
    assert error.value.evidence.stderr_tail == "boom"
    assert "prompt" not in error.value.evidence.redacted_argv


@pytest.mark.skipif(
    not all(os.environ.get(name) for name in (
        "ERASMUS_MISTRALRS_MODEL", "ERASMUS_LORA_ADAPTER",
    )),
    reason="set model and LoRA artifact paths for live mistral.rs lifecycle coverage",
)
def test_live_mistralrs_lora_load_and_process_shutdown():
    """Start with one adapter mode, health-check, then shut down the process."""
    spec = HeadlessSpec(
        "mistralrs", os.environ["ERASMUS_MISTRALRS_MODEL"],
        lora=(os.environ["ERASMUS_LORA_ADAPTER"],),
    )
    lifecycle = MistralRsLifecycle(spec)
    lifecycle.start(timeout_seconds=600)
    try:
        assert lifecycle.healthy
    finally:
        lifecycle.stop(timeout_seconds=30)
    assert not lifecycle.running
