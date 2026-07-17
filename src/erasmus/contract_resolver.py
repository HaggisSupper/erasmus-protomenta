"""Deterministic, fail-safe resolution for contract conflicts."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class Resolution(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    QUARANTINE = "quarantine"
    HALT = "halt"

@dataclass(frozen=True)
class ContractDecision:
    resolution: Resolution
    reason: str
    retryable: bool = False

def resolve(*, conflict: str, attempts: int = 0, max_attempts: int = 3) -> ContractDecision:
    """Resolve without throwing; immutable-contract violations always win."""
    if conflict in {"contract_mutated", "contract_missing", "stale_sha"}:
        return ContractDecision(Resolution.HALT, conflict)
    if conflict in {"malformed_request", "path_escape", "unauthorized_capability"}:
        return ContractDecision(Resolution.DENY, conflict)
    if conflict in {"worker_timeout", "worker_crash", "deadlock"}:
        if attempts < max_attempts:
            return ContractDecision(Resolution.QUARANTINE, conflict, retryable=True)
        return ContractDecision(Resolution.HALT, f"{conflict}: retry limit exceeded")
    return ContractDecision(Resolution.DENY, f"unknown conflict: {conflict}")
