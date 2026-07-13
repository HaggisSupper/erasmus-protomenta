"""Tests for the governance control plane (Issue #17).

Coverage:
- Valid contract produces 'ready'.
- Invalid JSON schema produces 'blocked'.
- Reviewer with write authority produces 'blocked'.
- Implementer with review authority produces 'blocked' (ambiguous authority).
- Implementer with both write and review produces 'blocked' (ambiguous authority).
- Shared branch ownership (multiple writers) produces 'blocked'.
- Stale head SHA produces 'blocked'.
- Missing rollback procedure/verification produces 'repair_required'.
- Missing required evidence categories produces 'repair_required'.
- Retry budget exhaustion (>= 3 attempts) produces 'abandoned'.
- human_approval_required=True produces 'awaiting_human'.
- ValidationResult.to_dict() is machine-readable.
- Fixture files load and validate correctly.
- Provable and unresolvable lists are non-empty.
- Schema validity is necessary but not sufficient (schema-valid but governance-invalid cases).
- Windows PowerShell validation script exists.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from erasmus.governance import (
    MAX_REPAIR_CYCLES,
    ReadinessStatus,
    ValidationResult,
    validate_task_contract,
    validate_task_contract_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent.parent / "contracts" / "fixtures"

_VALID_SHA_A = "a" * 40
_VALID_SHA_B = "b" * 40
_VALID_SHA_C = "c" * 40


def _minimal_valid() -> dict[str, Any]:
    """Return the smallest contract that passes all governance checks."""
    return {
        "contract_version": "1.0.0",
        "mission_id": "test-mission-01",
        "issue_number": 17,
        "role": "implementer",
        "agent": "test-agent",
        "branch": "test/branch",
        "base_sha": _VALID_SHA_A,
        "head_sha": _VALID_SHA_B,
        "authority": {
            "read": True,
            "write": True,
            "review": False,
            "merge": False,
        },
        "allowed_paths": ["src/"],
        "prohibited_actions": ["merge_own_work"],
        "required_evidence": [
            "ci_green: all tests pass",
            "test_result: all tests pass",
            "review_result: approved at head",
            "rollback_declaration: revert commits",
        ],
        "rollback": {
            "procedure": "git revert HEAD",
            "verified": True,
        },
        "tenth_man_countercase": "The strongest objection to this change is...",
        "human_approval_required": False,
    }


# ---------------------------------------------------------------------------
# Valid contract
# ---------------------------------------------------------------------------


class TestValidContract:
    def test_valid_contract_is_ready(self):
        result = validate_task_contract(_minimal_valid())
        assert result.status == ReadinessStatus.READY

    def test_valid_contract_has_no_errors(self):
        result = validate_task_contract(_minimal_valid())
        assert result.errors == []

    def test_valid_contract_has_provable_items(self):
        result = validate_task_contract(_minimal_valid())
        assert len(result.provable) > 0

    def test_valid_contract_has_unresolvable_items(self):
        """Validator must always declare what it cannot prove."""
        result = validate_task_contract(_minimal_valid())
        assert len(result.unresolvable) > 0

    def test_valid_contract_to_dict_has_required_keys(self):
        result = validate_task_contract(_minimal_valid())
        d = result.to_dict()
        assert d["status"] == "ready"
        for key in ("errors", "warnings", "provable", "unresolvable", "repair_count"):
            assert key in d

    def test_valid_sha_format_confirmed_in_provable(self):
        result = validate_task_contract(_minimal_valid())
        assert any("head_sha" in p for p in result.provable)

    def test_valid_contract_repair_count_is_zero(self):
        result = validate_task_contract(_minimal_valid())
        assert result.repair_count == 0

    def test_valid_contract_with_head_sha_check(self):
        contract = _minimal_valid()
        result = validate_task_contract(
            contract,
            current_head_sha=_VALID_SHA_B,
        )
        assert result.status == ReadinessStatus.READY

    def test_valid_contract_with_single_branch_writer(self):
        result = validate_task_contract(
            _minimal_valid(),
            branch_writers=["test-agent"],
        )
        assert result.status == ReadinessStatus.READY


# ---------------------------------------------------------------------------
# JSON Schema violations → blocked
# ---------------------------------------------------------------------------


class TestSchemaViolations:
    def test_missing_required_field_is_blocked(self):
        contract = _minimal_valid()
        del contract["mission_id"]
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("schema" in e for e in result.errors)

    def test_invalid_contract_version_is_blocked(self):
        contract = _minimal_valid()
        contract["contract_version"] = "2.0.0"
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_invalid_sha_format_is_blocked(self):
        contract = _minimal_valid()
        contract["head_sha"] = "not-a-sha"
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_invalid_role_is_blocked(self):
        contract = _minimal_valid()
        contract["role"] = "superuser"
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_empty_allowed_paths_is_blocked(self):
        contract = _minimal_valid()
        contract["allowed_paths"] = []
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_empty_prohibited_actions_is_blocked(self):
        contract = _minimal_valid()
        contract["prohibited_actions"] = []
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_additional_property_is_blocked(self):
        contract = _minimal_valid()
        contract["unexpected_field"] = "oops"
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_missing_rollback_block_is_blocked(self):
        contract = _minimal_valid()
        del contract["rollback"]
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED


# ---------------------------------------------------------------------------
# Reviewer write authority → blocked
# ---------------------------------------------------------------------------


class TestReviewerWriteRejection:
    """Governance policy: reviewer may_not modify_implementation_branch."""

    def test_reviewer_with_write_true_is_blocked(self):
        contract = _minimal_valid()
        contract["role"] = "reviewer"
        contract["authority"]["write"] = True
        contract["authority"]["merge"] = False
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("authority_violation" in e for e in result.errors)

    def test_reviewer_with_merge_true_is_blocked(self):
        contract = _minimal_valid()
        contract["role"] = "reviewer"
        contract["authority"]["write"] = False
        contract["authority"]["merge"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("authority_violation" in e for e in result.errors)

    def test_reviewer_with_write_and_merge_true_is_blocked(self):
        contract = _minimal_valid()
        contract["role"] = "reviewer"
        contract["authority"]["write"] = True
        contract["authority"]["merge"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_reviewer_with_only_read_and_review_is_allowed(self):
        """A reviewer may hold read=True, review=True."""
        contract = _minimal_valid()
        contract["role"] = "reviewer"
        contract["authority"]["write"] = False
        contract["authority"]["merge"] = False
        contract["authority"]["review"] = True
        result = validate_task_contract(contract)
        # Should not be blocked by authority checks (only blocked if schema fails)
        blocking_authority = [e for e in result.errors if "authority_violation" in e]
        assert blocking_authority == []

    def test_fixture_reviewer_write_is_blocked(self):
        result = validate_task_contract_file(_FIXTURES / "invalid_reviewer_write.json")
        assert result.status == ReadinessStatus.BLOCKED


# ---------------------------------------------------------------------------
# Ambiguous authority → blocked
# ---------------------------------------------------------------------------


class TestAmbiguousAuthorityRejection:
    """Governance policy: ambiguous_authority is a halt trigger."""

    def test_implementer_with_review_authority_is_blocked(self):
        """Implementer may_not approve_own_work; review authority is disallowed."""
        contract = _minimal_valid()
        contract["role"] = "implementer"
        contract["authority"]["review"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("authority_violation" in e for e in result.errors)

    def test_implementer_with_write_and_review_is_blocked(self):
        """Both authority_violation and ambiguous_authority detected."""
        contract = _minimal_valid()
        contract["role"] = "implementer"
        contract["authority"]["write"] = True
        contract["authority"]["review"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any(
            "authority_violation" in e or "ambiguous_authority" in e
            for e in result.errors
        )

    def test_implementer_with_merge_authority_is_blocked(self):
        """Implementer may_not merge_own_work."""
        contract = _minimal_valid()
        contract["role"] = "implementer"
        contract["authority"]["merge"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("authority_violation" in e for e in result.errors)

    def test_fixture_ambiguous_authority_is_blocked(self):
        result = validate_task_contract_file(_FIXTURES / "invalid_ambiguous_authority.json")
        assert result.status == ReadinessStatus.BLOCKED

    def test_final_authority_may_hold_write_and_review(self):
        """final_authority role is exempt from the ambiguous-authority check."""
        contract = _minimal_valid()
        contract["role"] = "final_authority"
        contract["authority"]["write"] = True
        contract["authority"]["review"] = True
        contract["authority"]["merge"] = True
        result = validate_task_contract(contract)
        ambiguous = [e for e in result.errors if "ambiguous_authority" in e]
        assert ambiguous == []


# ---------------------------------------------------------------------------
# Shared branch ownership → blocked
# ---------------------------------------------------------------------------


class TestSharedBranchOwnershipRejection:
    """Governance policy: max_writers=1."""

    def test_two_writers_is_blocked(self):
        result = validate_task_contract(
            _minimal_valid(),
            branch_writers=["agent-a", "agent-b"],
        )
        assert result.status == ReadinessStatus.BLOCKED
        assert any("shared_branch_writers" in e for e in result.errors)

    def test_three_writers_is_blocked(self):
        result = validate_task_contract(
            _minimal_valid(),
            branch_writers=["agent-a", "agent-b", "agent-c"],
        )
        assert result.status == ReadinessStatus.BLOCKED

    def test_one_writer_is_not_blocked(self):
        result = validate_task_contract(
            _minimal_valid(),
            branch_writers=["agent-a"],
        )
        # shared branch check passes with single writer
        shared = [e for e in result.errors if "shared_branch_writers" in e]
        assert shared == []

    def test_no_writers_supplied_emits_warning_not_error(self):
        result = validate_task_contract(_minimal_valid(), branch_writers=None)
        assert not any("shared_branch_writers" in e for e in result.errors)
        assert any("shared_branch_unverifiable" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Stale head SHA → blocked
# ---------------------------------------------------------------------------


class TestStaleSHARejection:
    """Governance policy: stale_review_after_head_change=true."""

    def test_mismatched_head_sha_is_blocked(self):
        contract = _minimal_valid()
        # Contract says SHA_B; actual HEAD is SHA_C
        result = validate_task_contract(
            contract,
            current_head_sha=_VALID_SHA_C,
        )
        assert result.status == ReadinessStatus.BLOCKED
        assert any("stale_head_sha" in e for e in result.errors)

    def test_matching_head_sha_passes(self):
        contract = _minimal_valid()
        result = validate_task_contract(
            contract,
            current_head_sha=_VALID_SHA_B,  # matches contract["head_sha"]
        )
        stale = [e for e in result.errors if "stale_head_sha" in e]
        assert stale == []

    def test_no_head_sha_supplied_emits_warning_not_error(self):
        result = validate_task_contract(_minimal_valid(), current_head_sha=None)
        assert not any("stale_head_sha" in e for e in result.errors)
        assert any("stale_sha_unverifiable" in w for w in result.warnings)

    def test_fixture_stale_sha_is_blocked(self):
        result = validate_task_contract_file(
            _FIXTURES / "valid_task_for_stale_sha.json",
            current_head_sha=_VALID_SHA_C,  # deliberately different from fixture head_sha
        )
        assert result.status == ReadinessStatus.BLOCKED
        assert any("stale_head_sha" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing rollback → repair_required
# ---------------------------------------------------------------------------


class TestMissingRollbackRejection:
    """Governance policy: missing_rollback is a halt trigger (→ blocked)."""

    def test_rollback_not_verified_is_blocked(self):
        contract = _minimal_valid()
        contract["rollback"]["verified"] = False
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("missing_rollback" in e for e in result.errors)

    def test_empty_rollback_procedure_is_blocked(self):
        """Empty procedure fails schema (minLength=1) → blocked."""
        contract = _minimal_valid()
        contract["rollback"]["procedure"] = ""
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_whitespace_only_rollback_procedure_is_blocked(self):
        """Whitespace-only procedure passes schema but fails governance → blocked."""
        contract = _minimal_valid()
        contract["rollback"]["procedure"] = "   "
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_fixture_missing_rollback_is_blocked(self):
        result = validate_task_contract_file(_FIXTURES / "invalid_missing_rollback.json")
        assert result.status == ReadinessStatus.BLOCKED
        assert any("missing_rollback" in e for e in result.errors)

    def test_verified_rollback_with_procedure_passes(self):
        contract = _minimal_valid()
        contract["rollback"]["verified"] = True
        contract["rollback"]["procedure"] = "git revert HEAD"
        result = validate_task_contract(contract)
        assert not any("missing_rollback" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing required evidence → repair_required
# ---------------------------------------------------------------------------


class TestMissingEvidenceRejection:
    """Evidence must be bound to CI, review, and rollback categories."""

    def test_empty_evidence_list_is_blocked_by_schema(self):
        """Schema enforces minItems=1; empty list → blocked, not repair_required."""
        contract = _minimal_valid()
        contract["required_evidence"] = []
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.BLOCKED

    def test_evidence_missing_ci_is_repair_required(self):
        contract = _minimal_valid()
        contract["required_evidence"] = [
            "review_result: approved",
            "rollback_declaration: revert commits",
        ]
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.REPAIR_REQUIRED
        assert any("missing_evidence" in e and "ci/test" in e for e in result.errors)

    def test_evidence_missing_review_is_repair_required(self):
        contract = _minimal_valid()
        contract["required_evidence"] = [
            "ci_green: all tests pass",
            "rollback_declaration: revert commits",
        ]
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.REPAIR_REQUIRED
        assert any("missing_evidence" in e and "review" in e for e in result.errors)

    def test_evidence_missing_rollback_declaration_is_repair_required(self):
        contract = _minimal_valid()
        contract["required_evidence"] = [
            "ci_green: all tests pass",
            "review_result: approved",
        ]
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.REPAIR_REQUIRED
        assert any("missing_evidence" in e and "rollback" in e for e in result.errors)

    def test_fixture_missing_evidence_is_repair_required(self):
        result = validate_task_contract_file(_FIXTURES / "invalid_missing_evidence.json")
        assert result.status == ReadinessStatus.REPAIR_REQUIRED

    def test_all_evidence_categories_present_passes(self):
        contract = _minimal_valid()
        result = validate_task_contract(contract)
        assert not any("missing_evidence" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Retry budget exhaustion → abandoned
# ---------------------------------------------------------------------------


class TestRetryBudgetExhaustion:
    """After MAX_REPAIR_CYCLES materially-similar failures, status is abandoned."""

    def test_exactly_max_attempts_is_abandoned(self):
        result = validate_task_contract(
            _minimal_valid(),
            repair_attempts=MAX_REPAIR_CYCLES,
        )
        assert result.status == ReadinessStatus.ABANDONED

    def test_below_max_attempts_is_not_abandoned(self):
        result = validate_task_contract(
            _minimal_valid(),
            repair_attempts=MAX_REPAIR_CYCLES - 1,
        )
        assert result.status != ReadinessStatus.ABANDONED

    def test_above_max_attempts_is_abandoned(self):
        result = validate_task_contract(
            _minimal_valid(),
            repair_attempts=MAX_REPAIR_CYCLES + 5,
        )
        assert result.status == ReadinessStatus.ABANDONED

    def test_abandoned_includes_escalation_message(self):
        result = validate_task_contract(
            _minimal_valid(),
            repair_attempts=MAX_REPAIR_CYCLES,
        )
        assert any("repair_budget_exhausted" in e for e in result.errors)
        assert any("Protomentat" in e for e in result.errors)

    def test_abandoned_overrides_blocking_errors(self):
        """Even a broken contract is abandoned (not blocked) when budget is gone."""
        contract = _minimal_valid()
        del contract["mission_id"]
        result = validate_task_contract(
            contract,
            repair_attempts=MAX_REPAIR_CYCLES,
        )
        assert result.status == ReadinessStatus.ABANDONED

    def test_repair_count_is_recorded_in_result(self):
        attempts = 2
        result = validate_task_contract(
            _minimal_valid(),
            repair_attempts=attempts,
        )
        assert result.repair_count == attempts

    def test_max_repair_cycles_constant_is_three(self):
        """Governance policy specifies exactly 3 materially-similar repair cycles."""
        assert MAX_REPAIR_CYCLES == 3


# ---------------------------------------------------------------------------
# Human approval gate → awaiting_human
# ---------------------------------------------------------------------------


class TestAwaitingHuman:
    def test_human_approval_required_true_produces_awaiting_human(self):
        contract = _minimal_valid()
        contract["human_approval_required"] = True
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.AWAITING_HUMAN

    def test_human_approval_false_does_not_block(self):
        contract = _minimal_valid()
        contract["human_approval_required"] = False
        result = validate_task_contract(contract)
        assert result.status == ReadinessStatus.READY


# ---------------------------------------------------------------------------
# Evidence binding
# ---------------------------------------------------------------------------


class TestEvidenceBinding:
    """Validator confirms evidence is bound to required governance properties."""

    def test_mission_id_confirmed_as_provable(self):
        result = validate_task_contract(_minimal_valid())
        assert any("mission_id" in p for p in result.provable)

    def test_head_sha_format_confirmed_as_provable(self):
        result = validate_task_contract(_minimal_valid())
        assert any("head_sha" in p for p in result.provable)

    def test_rollback_verified_confirmed_as_provable(self):
        result = validate_task_contract(_minimal_valid())
        assert any("rollback.verified" in p for p in result.provable)

    def test_contract_version_confirmed_as_provable(self):
        result = validate_task_contract(_minimal_valid())
        assert any("contract_version" in p for p in result.provable)

    def test_unresolvable_includes_mission_correctness(self):
        result = validate_task_contract(_minimal_valid())
        assert any("mission objective" in u for u in result.unresolvable)

    def test_unresolvable_includes_ci_accuracy(self):
        result = validate_task_contract(_minimal_valid())
        assert any("CI" in u for u in result.unresolvable)

    def test_unresolvable_includes_reviewer_independence(self):
        result = validate_task_contract(_minimal_valid())
        assert any("reviewer" in u for u in result.unresolvable)


# ---------------------------------------------------------------------------
# Schema validity is not sufficient
# ---------------------------------------------------------------------------


class TestSchemaNotSufficient:
    """A schema-valid contract can still be governance-invalid."""

    def test_schema_valid_but_missing_evidence_categories_not_ready(self):
        """Contract passes JSON schema but lacks required evidence categories."""
        contract = _minimal_valid()
        contract["required_evidence"] = ["scope_respected: changes within allowed_paths"]
        result = validate_task_contract(contract)
        # Schema check passes (minItems=1), but governance check fails
        schema_errors = [e for e in result.errors if e.startswith("schema:")]
        assert schema_errors == [], f"Unexpected schema errors: {schema_errors}"
        assert result.status != ReadinessStatus.READY

    def test_schema_valid_but_rollback_unverified_not_ready(self):
        contract = _minimal_valid()
        contract["rollback"]["verified"] = False
        result = validate_task_contract(contract)
        schema_errors = [e for e in result.errors if e.startswith("schema:")]
        assert schema_errors == []
        assert result.status != ReadinessStatus.READY


# ---------------------------------------------------------------------------
# Fixture file loading
# ---------------------------------------------------------------------------


class TestFixtureFiles:
    def test_valid_fixture_is_ready(self):
        result = validate_task_contract_file(_FIXTURES / "valid_task.json")
        assert result.status == ReadinessStatus.READY

    def test_nonexistent_file_is_blocked(self):
        result = validate_task_contract_file(_FIXTURES / "does_not_exist.json")
        assert result.status == ReadinessStatus.BLOCKED
        assert any("file_error" in e for e in result.errors)

    def test_invalid_json_file_is_blocked(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("this is not json", encoding="utf-8")
        result = validate_task_contract_file(bad)
        assert result.status == ReadinessStatus.BLOCKED
        assert any("file_error" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Windows PowerShell validation script exists
# ---------------------------------------------------------------------------


class TestWindowsPowerShellScript:
    """Verify that the Windows PowerShell validation script is present and correct."""

    _SCRIPT = Path(__file__).parent.parent / "scripts" / "validate_contract.ps1"

    def test_powershell_script_exists(self):
        assert self._SCRIPT.exists(), (
            f"Windows PowerShell validation script not found at {self._SCRIPT}; "
            "required for Windows-first operation"
        )

    def test_powershell_script_references_validator(self):
        content = self._SCRIPT.read_text(encoding="utf-8")
        assert "validate_contract" in content.lower(), (
            "PowerShell script must reference validate_contract"
        )

    def test_powershell_script_references_status(self):
        content = self._SCRIPT.read_text(encoding="utf-8")
        assert "status" in content.lower(), (
            "PowerShell script must display governance status"
        )

    def test_python_cli_script_exists(self):
        cli = Path(__file__).parent.parent / "scripts" / "validate_contract.py"
        assert cli.exists(), (
            f"Python CLI validation script not found at {cli}"
        )


class TestImmutableContract:
    _ROOT = Path(__file__).parent.parent
    _CONTRACT = _ROOT / "constitution" / "immutable-contract.md"

    def test_canonical_governance_paths_use_exact_case(self):
        assert "immutable-contract.md" in {
            path.name for path in (self._ROOT / "constitution").iterdir()
        }
        assert "architecture.md" in {
            path.name for path in (self._ROOT / "docs").iterdir()
        }

    def test_required_immutable_invariants_are_present(self):
        content = self._CONTRACT.read_text(encoding="utf-8")
        required = (
            "## Epistemic integrity",
            "## Authority and dissent",
            "## Persistence and promotion",
            "## Capability and operation",
            "## Provenance and reversibility",
            "Evidence outranks confidence and agreement.",
            "The Protomentat retains final authority over consequential ambiguity.",
            "remain logically separate",
            "Every capability declares typed input and output",
            "one process and one SQLite database",
            "Windows-first operation is required. No Docker.",
            "independent dissent, provenance, or human sovereignty",
        )
        missing = [clause for clause in required if clause not in content]
        assert not missing, f"immutable contract is missing required clauses: {missing}"
