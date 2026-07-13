import base64
import json
import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from erasmus.capability_graph import CapabilityGraph
from erasmus.store import Store
from erasmus.tool_registry import (
    ToolRegistry,
    _repository_identity,
    artifact_digest,
    load_tool_manifest,
    sign_manifest,
    validate_tool_manifest,
    validate_toolchain_document,
)


TARGET = "any-py3-none"
MANIFESTS = Path("tools/manifests")


def registry(tmp_path):
    store = Store(str(tmp_path / "registry.db"))
    store.init()
    CapabilityGraph(store.db).import_bundle("capabilities/okf/pr-governance")
    result = ToolRegistry(store.db, tmp_path / "cache")
    publishers = json.loads(Path("tools/publishers.json").read_text())["publishers"]
    for publisher in publishers:
        result.trust_publisher(
            publisher["key_id"], base64.b64decode(publisher["public_key"]), publisher["owner"]
        )
    return result


def register_all(tool_registry):
    for path in sorted(MANIFESTS.glob("*.json")):
        tool_registry.register(load_tool_manifest(path))


def test_canonical_manifests_signatures_digests_and_toolchain(tmp_path):
    tool_registry = registry(tmp_path)
    for path in sorted(MANIFESTS.glob("*.json")):
        manifest = load_tool_manifest(path)
        assert validate_tool_manifest(manifest) == []
        assert artifact_digest(manifest["entrypoint"]["artifact"]) == manifest["digest"]["value"]
        tool_registry.register(manifest)
    assert validate_toolchain_document("TOOLCHAIN.md", MANIFESTS) == []
    assert {item["lifecycle"] for item in tool_registry.list()} == {"candidate"}


def test_verify_install_activate_resolve_execute_and_restart(tmp_path, monkeypatch):
    tool_registry = registry(tmp_path)
    register_all(tool_registry)
    manifest = load_tool_manifest(MANIFESTS / "sqlite_reader.json")
    artifact = manifest["entrypoint"]["artifact"]
    tool_registry.verify(manifest, artifact, TARGET)
    cached = tool_registry.install(manifest, artifact)
    tool_registry.activate("sqlite_reader", "1.0.0", TARGET)

    data = sqlite3.connect(tmp_path / "data.db")
    data.execute("CREATE TABLE values_for_test(value TEXT)")
    data.execute("INSERT INTO values_for_test VALUES('governed')")
    data.commit()
    data.close()
    fake_path = tmp_path / "fake-bin"
    fake_path.mkdir()
    (fake_path / "sqlite_reader.py").write_text("raise SystemExit('PATH shadow')")
    monkeypatch.setenv("PATH", str(fake_path))
    completed = tool_registry.execute(
        "query_sqlite", "1.0.0", TARGET, {"database:read"}, set(),
        [str(tmp_path / "data.db"), "SELECT value FROM values_for_test"], tmp_path,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout) == [{"value": "governed"}]
    assert cached.relative_to(tool_registry.cache_root).as_posix() in {
        item["cache_path"] for item in tool_registry.export()["tools"]
    }

    reopened = Store(str(tmp_path / "registry.db"))
    reopened.init()
    assert ToolRegistry(reopened.db, tmp_path / "cache").resolve(
        "query_sqlite", "1.0.0", TARGET, {"database:read"}, set()
    )["tool_id"] == "sqlite_reader"


def test_digest_target_signature_provenance_and_authority_fail_closed(tmp_path):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "pytest_runner.json")
    tampered_manifest = deepcopy(manifest)
    tampered_manifest["source"]["commit"] = "not-a-sha"
    assert validate_tool_manifest(tampered_manifest)

    untrusted = deepcopy(manifest)
    untrusted["signature"]["key_id"] = "unknown"
    with pytest.raises(PermissionError, match="publisher"):
        tool_registry.register(untrusted)

    tool_registry.register(manifest)
    tampered = tmp_path / "tampered.py"
    tampered.write_text("print('tampered')")
    with pytest.raises(ValueError, match="digest mismatch"):
        tool_registry.verify(manifest, tampered, TARGET)
    with pytest.raises(LookupError, match="unknown tool"):
        tool_registry.verify(manifest, manifest["entrypoint"]["artifact"], "windows-x86_64")

    tool_registry.verify(manifest, manifest["entrypoint"]["artifact"], TARGET)
    tool_registry.install(manifest, manifest["entrypoint"]["artifact"])
    tool_registry.activate("pytest_runner", "1.0.0", TARGET)
    with pytest.raises(PermissionError, match="authority"):
        tool_registry.resolve("run_tests", "1.0.0", TARGET, set(), set())


