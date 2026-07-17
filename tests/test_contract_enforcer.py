from pathlib import Path
import pytest
from erasmus.contract_enforcer import ContractViolation, enforce, load_contract_snapshot, verify_snapshot

def test_snapshot_detects_mutation(tmp_path: Path):
    (tmp_path / "constitution").mkdir(); (tmp_path / "governance").mkdir()
    (tmp_path / "constitution" / "immutable-contract.md").write_text("contract")
    (tmp_path / "governance" / "agent-control-policy.yaml").write_text("version: 1")
    snap = load_contract_snapshot(tmp_path)
    verify_snapshot(snap)
    (tmp_path / "governance" / "agent-control-policy.yaml").write_text("version: 2")
    with pytest.raises(ContractViolation): verify_snapshot(snap)

def test_enforce_rejects_unauthorized(tmp_path: Path):
    (tmp_path / "constitution").mkdir(); (tmp_path / "governance").mkdir()
    for path in (tmp_path / "constitution" / "immutable-contract.md", tmp_path / "governance" / "agent-control-policy.yaml"): path.write_text("x")
    snap = load_contract_snapshot(tmp_path)
    with pytest.raises(ContractViolation): enforce(snap, project_root=tmp_path, capability="write", declared=[], granted=[])
