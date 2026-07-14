"""Headless multi-runtime routing and mistral.rs lifecycle coverage."""

from __future__ import annotations

import os
import time
from threading import Event, Lock

import pytest

from erasmus.headless import (
    HeadlessResult,
    HeadlessRouter,
    HeadlessSpec,
    MistralRsLifecycle,
    build_command,
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
        "--no-display-prompt", "--simple-io",
    )
    assert build_command(HeadlessSpec("mistralrs", "Qwen/Qwen3-4B"), "hello world") == (
        "mistralrs", "run", "auto", "--model-id", "Qwen/Qwen3-4B",
    )


def test_mistralrs_command_contains_lora_and_xlora_flags():
    spec = HeadlessSpec(
        "mistralrs", "base-model", lora=("adapter-a", "adapter-b"),
        xlora="xlora-model", xlora_order="order.json", target_non_granular_index=2,
    )
    assert build_command(spec, "prompt") == (
        "mistralrs", "run", "auto", "--model-id", "base-model",
        "--lora", "adapter-a;adapter-b", "--xlora", "xlora-model",
        "--xlora-order", "order.json", "--tgt-non-granular-index", "2",
    )


def test_xlora_is_rejected_for_non_mistralrs_backends():
    with pytest.raises(ValueError, match="only by the mistralrs backend"):
        HeadlessSpec("llama_cpp", "model.gguf", xlora="adapter")
    with pytest.raises(ValueError, match="only by the mistralrs backend"):
        HeadlessSpec("lmstudio", "model", xlora_order="order.json")


def test_router_runs_candidates_concurrently_and_selects_fastest_success():
    active = 0
    peak = 0
    lock = Lock()

    def runner(spec, prompt, timeout):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03 if spec.model == "fast" else 0.08)
        with lock:
            active -= 1
        return HeadlessResult(spec=spec, content=prompt, latency_seconds=0.03 if spec.model == "fast" else 0.08)

    started = time.monotonic()
    result = HeadlessRouter(runner).route(
        [HeadlessSpec("ollama", "slow"), HeadlessSpec("lmstudio", "fast")],
        "prompt", timeout_seconds=1,
    )
    assert result.spec.model == "fast"
    assert peak == 2
    assert time.monotonic() - started < 0.07


def test_router_fails_closed_when_all_candidates_fail():
    def runner(spec, prompt, timeout):
        raise RuntimeError(f"{spec.model} unavailable")

    with pytest.raises(RuntimeError, match="all headless runtimes failed"):
        HeadlessRouter(runner).route(
            [HeadlessSpec("mistralrs", "missing")], "prompt", timeout_seconds=1
        )


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
        HeadlessSpec("mistralrs", "base", lora=("adapter",), xlora="xlora"),
        popen=lambda *args, **kwargs: process,
        healthcheck=lambda spec, timeout: True,
    )
    lifecycle.start(timeout_seconds=1)
    lifecycle.stop(timeout_seconds=1)
    assert process.terminated


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


@pytest.mark.skipif(
    not all(os.environ.get(name) for name in (
        "ERASMUS_MISTRALRS_MODEL", "ERASMUS_LORA_ADAPTER", "ERASMUS_XLORA_ADAPTER",
    )),
    reason="set model and LoRA/XLora artifact paths for live mistral.rs lifecycle coverage",
)
def test_live_mistralrs_lora_xlora_load_and_unload():
    """Start with both adapter types, health-check, then unload by termination."""
    spec = HeadlessSpec(
        "mistralrs", os.environ["ERASMUS_MISTRALRS_MODEL"],
        lora=(os.environ["ERASMUS_LORA_ADAPTER"],),
        xlora=os.environ["ERASMUS_XLORA_ADAPTER"],
    )
    lifecycle = MistralRsLifecycle(spec)
    lifecycle.start(timeout_seconds=600)
    try:
        assert lifecycle.healthy
    finally:
        lifecycle.stop(timeout_seconds=30)
    assert not lifecycle.running
