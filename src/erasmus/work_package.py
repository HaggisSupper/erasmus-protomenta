"""Typed worker handoff/state packet."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json

@dataclass(frozen=True)
class WorkPackage:
    package_id: str
    actor: str
    scope: str
    contract_snapshot: str
    files: tuple[str, ...]
    tests: tuple[str, ...]
    status: str = "proposed"
    rollback: str = ""
    def to_json(self) -> str: return json.dumps(asdict(self), sort_keys=True)
    def with_status(self, status: str) -> "WorkPackage": return WorkPackage(self.package_id, self.actor, self.scope, self.contract_snapshot, self.files, self.tests, status, self.rollback)
