"""Deterministic execution for approved capability contracts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from erasmus.store import Store


_CONTRACT_SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "capabilities"
    / "contracts"
    / "capability.schema.json"
)
_LIFECYCLES = frozenset(
    {
        "proposed",
        "implemented",
        "isolated_test",
        "adversarial_review",
        "approved",
        "active",
        "suspended",
        "retired",
    }
)
_TRANSITIONS = {
    "proposed": frozenset({"implemented"}),
    "implemented": frozenset({"isolated_test"}),
    "isolated_test": frozenset({"adversarial_review"}),
    "adversarial_review": frozenset({"approved"}),
    "approved": frozenset({"active"}),
    "active": frozenset({"suspended", "retired"}),
    "suspended": frozenset({"active", "retired"}),
    "retired": frozenset(),
}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CapabilityRuntimeError(RuntimeError):
    """Raised for invalid runtime configuration or lifecycle operations."""


class _InvocationError(Exception):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True)
class CapabilityContract:
    """A versioned contract already admitted to the capability graph."""

    raw: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> CapabilityContract:
        schema = json.loads(_CONTRACT_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(
            {
                "$schema": schema["$schema"],
                "$defs": schema["$defs"],
                "$ref": "#/$defs/capability",
            }
        )
        errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.path))
        if errors:
            message = "; ".join(error.message for error in errors)
            raise CapabilityRuntimeError(f"invalid capability contract: {message}")
        return cls(dict(raw))

    @property
    def capability_id(self) -> str:
        return str(self.raw["id"])

    @property
    def version(self) -> str:
        return str(self.raw["version"])

    @property
    def authorities(self) -> frozenset[str]:
        return frozenset(str(value) for value in self.raw["authority_required"])

    @property
    def side_effects(self) -> frozenset[str]:
        return frozenset(str(value) for value in self.raw["side_effects"])

    @property
    def provenance_requirements(self) -> frozenset[str]:
        return frozenset(str(value) for value in self.raw["provenance_requirements"])

    def value_schema(self, direction: str) -> dict[str, Any]:
        ports = self.raw[f"{direction}s"]
        return {
            "type": "object",
            "properties": {str(port["name"]): port["schema"] for port in ports},
            "required": [str(port["name"]) for port in ports],
            "additionalProperties": False,
        }


@dataclass(frozen=True)
class CapabilityRequest:
    capability_id: str
    version: str
    inputs: Mapping[str, Any]
    authorities: frozenset[str] = frozenset()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    side_effects: frozenset[str] = frozenset()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityResult:
    invocation_id: str
    ok: bool
    started_at: str
    duration_ms: int
    outputs: Mapping[str, Any] | None = None
    failure: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    side_effects: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalHandler:
    command: tuple[str, ...]
    timeout_seconds: float = 30.0
    cwd: str | Path | None = None


Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]] | ExternalHandler


class CapabilityRuntime:
    """Dispatch explicitly configured implementations after lifecycle approval."""

    def __init__(self, store: Store):
        self.store = store
        self._handlers: dict[tuple[str, str], tuple[str, str, Handler]] = {}

    def configure(
        self,
        capability_id: str,
        version: str,
        implementation_id: str,
        implementation_version: str,
        handler: Handler,
    ) -> None:
        if isinstance(handler, ExternalHandler) and (
            not handler.command or handler.timeout_seconds <= 0
        ):
            raise CapabilityRuntimeError("external handler requires a command and positive timeout")
        contract = self._load_contract(capability_id, version)
        if implementation_id not in contract.raw["allowed_implementations"]:
            raise CapabilityRuntimeError("implementation is not bound by the capability contract")
        with self.store.db as connection:
            declared = connection.execute(
                """
                SELECT 1 FROM capability_implementations
                WHERE id = ? AND version = ? AND capability_id = ?
                  AND capability_version = ?
                """,
                (implementation_id, implementation_version, capability_id, version),
            ).fetchone()
        if declared is None:
            raise CapabilityRuntimeError("implementation version is not present in the graph")

        key = (capability_id, version)
        with self.store.db as connection:
            existing = connection.execute(
                """
                SELECT implementation_id, implementation_version
                FROM capability_runtime_state
                WHERE capability_id = ? AND capability_version = ?
                """,
                key,
            ).fetchone()
            if existing and tuple(existing) != (implementation_id, implementation_version):
                raise CapabilityRuntimeError("capability is already bound to another implementation")
            connection.execute(
                """
                INSERT OR IGNORE INTO capability_runtime_state(
                    capability_id, capability_version, implementation_id,
                    implementation_version, lifecycle
                ) VALUES (?, ?, ?, ?, 'proposed')
                """,
                (capability_id, version, implementation_id, implementation_version),
            )
        self._handlers[key] = (implementation_id, implementation_version, handler)

    def transition(self, capability_id: str, version: str, target: str) -> None:
        if target not in _LIFECYCLES:
            raise CapabilityRuntimeError(f"unknown lifecycle state: {target}")
        with self.store.db as connection:
            row = connection.execute(
                """
                SELECT lifecycle FROM capability_runtime_state
                WHERE capability_id = ? AND capability_version = ?
                """,
                (capability_id, version),
            ).fetchone()
            if row is None:
                raise CapabilityRuntimeError("capability is not configured")
            current = str(row["lifecycle"])
            if target not in _TRANSITIONS[current]:
                raise CapabilityRuntimeError(f"invalid lifecycle transition: {current} -> {target}")
            connection.execute(
                """
                UPDATE capability_runtime_state SET lifecycle = ?, updated_at = CURRENT_TIMESTAMP
                WHERE capability_id = ? AND capability_version = ?
                """,
                (target, capability_id, version),
            )

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        invocation_id = str(uuid.uuid4())
        started_at = datetime.now(UTC).isoformat()
        started = time.perf_counter()
        outputs: Mapping[str, Any] | None = None
        failure: Mapping[str, Any] | None = None
        implementation_id: str | None = None
        implementation_version: str | None = None

        try:
            configured = self._handlers.get((request.capability_id, request.version))
            if configured is None:
                raise _InvocationError("unregistered", "capability is not configured in this runtime")
            implementation_id, implementation_version, handler = configured
            contract = self._load_contract(request.capability_id, request.version)
            lifecycle = self._lifecycle(request.capability_id, request.version)
            if lifecycle != "active":
                raise _InvocationError("inactive", f"capability lifecycle is {lifecycle}")
            missing_authorities = sorted(contract.authorities - request.authorities)
            if missing_authorities:
                raise _InvocationError(
                    "authority_denied",
                    "required authority is missing",
                    {"missing": missing_authorities},
                )
            if request.side_effects != contract.side_effects:
                raise _InvocationError(
                    "side_effect_mismatch",
                    "declared side effects do not match the contract",
                )
            missing_provenance = sorted(
                contract.provenance_requirements - frozenset(request.provenance)
            )
            if missing_provenance:
                raise _InvocationError(
                    "provenance_missing",
                    "required provenance is missing",
                    {"missing": missing_provenance},
                )
            self._validate_values(contract.value_schema("input"), request.inputs, "invalid_input")
            outputs = self._dispatch(handler, request.inputs)
            self._validate_values(contract.value_schema("output"), outputs, "invalid_output")
        except _InvocationError as error:
            failure = {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        except Exception as error:  # defensive boundary for explicitly configured handlers
            failure = {
                "code": "implementation_error",
                "message": str(error),
                "details": {"type": type(error).__name__},
            }

        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        result = CapabilityResult(
            invocation_id=invocation_id,
            ok=failure is None,
            started_at=started_at,
            duration_ms=duration_ms,
            outputs=outputs if failure is None else None,
            failure=failure,
            provenance=dict(request.provenance),
            side_effects=tuple(sorted(request.side_effects)),
            evidence_refs=request.evidence_refs,
        )
        self._record(request, result, implementation_id, implementation_version)
        return result

    def _load_contract(self, capability_id: str, version: str) -> CapabilityContract:
        with self.store.db as connection:
            row = connection.execute(
                "SELECT manifest_json FROM capability_manifest_sets LIMIT 1",
            ).fetchone()
        if row is None:
            raise CapabilityRuntimeError("capability contract is not present in the graph")
        manifest = json.loads(row["manifest_json"])
        contract = next(
            (
                item
                for item in manifest["capabilities"]
                if item["id"] == capability_id and item["version"] == version
            ),
            None,
        )
        if contract is None:
            raise CapabilityRuntimeError("capability contract is not present in the graph")
        return CapabilityContract.from_dict(contract)

    def _lifecycle(self, capability_id: str, version: str) -> str:
        with self.store.db as connection:
            row = connection.execute(
                """
                SELECT lifecycle FROM capability_runtime_state
                WHERE capability_id = ? AND capability_version = ?
                """,
                (capability_id, version),
            ).fetchone()
        if row is None:
            raise _InvocationError("unregistered", "capability lifecycle is not configured")
        return str(row["lifecycle"])

    @staticmethod
    def _validate_values(schema: Mapping[str, Any], values: Mapping[str, Any], code: str) -> None:
        errors = sorted(Draft202012Validator(schema).iter_errors(values), key=lambda error: list(error.path))
        if errors:
            raise _InvocationError(code, "; ".join(error.message for error in errors))

    @staticmethod
    def _dispatch(handler: Handler, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(handler, ExternalHandler):
            return handler(inputs)
        try:
            completed = subprocess.run(
                handler.command,
                input=json.dumps(inputs, sort_keys=True, separators=(",", ":")),
                capture_output=True,
                text=True,
                cwd=handler.cwd,
                timeout=handler.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise _InvocationError(
                "timeout",
                "external implementation exceeded its timeout",
                {"timeout_seconds": handler.timeout_seconds},
            ) from error
        if completed.returncode != 0:
            raise _InvocationError(
                "external_failure",
                "external implementation returned a non-zero exit code",
                {"returncode": completed.returncode, "stderr": completed.stderr[-2000:]},
            )
        try:
            output = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise _InvocationError("invalid_output", "external implementation returned invalid JSON") from error
        if not isinstance(output, dict):
            raise _InvocationError("invalid_output", "external implementation output must be an object")
        return output

    def _record(
        self,
        request: CapabilityRequest,
        result: CapabilityResult,
        implementation_id: str | None,
        implementation_version: str | None,
    ) -> None:
        result_payload = {
            "ok": result.ok,
            "outputs": result.outputs,
            "failure": result.failure,
        }
        with self.store.db as connection:
            connection.execute(
                """
                INSERT INTO capability_invocations(
                    invocation_id, capability_id, capability_version,
                    implementation_id, implementation_version, request_json,
                    result_json, status, started_at, duration_ms, provenance_json,
                    side_effects_json, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.invocation_id,
                    request.capability_id,
                    request.version,
                    implementation_id,
                    implementation_version,
                    json.dumps(request.inputs, sort_keys=True, separators=(",", ":")),
                    json.dumps(result_payload, sort_keys=True, separators=(",", ":")),
                    "success" if result.ok else "failure",
                    result.started_at,
                    result.duration_ms,
                    json.dumps(result.provenance, sort_keys=True, separators=(",", ":")),
                    json.dumps(result.side_effects),
                    json.dumps(result.evidence_refs),
                ),
            )


