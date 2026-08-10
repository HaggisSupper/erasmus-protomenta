from __future__ import annotations

from pathlib import Path

import pytest

from erasmus.contract_enforcer import ContractEnforcer, ContractViolation, contract_hash


def test_contract_hash_stable_for_different_key_order():
    assert contract_hash({"b": 1, "a": 2}) == contract_hash({"a": 2, "b": 1})


def test_enforcer_requires_matching_snapshot_and_authorized_capability(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    contract = {"capabilities": ["read", "write"]}
    snapshot = contract_hash(contract)
    enforcer = ContractEnforcer(contract, allowed_roots=(str(tmp_path),))
    enforcer.enforce(snapshot=snapshot, root=str(root), capability="read", granted=("read",))
    assert enforcer.check_root(str(root)) == root


def test_enforcer_rejects_missing_or_wrong_snapshot(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    contract = {"capabilities": ["read"]}
    enforcer = ContractEnforcer(contract, allowed_roots=(str(tmp_path),))
    with pytest.raises(ContractViolation, match="snapshot mismatch"):
        enforcer.enforce(snapshot="not-a-match", root=str(root), capability="read", granted=("read",))


def test_enforcer_rejects_unknown_capability_and_bad_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    contract = {"allowed_capabilities": ["write"]}
    enforcer = ContractEnforcer(contract, allowed_roots=(str(root),))
    with pytest.raises(ContractViolation, match="not authorized"):
        enforcer.enforce(snapshot=contract_hash(contract), root=str(root), capability="read", granted=("write",))
    with pytest.raises(ContractViolation, match="outside the allowed roots"):
        enforcer.enforce(snapshot=contract_hash(contract), root=str(tmp_path / "outside"), capability="write", granted=("write",))


def test_enforcer_requires_configured_allowed_roots():
    enforcer = ContractEnforcer({"allowed_capabilities": []})
    with pytest.raises(ContractViolation, match="no allowed roots configured"):
        enforcer.check_root("C:\\")

