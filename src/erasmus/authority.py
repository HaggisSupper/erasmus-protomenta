"""Deterministic actor/operation/scope authority decisions."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum

class AuthorityDecision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"

@dataclass(frozen=True)
class AuthorityResult:
    actor: str
    operation: str
    scope: str
    decision: AuthorityDecision
    reason: str

def decide(actor: str, operation: str, scope: str, rules: list[dict]) -> AuthorityResult:
    matches = [r for r in rules if (r.get("actor") in {actor, "*"}) and (r.get("operation") in {operation, "*"}) and (r.get("scope") in {scope, "*"})]
    for rule in matches:
        if rule.get("effect") == "deny": return AuthorityResult(actor, operation, scope, AuthorityDecision.DENIED, rule.get("reason", "Denied by policy"))
    for rule in matches:
        if rule.get("requiresHumanApproval"): return AuthorityResult(actor, operation, scope, AuthorityDecision.REQUIRES_HUMAN_APPROVAL, rule.get("reason", "Human approval required"))
    for rule in matches:
        if rule.get("effect") == "allow": return AuthorityResult(actor, operation, scope, AuthorityDecision.ALLOWED, rule.get("reason", "Allowed by policy"))
    return AuthorityResult(actor, operation, scope, AuthorityDecision.DENIED, "No matching allow rule")
