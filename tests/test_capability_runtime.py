import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from erasmus.capability_graph import CapabilityGraph
from erasmus.capability_runtime import (
    CapabilityRequest,
    CapabilityRuntime,
    CapabilityRuntimeError,
    ExternalHandler,
    hash_content,
    query_sqlite_fts,
    validate_json_schema,
)
from erasmus.store import Store


MANIFEST = Path("capabilities/okf/pr-governance")
PROVENANCE = {"caller": "pytest", "request_id": "request-1"}


def runtime(tmp_path):
    store = Store(str(tmp_path / "runtime.db"))
    store.init()
    CapabilityGraph(store.db).import_bundle(MANIFEST)
    return store, CapabilityRuntime(store)


def activate(subject, capability_id, implementation_id, handler):
    subject.configure(capability_id, "1.0.0", implementation_id, "1.0.0", handler)
    for state in (
        "implemented",
        "isolated_test",
        "adversarial_review",
        "approved",
        "active",
    ):
        subject.transition(capability_id, "1.0.0", state)


def request(capability_id, inputs, authorities, side_effects=frozenset(), provenance=PROVENANCE):
    return CapabilityRequest(
        capability_id=capability_id,
        version="1.0.0",
        inputs=inputs,
        authorities=frozenset(authorities),
        provenance=provenance,
        side_effects=frozenset(side_effects),
        evidence_refs=("evidence:test",),
    )


def test_reference_capabilities_execute_and_persist(tmp_path):
    store, subject = runtime(tmp_path)
    activate(subject, "validate_json_schema", "jsonschema_validator", validate_json_schema)
    activate(subject, "hash_content", "sha256_hasher", hash_content([tmp_path]))

    schema_result = subject.invoke(
        request(
            "validate_json_schema",
            {"schema": {"type": "integer"}, "instance": "wrong"},
            {"schema:validate"},
        )
    )
    assert schema_result.ok and schema_result.outputs["valid"] is False
    assert schema_result.provenance == PROVENANCE

    text_result = subject.invoke(
        request(
            "hash_content",
            {"source": {"text": "erasmus"}},
            {"content:hash", "file:read"},
        )
    )
    assert text_result.outputs == {
        "algorithm": "sha256",
        "digest": hashlib.sha256(b"erasmus").hexdigest(),
    }

    content = tmp_path / "content.txt"
    content.write_text("protomenta", encoding="utf-8")
    file_result = subject.invoke(
        request(
            "hash_content",
            {"source": {"path": str(content)}},
            {"content:hash", "file:read"},
        )
    )
    assert file_result.outputs["digest"] == hashlib.sha256(b"protomenta").hexdigest()
    assert store.db.execute("SELECT COUNT(*) FROM capability_invocations").fetchone()[0] == 3


def test_sqlite_fts_is_bounded_and_read_only(tmp_path):
    database = tmp_path / "knowledge.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE VIRTUAL TABLE notes USING fts5(body)")
        connection.executemany("INSERT INTO notes(body) VALUES(?)", [("red fox",), ("blue fox",)])

    _, subject = runtime(tmp_path)
    activate(subject, "query_sqlite_fts", "sqlite_fts_reader", query_sqlite_fts([tmp_path]))
    result = subject.invoke(
        request(
            "query_sqlite_fts",
            {"database": str(database), "table": "notes", "query": "fox", "limit": 1},
            {"database:read"},
        )
    )
    assert result.ok and len(result.outputs["rows"]) == 1


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda value: value.update(authorities=frozenset()), "authority_denied"),
        (lambda value: value.update(provenance={}), "provenance_missing"),
        (lambda value: value.update(side_effects=frozenset({"file:write"})), "side_effect_mismatch"),
        (lambda value: value.update(inputs={"source": {"unexpected": "x"}}), "invalid_input"),
    ],
)
def test_requests_fail_closed_and_are_recorded(tmp_path, change, code):
    store, subject = runtime(tmp_path)
    activate(subject, "hash_content", "sha256_hasher", hash_content([tmp_path]))
    values = {
        "inputs": {"source": {"text": "x"}},
        "authorities": frozenset({"content:hash", "file:read"}),
        "provenance": PROVENANCE,
        "side_effects": frozenset(),
    }
    change(values)
    result = subject.invoke(
        CapabilityRequest("hash_content", "1.0.0", evidence_refs=(), **values)
    )
    assert not result.ok and result.failure["code"] == code
    assert store.db.execute("SELECT status FROM capability_invocations").fetchone()[0] == "failure"


