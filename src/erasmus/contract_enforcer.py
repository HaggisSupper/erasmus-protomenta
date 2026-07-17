"""Fail-closed enforcement for immutable Erasmus governance contracts."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

class ContractViolation(ValueError): pass

@dataclass(frozen=True)
class ContractSnapshot:
    root: Path
    digests: dict[str, str]

def _files(root: Path) -> tuple[Path, ...]:
    return (root / "constitution" / "immutable-contract.md", root / "governance" / "agent-control-policy.yaml")

def load_contract_snapshot(root: str | Path) -> ContractSnapshot:
    root = Path(root).resolve()
    digests: dict[str, str] = {}
    for path in _files(root):
        if not path.is_file(): raise ContractViolation(f"missing immutable contract: {path}")
        digests[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return ContractSnapshot(root, digests)

def verify_snapshot(snapshot: ContractSnapshot) -> None:
    current = load_contract_snapshot(snapshot.root)
    if current.digests != snapshot.digests: raise ContractViolation("immutable governance contracts changed")

def enforce(snapshot: ContractSnapshot, *, project_root: str | Path, capability: str,
            declared: Iterable[str], granted: Iterable[str]) -> Path:
    verify_snapshot(snapshot)
    root = Path(project_root).resolve()
    if not root.is_dir() or not any(root == snapshot.root or snapshot.root in root.parents for _ in (0,)):
        raise ContractViolation("project root is outside the governed root")
    if capability not in set(declared) or capability not in set(granted):
        raise ContractViolation(f"capability not authorized: {capability}")
    return root
