"""Deterministic governance control plane for agent task contracts.

Validates task contracts against:
  1. JSON schema (contracts/agent-task.schema.json)
  2. Governance policy (governance/agent-control-policy.yaml)
  3. Evidence binding requirements

Produces one of five machine-readable statuses:
  ready           – all gates pass; safe to proceed
  blocked         – a hard governance gate fails; human action required before repair
  repair_required – a fixable structural issue was detected; implementer may correct
  awaiting_human  – contract is structurally valid but human judgment is required
  abandoned       – repair budget (3 materially-similar attempts) exhausted; escalate

This validator reports explicitly what it can prove and what remains a human
judgment.  Schema validity is necessary but never sufficient evidence of mission
correctness.

Architecture note: no LLM reasoning, no external daemon, no OAuth, no Docker.
Windows-first operation.  All checks are deterministic.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsonschema
import jsonschema.validators

_REPO_ROOT = Path(__file__).parent.parent.parent
_SCHEMA_PATH = _REPO_ROOT / "contracts" / "agent-task.schema.json"

# Maximum materially-similar repair cycles before the contract is abandoned
# and escalated to the Protomentat (per governance/agent-control-policy.yaml).
MAX_REPAIR_CYCLES: int = 3

# Roles that must not carry write authority.
_NO_WRITE_ROLES: frozenset[str] = frozenset({"reviewer"})

# Roles that must not carry merge authority.
_NO_MERGE_ROLES: frozenset[str] = frozenset({"reviewer", "implementer"})

# Roles that must not carry review authority (they may_not approve own work).
_NO_REVIEW_ROLES: frozenset[str] = frozenset({"implementer"})

# Evidence categories that must be represented in required_evidence for a
# contract to reach 'ready'.  At least one item in required_evidence must
# contain (case-insensitive substring) one of the listed strings in each group.
_EVIDENCE_GROUPS: dict[str, tuple[str, ...]] = {
    "ci/test": ("ci_green", "ci", "test_result", "tests_passed"),
    "review": ("review_result", "review_approved", "reviewed_at_head", "review"),
    "rollback": ("rollback_declaration", "rollback_verified", "rollback"),
}

# Regex for a 40-char lowercase hex SHA (redundant with schema, but allows
# early detailed error messages when the schema check is not conclusive).
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ReadinessStatus(StrEnum):
    """Machine-readable governance readiness status."""

    READY = "ready"
    BLOCKED = "blocked"
    REPAIR_REQUIRED = "repair_required"
    AWAITING_HUMAN = "awaiting_human"
    ABANDONED = "abandoned"


@dataclass
class ValidationResult:
    """Result of a task-contract governance validation.

    Attributes
    ----------
    status:
        One of the five ReadinessStatus values.
    errors:
        Deterministic, actionable error messages.  Non-empty whenever status
        is not READY or AWAITING_HUMAN.
    warnings:
        Advisory messages that do not block readiness.
    provable:
        List of governance properties this validator can confirm
        deterministically.
    unresolvable:
        List of governance properties that require human judgment and cannot
        be determined by this validator.
    repair_count:
        The repair_attempts value this result was computed at.
    """

    status: ReadinessStatus
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provable: list[str] = field(default_factory=list)
    unresolvable: list[str] = field(default_factory=list)
    repair_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for machine-readable output (JSON or CI annotations)."""
        return {
            "status": str(self.status),
            "errors": self.errors,
            "warnings": self.warnings,
            "provable": self.provable,
            "unresolvable": self.unresolvable,
            "repair_count": self.repair_count,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_schema() -> dict[str, Any]:
    """Load the canonical agent-task schema from the repository."""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Agent-task schema not found at {_SCHEMA_PATH}. "
            "Ensure the repository root is intact."
        )
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _schema_errors(contract: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return all JSON Schema validation error messages, or [] if valid."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(contract), key=lambda e: list(e.path))
    return [f"schema: {e.message} (path: {'/'.join(str(p) for p in e.path) or '/'})" for e in errors]


def _check_authority(contract: dict[str, Any]) -> list[str]:
    """Return blocking errors for any role/authority mismatch.

    Deterministically enforces governance/agent-control-policy.yaml rules:
      - reviewer may_not modify_implementation_branch (write=false, merge=false)
      - implementer may_not approve_own_work (review=false)
      - implementer may_not merge_own_work (merge=false)
      - Any role (except final_authority / governor) must not hold write+review
        simultaneously (ambiguous authority – cannot be both implementer and reviewer).
    """
    errors: list[str] = []
    role: str = contract.get("role", "")
    authority: dict[str, Any] = contract.get("authority", {})

    if role in _NO_WRITE_ROLES and authority.get("write"):
        errors.append(
            f"authority_violation: role '{role}' must not claim write authority "
            "(governance/agent-control-policy.yaml: may_not modify_implementation_branch)"
        )
    if role in _NO_MERGE_ROLES and authority.get("merge"):
        errors.append(
            f"authority_violation: role '{role}' must not claim merge authority "
            "(governance/agent-control-policy.yaml: may_not merge_own_work)"
        )
    if role in _NO_REVIEW_ROLES and authority.get("review"):
        errors.append(
            f"authority_violation: role '{role}' must not claim review authority "
            "(governance/agent-control-policy.yaml: may_not approve_own_work)"
        )
    # Ambiguous authority: holding both write and review outside sanctioned roles.
    if role not in ("governor", "final_authority"):
        if authority.get("write") and authority.get("review"):
            errors.append(
                f"ambiguous_authority: role '{role}' claims both write and review "
                "authority simultaneously; these authorities cannot be combined "
                "without Protomentat sanction"
            )
    return errors


def _check_shared_branch(branch_writers: list[str] | None) -> list[str]:
    """Return a blocking error if more than one writer is declared for the branch.

    The governance policy mandates max_writers=1.  branch_writers must be
    supplied by the caller from a branch-protection or PR API query;
    the contract itself does not encode the full writer list.
    """
    if branch_writers is not None and len(branch_writers) > 1:
        quoted = ", ".join(f"'{w}'" for w in branch_writers)
        return [
            f"shared_branch_writers: branch has {len(branch_writers)} writers "
            f"({quoted}); max_writers=1 (governance/agent-control-policy.yaml)"
        ]
    return []


def _check_stale_sha(
    contract: dict[str, Any],
    current_head_sha: str | None,
) -> list[str]:
    """Return a blocking error if the contract's head_sha does not match the
    current HEAD of the branch.

    Stale-SHA evidence is explicitly rejected by governance policy
    (branch_rules.stale_review_after_head_change=true).
    """
    if current_head_sha is None:
        return []
    contract_sha: str = contract.get("head_sha", "")
    if contract_sha != current_head_sha:
        return [
            f"stale_head_sha: contract head_sha '{contract_sha}' does not match "
            f"current HEAD '{current_head_sha}'; review and evidence are stale "
            "(governance/agent-control-policy.yaml: stale_review_after_head_change)"
        ]
    return []


def _check_rollback(contract: dict[str, Any]) -> list[str]:
    """Return repair-required errors if the rollback declaration is incomplete."""
    errors: list[str] = []
    rollback: dict[str, Any] = contract.get("rollback", {})
    if not rollback.get("procedure", "").strip():
        errors.append(
            "missing_rollback: rollback.procedure is empty; "
            "a rollback procedure must be declared"
        )
    if not rollback.get("verified", False):
        errors.append(
            "missing_rollback: rollback.verified is false; "
            "the rollback procedure must be verified before readiness"
        )
    return errors


def _check_evidence(contract: dict[str, Any]) -> list[str]:
    """Return repair-required errors for missing evidence categories.

    Evidence must be bound to mission id, task contract version, head SHA,
    test result, review result, and rollback declaration.
    Schema already enforces minItems=1; this check ensures category coverage.
    """
    errors: list[str] = []
    items: list[str] = [e.lower() for e in contract.get("required_evidence", [])]

    for group_name, keywords in _EVIDENCE_GROUPS.items():
        if not any(kw in item for item in items for kw in keywords):
            errors.append(
                f"missing_evidence: required_evidence contains no item covering "
                f"'{group_name}'; add at least one of: {', '.join(keywords)}"
            )
    return errors


def _build_provable(contract: dict[str, Any]) -> list[str]:
    """Return the list of properties this validator can deterministically confirm."""
    provable: list[str] = []
    provable.append("contract JSON is parseable")
    if contract.get("contract_version") == "1.0.0":
        provable.append("contract_version is 1.0.0")
    if contract.get("mission_id", "").strip():
        provable.append("mission_id is non-empty")
    if _SHA_RE.match(contract.get("head_sha", "")):
        provable.append("head_sha matches 40-char hex format")
    if _SHA_RE.match(contract.get("base_sha", "")):
        provable.append("base_sha matches 40-char hex format")
    if contract.get("rollback", {}).get("verified"):
        provable.append("rollback.verified is true")
    if contract.get("required_evidence"):
        provable.append(
            f"required_evidence has {len(contract['required_evidence'])} item(s)"
        )
    if contract.get("authority", {}).get("read") is True:
        provable.append("authority.read is declared true")
    return provable


_UNRESOLVABLE: list[str] = [
    "whether mission objective is actually achieved",
    "whether evidence content is accurate (only presence is checked)",
    "whether the rollback procedure is operationally correct",
    "whether the reviewer is genuinely independent of the implementation",
    "whether CI was run against the exact committed code at head_sha",
    "whether tenth_man_countercase constitutes a genuine dissent",
    "whether acceptance criteria reflect actual mission success",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_task_contract(
    contract: dict[str, Any],
    *,
    current_head_sha: str | None = None,
    branch_writers: list[str] | None = None,
    repair_attempts: int = 0,
    schema: dict[str, Any] | None = None,
) -> ValidationResult:
    """Deterministically validate a task contract against the governance policy.

    Parameters
    ----------
    contract:
        Parsed task contract (dict from JSON).
    current_head_sha:
        If provided, the actual current HEAD SHA of the branch.  Used to detect
        stale evidence.  None means the caller cannot supply it and the check
        is skipped (a warning is emitted instead).
    branch_writers:
        If provided, the list of GitHub usernames with write access to the
        branch.  Used to enforce max_writers=1.  None skips the check.
    repair_attempts:
        The number of materially-similar failed repair attempts so far.
        When >= MAX_REPAIR_CYCLES (3), the contract is immediately abandoned
        and escalated to the Protomentat.
    schema:
        Override the schema to load (for testing).  If None, the canonical
        schema is loaded from contracts/agent-task.schema.json.

    Returns
    -------
    ValidationResult
        Contains status, errors, warnings, provable facts, and unresolvable
        human-judgment items.
    """
    # --- Repair budget check (overrides all other status) ---
    if repair_attempts >= MAX_REPAIR_CYCLES:
        return ValidationResult(
            status=ReadinessStatus.ABANDONED,
            errors=[
                f"repair_budget_exhausted: {repair_attempts} materially-similar "
                f"repair attempt(s) have failed (maximum is {MAX_REPAIR_CYCLES}); "
                "escalate to Protomentat for human judgment"
            ],
            unresolvable=_UNRESOLVABLE,
            repair_count=repair_attempts,
        )

    if schema is None:
        schema = _load_schema()

    blocking_errors: list[str] = []
    repair_errors: list[str] = []
    warnings: list[str] = []

    # --- 1. JSON Schema validation ---
    schema_errs = _schema_errors(contract, schema)
    blocking_errors.extend(schema_errs)

    # Authority checks always run so that explicit authority_violation messages
    # appear even when the allOf schema constraint already flags the same issue.
    # --- 2. Authority and role checks ---
    blocking_errors.extend(_check_authority(contract))

    # Skip deeper checks when schema is fundamentally broken to avoid false
    # positives from partially-formed contracts.
    if not schema_errs:
        # --- 3. Shared branch ownership ---
        blocking_errors.extend(_check_shared_branch(branch_writers))

        # --- 4. Stale head SHA ---
        blocking_errors.extend(_check_stale_sha(contract, current_head_sha))

        # --- 5. Rollback declaration ---
        # missing_rollback is a governance halt trigger; treated as blocking.
        blocking_errors.extend(_check_rollback(contract))

        # --- 6. Evidence binding ---
        repair_errors.extend(_check_evidence(contract))

    # --- Stale SHA check warning when sha is not supplied ---
    if current_head_sha is None and not schema_errs:
        warnings.append(
            "stale_sha_unverifiable: current_head_sha was not supplied; "
            "stale-SHA check skipped – supply HEAD SHA for full enforcement"
        )
    if branch_writers is None and not schema_errs:
        warnings.append(
            "shared_branch_unverifiable: branch_writers was not supplied; "
            "shared-branch check skipped – supply writer list for full enforcement"
        )

    # --- Build provable list ---
    provable = _build_provable(contract) if not schema_errs else ["contract JSON is parseable"]

    # --- Determine status ---
    if blocking_errors:
        status = ReadinessStatus.BLOCKED
    elif repair_errors:
        status = ReadinessStatus.REPAIR_REQUIRED
    elif contract.get("human_approval_required", False):
        status = ReadinessStatus.AWAITING_HUMAN
    else:
        status = ReadinessStatus.READY

    all_errors = blocking_errors + repair_errors
    return ValidationResult(
        status=status,
        errors=all_errors,
        warnings=warnings,
        provable=provable,
        unresolvable=_UNRESOLVABLE,
        repair_count=repair_attempts,
    )


def validate_task_contract_file(
    path: str | Path,
    *,
    current_head_sha: str | None = None,
    branch_writers: list[str] | None = None,
    repair_attempts: int = 0,
) -> ValidationResult:
    """Load a JSON file and validate it as a task contract.

    Wraps validate_task_contract() with file I/O so callers (scripts,
    CI steps) do not need to handle JSON parsing.
    """
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as fh:
            contract = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return ValidationResult(
            status=ReadinessStatus.BLOCKED,
            errors=[f"file_error: could not load contract from '{path}': {exc}"],
            unresolvable=_UNRESOLVABLE,
        )
    return validate_task_contract(
        contract,
        current_head_sha=current_head_sha,
        branch_writers=branch_writers,
        repair_attempts=repair_attempts,
    )