def validate_json_schema(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    validator = Draft202012Validator(inputs["schema"])
    errors = sorted(validator.iter_errors(inputs["instance"]), key=lambda error: list(error.path))
    return {
        "valid": not errors,
        "errors": [
            {"path": "/".join(str(part) for part in error.path), "message": error.message}
            for error in errors
        ],
    }


def hash_content(allowed_roots: Sequence[str | Path]) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    roots = _resolved_roots(allowed_roots)

    def handler(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        source = inputs["source"]
        if "text" in source:
            payload = str(source["text"]).encode("utf-8")
        else:
            payload = _allowed_path(source["path"], roots).read_bytes()
        return {"algorithm": "sha256", "digest": hashlib.sha256(payload).hexdigest()}

    return handler


def query_sqlite_fts(
    allowed_roots: Sequence[str | Path],
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    roots = _resolved_roots(allowed_roots)

    def handler(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        database = _allowed_path(inputs["database"], roots)
        table = str(inputs["table"])
        if not _IDENTIFIER.fullmatch(table):
            raise ValueError("invalid FTS table identifier")
        uri = f"{database.as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f'SELECT rowid, * FROM "{table}" WHERE "{table}" MATCH ? LIMIT ?',
                (inputs["query"], inputs["limit"]),
            ).fetchall()
        return {"rows": [dict(row) for row in rows]}

    return handler


def _resolved_roots(allowed_roots: Sequence[str | Path]) -> tuple[Path, ...]:
    if not allowed_roots:
        raise CapabilityRuntimeError("at least one allowed root is required")
    return tuple(Path(root).resolve(strict=True) for root in allowed_roots)


def _allowed_path(value: Any, roots: Sequence[Path]) -> Path:
    candidate = Path(str(value)).resolve(strict=True)
    if not any(candidate.is_relative_to(root) for root in roots):
        raise _InvocationError("undeclared_read", "path is outside configured roots")
    if not candidate.is_file():
        raise ValueError("path is not a file")
    return candidate