def test_unregistered_inactive_and_undeclared_read_fail_closed(tmp_path):
    store, subject = runtime(tmp_path)
    unregistered = subject.invoke(
        request("hash_content", {"source": {"text": "x"}}, {"content:hash", "file:read"})
    )
    assert unregistered.failure["code"] == "unregistered"

    subject.configure("hash_content", "1.0.0", "sha256_hasher", "1.0.0", hash_content([tmp_path]))
    inactive = subject.invoke(
        request("hash_content", {"source": {"text": "x"}}, {"content:hash", "file:read"})
    )
    assert inactive.failure["code"] == "inactive"
    for state in ("implemented", "isolated_test", "adversarial_review", "approved", "active"):
        subject.transition("hash_content", "1.0.0", state)

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    denied = subject.invoke(
        request(
            "hash_content",
            {"source": {"path": str(outside)}},
            {"content:hash", "file:read"},
        )
    )
    assert denied.failure["code"] == "undeclared_read"
    assert store.db.execute("SELECT COUNT(*) FROM capability_invocations").fetchone()[0] == 3


def test_lifecycle_and_implementation_binding_are_strict(tmp_path):
    _, subject = runtime(tmp_path)
    with pytest.raises(CapabilityRuntimeError, match="not bound"):
        subject.configure("hash_content", "1.0.0", "other", "1.0.0", lambda _: {})
    subject.configure("hash_content", "1.0.0", "sha256_hasher", "1.0.0", hash_content([tmp_path]))
    with pytest.raises(CapabilityRuntimeError, match="invalid lifecycle"):
        subject.transition("hash_content", "1.0.0", "active")


def test_invalid_implementation_output_is_typed(tmp_path):
    _, subject = runtime(tmp_path)
    activate(subject, "validate_json_schema", "jsonschema_validator", lambda _: {"valid": True})
    result = subject.invoke(
        request(
            "validate_json_schema",
            {"schema": {"type": "integer"}, "instance": 1},
            {"schema:validate"},
        )
    )
    assert result.failure["code"] == "invalid_output"


def test_external_dispatch_returns_typed_failures(tmp_path):
    _, subject = runtime(tmp_path)
    success = ExternalHandler(
        (
            sys.executable,
            "-c",
            "import json,sys; value=json.load(sys.stdin); "
            "print(json.dumps({'build_result': {'head_sha': value['head_sha']}}))",
        )
    )
    activate(subject, "compile_build", "python_builder", success)
    external_request = request(
        "compile_build",
        {"head_sha": "abc123"},
        {"process:execute"},
        {"writes_build_artifacts"},
        {"head_sha": "abc123", "command": "python", "tool_version": sys.version},
    )
    assert subject.invoke(external_request).outputs["build_result"]["head_sha"] == "abc123"

    _, failing_runtime = runtime(tmp_path / "failure")
    activate(
        failing_runtime,
        "compile_build",
        "python_builder",
        ExternalHandler((sys.executable, "-c", "raise SystemExit(7)")),
    )
    assert failing_runtime.invoke(external_request).failure["code"] == "external_failure"

    _, timeout_runtime = runtime(tmp_path / "timeout")
    activate(
        timeout_runtime,
        "compile_build",
        "python_builder",
        ExternalHandler((sys.executable, "-c", "import time; time.sleep(2)"), timeout_seconds=0.01),
    )
    assert timeout_runtime.invoke(external_request).failure["code"] == "timeout"


def test_invocation_ledger_is_append_only(tmp_path):
    store, subject = runtime(tmp_path)
    activate(subject, "validate_json_schema", "jsonschema_validator", validate_json_schema)
    result = subject.invoke(
        request(
            "validate_json_schema",
            {"schema": {"type": "integer"}, "instance": 1},
            {"schema:validate"},
        )
    )
    assert result.ok
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute(
            "UPDATE capability_invocations SET status = 'failure' WHERE invocation_id = ?",
            (result.invocation_id,),
        )
    store.db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute(
            "DELETE FROM capability_invocations WHERE invocation_id = ?",
            (result.invocation_id,),
        )
