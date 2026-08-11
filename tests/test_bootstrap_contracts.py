"""Tests for bootstrap control-plane contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from erasmus.bootstrap_contracts import (
    KNOWN_STATES,
    validate_bootstrap_contract_file,
    validate_bootstrap_contract_payload,
)


ROOT = Path(__file__).parent.parent
SCHEMA_DIR = ROOT / "contracts" / "bootstrap"
FIXTURES = SCHEMA_DIR / "fixtures"
SCHEMA_FILES = (
    "component-spec.schema.json",
    "bootstrap-plan.schema.json",
    "service-observation.schema.json",
    "recovery-decision.schema.json",
    "bootstrap-result.schema.json",
)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_all_bootstrap_schemas_are_draft202012_compatible():
    for schema_file in SCHEMA_FILES:
        schema_path = SCHEMA_DIR / schema_file
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_valid_minimal_windows_fixture_passes():
    result = validate_bootstrap_contract_file(FIXTURES / "valid-minimal-windows.json")
    assert result.ok is True
    assert result.errors == ()
    assert result.derived_startup_order == (
        "sqlite-store",
        "erasmus-mcp",
        "mistral-rs",
        "llama-cpp",
        "headless-router",
    )
    assert result.derived_shutdown_order == (
        "headless-router",
        "llama-cpp",
        "mistral-rs",
        "erasmus-mcp",
        "sqlite-store",
    )


def test_duplicate_component_id_rejected():
    result = validate_bootstrap_contract_file(FIXTURES / "invalid-duplicate-component-id.json")
    assert result.ok is False
    assert any("duplicate IDs" in error for error in result.errors)


def test_dependency_cycle_rejected():
    result = validate_bootstrap_contract_file(FIXTURES / "invalid-dependency-cycle.json")
    assert result.ok is False
    assert any("dependency cycle" in error for error in result.errors)


def test_lifecycle_state_transitions_are_valid():
    payload = _load_fixture("valid-minimal-windows.json")
    result = validate_bootstrap_contract_payload(payload)
    assert result.ok is True
    for state in ("discovery", "starting", "running", "stopping", "stopped", "exited", "orphaned"):
        assert state in KNOWN_STATES


def test_mistral_is_primary_with_authorized_override_logic():
    payload = _load_fixture("valid-minimal-windows.json")
    result = validate_bootstrap_contract_payload(payload)
    assert result.ok is True
    assert any("runtime_policy" in warning for warning in result.warnings) is False


def test_recovery_action_requires_owned_process_evidence():
    payload = _load_fixture("valid-minimal-windows.json")
    payload["recovery_decisions"][0]["permitted_actions"] = ["stop_owned_process"]
    payload["recovery_decisions"][0]["ownership"]["status"] = "unknown"
    result = validate_bootstrap_contract_payload(payload)
    assert result.ok is False
    assert any("restart/stop is only allowed for owned process" in error for error in result.errors)


def test_recovery_decision_with_blocked_missing_reason_is_rejected():
    payload = _load_fixture("valid-minimal-windows.json")
    payload["recovery_decisions"][0]["classification"] = "blocked"
    payload["recovery_decisions"][0]["blocked_reason"] = ""
    result = validate_bootstrap_contract_payload(payload)
    assert result.ok is False
    assert any("blocked_reason" in error for error in result.errors)


def test_bootstrap_plan_dependency_graph_declared_matches_components():
    payload = _load_fixture("valid-minimal-windows.json")
    bad = copy.deepcopy(payload)
    bad["plan"]["required_components"].append("unknown-component")
    result = validate_bootstrap_contract_payload(bad)
    assert result.ok is False
    assert any("unknown component reference" in error for error in result.errors)


@pytest.mark.parametrize(
    "fixture",
    [
        "invalid-dependency-cycle.json",
        "invalid-duplicate-component-id.json",
    ],
)
def test_invalid_fixtures_fail(fixture):
    result = validate_bootstrap_contract_file(FIXTURES / fixture)
    assert result.ok is False