@pytest.mark.parametrize("lifecycle", ["quarantined", "deprecated", "revoked"])
def test_disabled_lifecycle_uninstall_and_audit_survive(tmp_path, lifecycle):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "pytest_runner.json")
    tool_registry.register(manifest)
    tool_registry.verify(manifest, manifest["entrypoint"]["artifact"], TARGET)
    cached = tool_registry.install(manifest, manifest["entrypoint"]["artifact"])
    tool_registry.set_lifecycle("pytest_runner", "1.0.0", TARGET, lifecycle)
    with pytest.raises(LookupError):
        tool_registry.resolve("run_tests", "1.0.0", TARGET, {"process:execute"}, set())
    tool_registry.uninstall("pytest_runner", "1.0.0", TARGET)
    assert not cached.exists()
    exported = tool_registry.export()
    assert any(item["event"] == "uninstalled" for item in exported["audit"])
    assert tool_registry.list()[0]["lifecycle"] == lifecycle


def test_duplicate_registration_and_toolchain_drift_fail(tmp_path):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "pytest_runner.json")
    tool_registry.register(manifest)
    with pytest.raises(sqlite3.IntegrityError):
        tool_registry.register(manifest)
    drifted = tmp_path / "TOOLCHAIN.md"
    drifted.write_text("# Purpose and scope\n")
    assert validate_toolchain_document(drifted, MANIFESTS)


def test_valid_signature_cannot_grant_undeclared_capability(tmp_path):
    tool_registry = registry(tmp_path)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    tool_registry.trust_publisher("test-key", public, "test publisher")
    manifest = load_tool_manifest(MANIFESTS / "pytest_runner.json")
    manifest["capabilities"] = [{"id": "merge_pull_request", "version": "1.0.0"}]
    with pytest.raises(ValueError, match="undeclared capability implementation"):
        tool_registry.register(sign_manifest(manifest, "test-key", key))


def test_concurrent_registration_keeps_one_canonical_row(tmp_path):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "pytest_runner.json")
    path = tmp_path / "registry.db"

    def register_once():
        store = Store(str(path))
        store.init()
        try:
            ToolRegistry(store.db, tmp_path / "cache").register(manifest)
            return "registered"
        except sqlite3.IntegrityError:
            return "duplicate"
        finally:
            store.db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: register_once(), range(2)))
    assert outcomes == ["duplicate", "registered"]
    assert len(tool_registry.list()) == 1


def test_install_preserves_permissions_and_uses_portable_cache_path(tmp_path):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "sqlite_reader.json")
    artifact = tmp_path / "sqlite_reader.py"
    artifact.write_bytes(Path(manifest["entrypoint"]["artifact"]).read_bytes())
    artifact.chmod(0o755)
    tool_registry.register(manifest)
    tool_registry.verify(manifest, artifact, TARGET)
    cached = tool_registry.install(manifest, artifact)
    if os.name != "nt":
        assert cached.stat().st_mode & 0o111
    assert not Path(tool_registry.list()[0]["cache_path"]).is_absolute()


def test_timeout_is_audited_without_argument_or_output_leak(tmp_path, monkeypatch):
    tool_registry = registry(tmp_path)
    manifest = load_tool_manifest(MANIFESTS / "sqlite_reader.json")
    tool_registry.register(manifest)
    tool_registry.verify(manifest, manifest["entrypoint"]["artifact"], TARGET)
    tool_registry.install(manifest, manifest["entrypoint"]["artifact"])
    tool_registry.activate("sqlite_reader", "1.0.0", TARGET)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr("erasmus.tool_registry.subprocess.run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        tool_registry.execute(
            "query_sqlite", "1.0.0", TARGET, {"database:read"}, set(),
            ["secret-input"], tmp_path,
        )
    detail = tool_registry.export()["audit"][-1]
    assert detail["event"] == "execution_timed_out"
    assert "secret-input" not in detail["detail_json"]


def test_repository_and_toolchain_paths_are_normalized(tmp_path):
    assert _repository_identity("git@github.com:HaggisSupper/erasmus-protomenta.git") == (
        "github.com", "haggissupper/erasmus-protomenta"
    )
    document = tmp_path / "TOOLCHAIN.md"
    document.write_text(Path("TOOLCHAIN.md").read_text() + "\nThe latest verified tools are listed.\n")
    assert validate_toolchain_document(document, MANIFESTS.resolve()) == []
    document.write_text(document.read_text() + "\nForbidden: run_tests@latest\n")
    assert "mutable latest identity is forbidden" in validate_toolchain_document(
        document, MANIFESTS.resolve()
    )
