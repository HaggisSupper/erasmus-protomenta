"""Small, fail-closed guard for immutable execution contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractViolation(ValueError):
    """Raised when an execution request cannot be proven contract-safe."""


def contract_hash(contract: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest for a JSON contract snapshot."""
    try:
        payload = json.dumps(
            contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    except (TypeError, ValueError) as exc:
        raise ContractViolation("contract is not JSON serializable") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ContractEnforcer:
    """Authorize only requests matching an immutable snapshot and root allowlist."""

    def __init__(
        self, contract: Mapping[str, Any], allowed_roots: Iterable[str | Path] = ()
    ):
        if not isinstance(contract, Mapping):
            raise ContractViolation("contract is required")
        self.contract = dict(contract)
        self.snapshot_hash = contract_hash(self.contract)
        self.allowed_roots = tuple(Path(root).resolve() for root in allowed_roots)

    def verify_snapshot(self, snapshot: Mapping[str, Any] | str | None) -> None:
        """Reject missing or changed snapshots (never silently continue)."""
        supplied = (
            contract_hash(snapshot) if isinstance(snapshot, Mapping) else snapshot
        )
        if not isinstance(supplied, str) or supplied.lower() != self.snapshot_hash:
            raise ContractViolation("immutable contract snapshot mismatch")

    def check_root(self, root: str | Path) -> Path:
        if not self.allowed_roots:
            raise ContractViolation("no allowed roots configured")
        candidate = Path(root).resolve() if isinstance(root, (str, Path)) else None
        if candidate is None or not any(
            candidate == allowed or allowed in candidate.parents
            for allowed in self.allowed_roots
        ):
            raise ContractViolation("path is outside the allowed roots")
        if not candidate.is_dir():
            raise ContractViolation("project root does not exist")
        return candidate

    def authorize(self, capability: str, granted: Iterable[str] = ()) -> None:
        if not isinstance(capability, str) or not capability.strip():
            raise ContractViolation("capability is required")
        declared = self.contract.get(
            "capabilities", self.contract.get("allowed_capabilities", ())
        )
        declared = (
            {str(item) for item in declared}
            if isinstance(declared, (list, tuple, set, frozenset))
            else set()
        )
        granted_set = {str(item) for item in granted}
        if capability not in declared or capability not in granted_set:
            raise ContractViolation(f"capability is not authorized: {capability}")

    def enforce(
        self,
        *,
        snapshot: Mapping[str, Any] | str | None,
        root: str | Path,
        capability: str,
        granted: Iterable[str] = (),
    ) -> Path:
        self.verify_snapshot(snapshot)
        checked = self.check_root(root)
        self.authorize(capability, granted)
        return checked


@dataclass(frozen=True)
class ContractSnapshot:
    root: Path
    digests: dict[str, str]


def _files(root: Path) -> tuple[Path, ...]:
    return (
        root / "constitution" / "immutable-contract.md",
        root / "governance" / "agent-control-policy.yaml",
    )


def load_contract_snapshot(root: str | Path) -> ContractSnapshot:
    root = Path(root).resolve()
    digests: dict[str, str] = {}
    for path in _files(root):
        if not path.is_file():
            raise ContractViolation(f"missing immutable contract: {path}")
        digests[str(path.relative_to(root))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return ContractSnapshot(root, digests)


def verify_snapshot(snapshot: ContractSnapshot) -> None:
    current = load_contract_snapshot(snapshot.root)
    if current.digests != snapshot.digests:
        raise ContractViolation("immutable governance contracts changed")


def enforce(
    snapshot: ContractSnapshot,
    *,
    project_root: str | Path,
    capability: str,
    declared: Iterable[str],
    granted: Iterable[str],
) -> Path:
    verify_snapshot(snapshot)
    root = Path(project_root).resolve()
    if not root.is_dir() or not any(
        root == snapshot.root or snapshot.root in root.parents for _ in (0,)
    ):
        raise ContractViolation("project root is outside the governed root")
    if capability not in set(declared) or capability not in set(granted):
        raise ContractViolation(f"capability not authorized: {capability}")
    return root
