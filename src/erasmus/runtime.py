"""Stdlib OpenAI-compatible client and durable local model sessions."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlparse

from erasmus.context import BoundedContext
from erasmus.store import Store


DEFAULT_SECTION_BUDGETS = {
    "constitution": 800,
    "checkpoint": 400,
    "propositions": 700,
    "adaptations": 400,
    "evidence": 1200,
    "dialogue": 596,
}


class LocalRuntimeError(RuntimeError):
    code = "runtime_error"
    action = "inspect the local runtime configuration and logs"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self), "action": self.action}


class RuntimeConfigurationError(LocalRuntimeError):
    code = "invalid_configuration"
    action = "fix the endpoint/model configuration and retry"


class RuntimeConnectionError(LocalRuntimeError):
    code = "connection_failed"
    action = "start the local endpoint and verify its base URL"


class RuntimeTimeoutError(LocalRuntimeError):
    code = "timeout"
    action = "increase timeout_seconds or inspect local model load"


class RuntimeProtocolError(LocalRuntimeError):
    code = "malformed_response"
    action = "verify the endpoint implements the OpenAI-compatible response contract"


class RuntimeCancelledError(LocalRuntimeError):
    code = "cancelled"
    action = "retry when a completion is still desired"


@dataclass(frozen=True, slots=True)
class LocalRuntimeConfig:
    base_url: str
    model: str
    runtime_kind: str = "mistral_rs"
    timeout_seconds: float = 120.0
    context_budget: int = 4096
    section_budgets: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_SECTION_BUDGETS)
    )
    adapter: str | None = None
    supports_embeddings: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> LocalRuntimeConfig:
        if not isinstance(raw, Mapping):
            raise RuntimeConfigurationError("runtime configuration must be an object")
        allowed = {
            "version", "base_url", "model", "runtime_kind", "timeout_seconds",
            "context_budget", "section_budgets", "adapter", "supports_embeddings",
        }
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise RuntimeConfigurationError(f"unknown runtime configuration fields: {unknown}")
        if raw.get("version", "1.0.0") != "1.0.0":
            raise RuntimeConfigurationError("runtime configuration version must be 1.0.0")
        try:
            config = cls(
                base_url=raw["base_url"],
                model=raw["model"],
                runtime_kind=raw.get("runtime_kind", "mistral_rs"),
                timeout_seconds=raw.get("timeout_seconds", 120.0),
                context_budget=raw.get("context_budget", 4096),
                section_budgets=raw.get("section_budgets", DEFAULT_SECTION_BUDGETS),
                adapter=raw.get("adapter"),
                supports_embeddings=raw.get("supports_embeddings", False),
            )
        except KeyError as error:
            raise RuntimeConfigurationError(f"missing runtime field: {error.args[0]}") from error
        config.validate()
        return config

    def validate(self) -> None:
        if not isinstance(self.base_url, str):
            raise RuntimeConfigurationError("base_url must be an absolute HTTP(S) URL")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeConfigurationError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeConfigurationError("base_url cannot contain credentials, query, or fragment")
        if not isinstance(self.model, str) or not self.model.strip():
            raise RuntimeConfigurationError("model must be non-empty")
        if self.runtime_kind not in {"mistral_rs", "llama_cpp", "openai_compatible"}:
            raise RuntimeConfigurationError("invalid runtime_kind")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise RuntimeConfigurationError("timeout_seconds must be positive")
        if (
            not isinstance(self.context_budget, int)
            or isinstance(self.context_budget, bool)
            or self.context_budget <= 0
        ):
            raise RuntimeConfigurationError("context_budget must be a positive integer")
        expected = set(DEFAULT_SECTION_BUDGETS)
        if not isinstance(self.section_budgets, Mapping) or set(self.section_budgets) != expected or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.section_budgets.values()
        ):
            raise RuntimeConfigurationError(
                f"section budgets must contain non-negative integers for {sorted(expected)}"
            )
        if sum(self.section_budgets.values()) < self.context_budget:
            # ponytail: section totals may exceed the global cap; a tokenizer contract
            # replaces whitespace counting if exact model tokens become necessary.
            raise RuntimeConfigurationError("section budgets must cover context_budget")
        if self.adapter is not None and (
            not isinstance(self.adapter, str) or not self.adapter.strip()
        ):
            raise RuntimeConfigurationError("adapter must be null or non-empty")
        if not isinstance(self.supports_embeddings, bool):
            raise RuntimeConfigurationError("supports_embeddings must be boolean")

    @property
    def budgets(self) -> dict[str, int]:
        return {"total": self.context_budget, **dict(self.section_budgets)}


class OpenAICompatibleRuntime:
    def __init__(self, config: LocalRuntimeConfig):
        config.validate()
        self.config = config
        self.capabilities: dict[str, bool] = {
            "streaming": True,
            "embeddings": config.supports_embeddings,
            "adapters": config.adapter is not None,
        }

    def discover(self) -> dict[str, Any]:
        data = self._json_request("GET", "models")
        models = data.get("data")
        if not isinstance(models, list) or any(
            not isinstance(model, Mapping) or not isinstance(model.get("id"), str)
            for model in models
        ):
            raise RuntimeProtocolError("models response requires a data array of model ids")
        advertised = data.get("capabilities", {})
        if isinstance(advertised, Mapping):
            for name in ("streaming", "embeddings", "adapters"):
                if isinstance(advertised.get(name), bool):
                    self.capabilities[name] = advertised[name]
        return {
            "runtime_kind": self.config.runtime_kind,
            "models": [model["id"] for model in models],
            "capabilities": dict(self.capabilities),
        }

    def list_models(self) -> list[str]:
        return list(self.discover()["models"])

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        cancel: Event | None = None,
    ) -> Iterator[str]:
        self._check_cancel(cancel)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        if self.config.adapter is not None:
            payload["adapter"] = self.config.adapter
        response = self._open("POST", "chat/completions", payload)
        saw_done = False
        try:
            while True:
                self._check_cancel(cancel)
                raw = response.readline()
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8", errors="strict").strip()
                except UnicodeDecodeError as error:
                    raise RuntimeProtocolError("stream is not valid UTF-8") from error
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    event = json.loads(data)
                    content = event["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
                    raise RuntimeProtocolError("malformed streaming chunk") from error
                if not isinstance(content, str):
                    raise RuntimeProtocolError("stream content must be text")
                if content:
                    yield content
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeTimeoutError("local runtime stream timed out") from error
        finally:
            response.close()
        if not saw_done:
            raise RuntimeProtocolError("stream ended without [DONE]")

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.capabilities["embeddings"]:
            raise RuntimeConfigurationError("runtime does not advertise embeddings")
        data = self._json_request(
            "POST", "embeddings", {"model": self.config.model, "input": texts}
        )
        try:
            vectors = [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as error:
            raise RuntimeProtocolError("malformed embeddings response") from error
        if any(
            not isinstance(vector, list)
            or any(not isinstance(value, (int, float)) for value in vector)
            for vector in vectors
        ):
            raise RuntimeProtocolError("embedding vectors must be numeric arrays")
        return vectors

    def complete_nonstream(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if self.config.adapter is not None:
            payload["adapter"] = self.config.adapter
        data = self._json_request("POST", "chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeProtocolError("malformed completion response") from error
        if not isinstance(content, str):
            raise RuntimeProtocolError("completion content must be text")
        return content

    def _json_request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        response = self._open(method, path, payload)
        try:
            data = json.loads(response.read())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeProtocolError("response is not valid JSON") from error
        finally:
            response.close()
        if not isinstance(data, Mapping):
            raise RuntimeProtocolError("response JSON must be an object")
        return data

    def _open(
        self, method: str, path: str, payload: Mapping[str, Any] | None
    ):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/" + path.lstrip("/"),
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            return urllib.request.urlopen(request, timeout=self.config.timeout_seconds)
        except urllib.error.HTTPError as error:
            raise RuntimeConnectionError(
                f"local runtime returned HTTP {error.code} for {path}"
            ) from error
        except (urllib.error.URLError, ConnectionError) as error:
            if isinstance(getattr(error, "reason", None), (TimeoutError, socket.timeout)):
                raise RuntimeTimeoutError("local runtime request timed out") from error
            raise RuntimeConnectionError(f"cannot connect to local runtime: {error}") from error
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeTimeoutError("local runtime request timed out") from error

    @staticmethod
    def _check_cancel(cancel: Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise RuntimeCancelledError("local runtime request was cancelled")


def run_session(
    store: Store,
    runtime: OpenAICompatibleRuntime,
    context: BoundedContext,
    user_prompt: str,
    *,
    cancel: Event | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Stream one bounded session and journal identity, context, and sources."""
    identity = {
        "endpoint": runtime.config.base_url,
        "runtime_kind": runtime.config.runtime_kind,
        "model": runtime.config.model,
        "adapter": runtime.config.adapter,
    }
    previous = store.db.execute(
        """
        SELECT endpoint, runtime_kind, model, adapter
        FROM local_runtime_sessions ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    with store.db:
        cursor = store.db.execute(
            """
            INSERT INTO local_runtime_sessions(
                endpoint, runtime_kind, model, adapter, capabilities_json,
                context_json, retrieved_refs_json, status
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                identity["endpoint"], identity["runtime_kind"], identity["model"],
                identity["adapter"], _json(runtime.capabilities),
                _json(context.as_dict()), _json(list(context.retrieved_refs)),
            ),
        )
        session_id = int(cursor.lastrowid)
        prior = dict(previous) if previous is not None else None
        if prior != identity:
            store.db.execute(
                """
                INSERT INTO runtime_identity_changes(session_id, prior_json, current_json)
                VALUES(?, ?, ?)
                """,
                (session_id, _json(prior) if prior else None, _json(identity)),
            )

    chunks: list[str] = []
    try:
        for chunk in runtime.stream(context.messages(user_prompt), cancel=cancel):
            chunks.append(chunk)
            if on_chunk is not None:
                on_chunk(chunk)
        content = "".join(chunks)
        event_payload = {
            "session_id": session_id,
            "content": content,
            "identity": identity,
            "retrieved_source_refs": list(context.retrieved_refs),
            "context_tokens": context.included_tokens,
        }
        with store.db:
            event = store.db.execute(
                "INSERT INTO events(kind, payload) VALUES('model_response', ?)",
                (_json(event_payload),),
            )
            event_id = int(event.lastrowid)
            store.db.execute(
                """
                UPDATE local_runtime_sessions
                SET status = 'success', response_event_id = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (event_id, session_id),
            )
        return {
            "session_id": session_id,
            "response_event_id": event_id,
            "content": content,
            "chunks": chunks,
            "identity": identity,
            "context": context.as_dict(),
        }
    except Exception as error:
        status = "cancelled" if isinstance(error, RuntimeCancelledError) else "failure"
        details = (
            error.as_dict()
            if isinstance(error, LocalRuntimeError)
            else {
                "code": "session_error",
                "message": str(error),
                "action": "inspect the local session callback and runtime logs",
            }
        )
        with store.db:
            store.db.execute(
                """
                UPDATE local_runtime_sessions
                SET status = ?, error_json = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, _json(details), session_id),
            )
        raise


def complete(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 120,
) -> str:
    """Preserve the original non-streaming convenience API."""
    config = LocalRuntimeConfig(base_url=base_url, model=model, timeout_seconds=timeout)
    return OpenAICompatibleRuntime(config).complete_nonstream(messages)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
