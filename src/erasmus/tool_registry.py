"""Signed, content-addressed local tool registry."""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "tools" / "contracts" / "tool.schema.json"
LIFECYCLES = {"candidate", "verified", "active", "quarantined", "deprecated", "revoked"}


def canonical_payload(manifest: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign_manifest(
    manifest: dict[str, Any], key_id: str, private_key: Ed25519PrivateKey
) -> dict[str, Any]:
    signed = json.loads(json.dumps(manifest))
    signed["signature"] = {
        "scheme": "ed25519",
        "key_id": key_id,
        "value": base64.b64encode(private_key.sign(canonical_payload(signed))).decode(),
    }
    return signed


def artifact_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_tool_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_tool_manifest(manifest: dict[str, Any]) -> list[str]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"schema:{'/'.join(map(str, error.path)) or '/'}: {error.message}"
        for error in sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
    ]


class ToolRegistry:
    def __init__(self, db: sqlite3.Connection, cache_root: str | Path = "state/tool-cache") -> None:
        self.db = db
        self.cache_root = Path(cache_root).resolve()

    def _audit(self, event: str, manifest: dict[str, Any], detail: Any) -> None:
        self.db.execute(
            "INSERT INTO tool_audit(event, tool_id, version, target, detail_json) VALUES(?, ?, ?, ?, ?)",
            (event, manifest["tool_id"], manifest["version"], manifest["target"],
             json.dumps(detail, sort_keys=True)),
        )

    def trust_publisher(self, key_id: str, public_key: bytes, owner: str) -> None:
        encoded = base64.b64encode(public_key).decode()
        existing = self.db.execute(
            "SELECT public_key FROM tool_publishers WHERE key_id=?", (key_id,)
        ).fetchone()
        if existing is not None and existing[0] != encoded:
            raise PermissionError("publisher key replacement requires an explicit migration")
        with self.db:
            self.db.execute(
                "INSERT INTO tool_publishers(key_id, public_key, owner) VALUES(?, ?, ?) ON CONFLICT(key_id) DO UPDATE SET public_key=excluded.public_key, owner=excluded.owner, status='trusted'",
                (key_id, encoded, owner),
            )

    def register(self, manifest: dict[str, Any]) -> None:
        errors = validate_tool_manifest(manifest)
        if errors:
            raise ValueError("; ".join(errors))
        publisher = self.db.execute(
            "SELECT public_key FROM tool_publishers WHERE key_id=? AND status='trusted'",
            (manifest["signature"]["key_id"],),
        ).fetchone()
        if publisher is None:
            raise PermissionError("unknown or untrusted publisher")
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(publisher[0])).verify(
                base64.b64decode(manifest["signature"]["value"]), canonical_payload(manifest)
            )
        except (InvalidSignature, ValueError) as exc:
            raise PermissionError("invalid manifest signature") from exc
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip().removesuffix(".git")
        if remote != manifest["source"]["repository"]:
            raise ValueError("source repository provenance mismatch")
        source = subprocess.run(
            ["git", "show", f"{manifest['source']['commit']}:{manifest['entrypoint']['artifact']}"],
            cwd=ROOT, capture_output=True, check=False,
        )
        if source.returncode or hashlib.sha256(source.stdout).hexdigest() != manifest["digest"]["value"]:
            raise ValueError("source commit provenance does not reproduce the artifact digest")
        for capability in manifest["capabilities"]:
            binding = self.db.execute(
                "SELECT 1 FROM capability_implementations WHERE id=? AND capability_id=? AND capability_version=?",
                (manifest["implementation_id"], capability["id"], capability["version"]),
            ).fetchone()
            if binding is None:
                raise ValueError(
                    f"undeclared capability implementation: {capability['id']}@{capability['version']}"
                )
        lifecycle = {
            "valid": "candidate", "deprecated": "deprecated", "revoked": "revoked"
        }[manifest["revocation_status"]]
        with self.db:
            self.db.execute(
                "INSERT INTO tool_manifests(tool_id, version, target, implementation_id, digest, manifest_json, lifecycle) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (manifest["tool_id"], manifest["version"], manifest["target"],
                 manifest["implementation_id"], manifest["digest"]["value"],
                 json.dumps(manifest, sort_keys=True), lifecycle),
            )
            self.db.executemany(
                "INSERT INTO tool_capabilities VALUES(?, ?, ?, ?, ?)",
                ((manifest["tool_id"], manifest["version"], manifest["target"],
                  capability["id"], capability["version"])
                 for capability in manifest["capabilities"]),
            )
            self._audit("registered", manifest, {"lifecycle": lifecycle})

    def _manifest(self, tool_id: str, version: str, target: str) -> tuple[dict[str, Any], str, str | None]:
        row = self.db.execute(
            "SELECT manifest_json, lifecycle, cache_path FROM tool_manifests WHERE tool_id=? AND version=? AND target=?",
            (tool_id, version, target),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown tool: {tool_id}@{version} ({target})")
        return json.loads(row[0]), row[1], row[2]

    def verify(self, manifest: dict[str, Any], artifact: str | Path, target: str) -> None:
        stored, lifecycle, _ = self._manifest(manifest["tool_id"], manifest["version"], target)
        if stored != manifest or lifecycle in {"quarantined", "deprecated", "revoked"}:
            raise PermissionError(f"tool cannot be verified from lifecycle {lifecycle}")
        actual = artifact_digest(artifact)
        if actual != manifest["digest"]["value"]:
            raise ValueError("artifact digest mismatch")
        with self.db:
            self.db.execute(
                "UPDATE tool_manifests SET lifecycle='verified' WHERE tool_id=? AND version=? AND target=?",
                (manifest["tool_id"], manifest["version"], target),
            )
            self._audit("verified", manifest, {"digest": actual})

    def install(self, manifest: dict[str, Any], artifact: str | Path) -> Path:
        _, lifecycle, _ = self._manifest(
            manifest["tool_id"], manifest["version"], manifest["target"]
        )
        if lifecycle != "verified":
            raise PermissionError("only verified tools may be installed")
        destination = (
            self.cache_root / manifest["digest"]["value"] / manifest["target"]
            / Path(manifest["entrypoint"]["artifact"]).name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact, destination)
        if artifact_digest(destination) != manifest["digest"]["value"]:
            destination.unlink(missing_ok=True)
            raise ValueError("cached artifact digest mismatch")
        with self.db:
            self.db.execute(
                "UPDATE tool_manifests SET cache_path=? WHERE tool_id=? AND version=? AND target=?",
                (str(destination), manifest["tool_id"], manifest["version"], manifest["target"]),
            )
            self._audit("installed", manifest, {"cache_path": str(destination)})
        return destination

    def activate(self, tool_id: str, version: str, target: str) -> None:
        manifest, lifecycle, cache_path = self._manifest(tool_id, version, target)
        if lifecycle != "verified" or cache_path is None or artifact_digest(cache_path) != manifest["digest"]["value"]:
            raise PermissionError("tool must be verified and installed before activation")
        capability_pairs = {(item["id"], item["version"]) for item in manifest["capabilities"]}
        with self.db:
            active = self.db.execute(
                "SELECT manifest_json FROM tool_manifests WHERE lifecycle='active' AND target=?",
                (target,),
            ).fetchall()
            for row in active:
                other = json.loads(row[0])
                if capability_pairs & {(item["id"], item["version"]) for item in other["capabilities"]}:
                    self.db.execute(
                        "UPDATE tool_manifests SET lifecycle='verified' WHERE tool_id=? AND version=? AND target=?",
                        (other["tool_id"], other["version"], other["target"]),
                    )
            self.db.execute(
                "UPDATE tool_manifests SET lifecycle='active' WHERE tool_id=? AND version=? AND target=?",
                (tool_id, version, target),
            )
            self._audit("activated", manifest, {})

    def resolve(
        self, capability_id: str, capability_version: str, target: str,
        authorities: set[str], side_effects: set[str],
    ) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT m.manifest_json FROM tool_manifests m JOIN tool_capabilities c ON c.tool_id=m.tool_id AND c.tool_version=m.version AND c.target=m.target WHERE c.capability_id=? AND c.capability_version=? AND m.target=? AND m.lifecycle='active'",
            (capability_id, capability_version, target),
        ).fetchall()
        if len(rows) != 1:
            raise LookupError("capability has no unambiguous active implementation")
        manifest = json.loads(rows[0][0])
        if not set(manifest["authority_required"]) <= authorities:
            raise PermissionError("authority mismatch")
        if set(manifest["side_effects"]) != side_effects:
            raise PermissionError("side-effect declaration mismatch")
        return manifest

    def execute(
        self, capability_id: str, capability_version: str, target: str,
        authorities: set[str], side_effects: set[str], args: list[str], cwd: str | Path,
    ) -> subprocess.CompletedProcess[str]:
        manifest = self.resolve(capability_id, capability_version, target, authorities, side_effects)
        _, _, cache_path = self._manifest(manifest["tool_id"], manifest["version"], target)
        if cache_path is None or artifact_digest(cache_path) != manifest["digest"]["value"]:
            raise PermissionError("cached artifact is missing or tampered")
        command = ([sys.executable] if manifest["entrypoint"]["runtime"] == "python" else []) + [cache_path, *args]
        completed = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            timeout=manifest["timeout_seconds"], check=False,
        )
        with self.db:
            self._audit("executed", manifest, {
                "argument_digest": hashlib.sha256(json.dumps(args).encode()).hexdigest(),
                "returncode": completed.returncode,
                "stdout_digest": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                "stderr_digest": hashlib.sha256(completed.stderr.encode()).hexdigest(),
            })
        return completed

    def set_lifecycle(self, tool_id: str, version: str, target: str, lifecycle: str) -> None:
        if lifecycle not in {"quarantined", "deprecated", "revoked"}:
            raise ValueError("only quarantine, deprecation, or revocation is allowed")
        manifest, _, _ = self._manifest(tool_id, version, target)
        with self.db:
            self.db.execute(
                "UPDATE tool_manifests SET lifecycle=? WHERE tool_id=? AND version=? AND target=?",
                (lifecycle, tool_id, version, target),
            )
            self._audit(lifecycle, manifest, {})

    def deactivate(self, tool_id: str, version: str, target: str) -> None:
        manifest, lifecycle, _ = self._manifest(tool_id, version, target)
        if lifecycle != "active":
            raise ValueError("only an active tool can be deactivated")
        with self.db:
            self.db.execute(
                "UPDATE tool_manifests SET lifecycle='verified' WHERE tool_id=? AND version=? AND target=?",
                (tool_id, version, target),
            )
            self._audit("deactivated", manifest, {})

    def uninstall(self, tool_id: str, version: str, target: str) -> None:
        manifest, lifecycle, cache_path = self._manifest(tool_id, version, target)
        if lifecycle == "active":
            raise PermissionError("deactivate or revoke before uninstall")
        if cache_path:
            path = Path(cache_path).resolve()
            if not path.is_relative_to(self.cache_root):
                raise ValueError("unsafe cache path")
            path.unlink(missing_ok=True)
        with self.db:
            self.db.execute(
                "UPDATE tool_manifests SET cache_path=NULL WHERE tool_id=? AND version=? AND target=?",
                (tool_id, version, target),
            )
            self._audit("uninstalled", manifest, {})

    def list(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT tool_id, version, target, implementation_id, digest, lifecycle, cache_path FROM tool_manifests ORDER BY tool_id, version, target"
        ).fetchall()]

    def inspect(self, tool_id: str, version: str, target: str) -> dict[str, Any]:
        manifest, lifecycle, cache_path = self._manifest(tool_id, version, target)
        return {"manifest": manifest, "lifecycle": lifecycle, "cache_path": cache_path}

    def export(self) -> dict[str, Any]:
        return {
            "tools": self.list(),
            "audit": [dict(row) for row in self.db.execute(
                "SELECT event, tool_id, version, target, detail_json, created_at FROM tool_audit ORDER BY id"
            ).fetchall()],
        }


def validate_toolchain_document(path: str | Path, manifest_dir: str | Path) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    required = [
        "# Purpose and scope", "# Deterministic-first policy", "# Supported platforms",
        "# Runtime priorities", "# Governed tools", "# Lifecycle state",
        "# Operations", "# Trust boundaries", "# Cache and registry",
        "# Verification", "# Exceptions and waivers", "# Contract relationships",
    ]
    errors = [f"missing section: {heading}" for heading in required if heading not in text]
    for manifest_path in sorted(Path(manifest_dir).glob("*.json")):
        manifest = load_tool_manifest(manifest_path)
        for value in (
            manifest_path.as_posix(), manifest["version"], manifest["digest"]["value"],
            manifest["source"]["commit"], manifest["signature"]["key_id"],
        ):
            if value not in text:
                errors.append(f"TOOLCHAIN.md omits governed value: {value}")
    if " latest " in f" {text.lower()} ":
        errors.append("mutable latest identity is forbidden")
    return errors
