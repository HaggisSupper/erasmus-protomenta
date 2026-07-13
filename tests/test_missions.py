import json
import sqlite3
import sys
from pathlib import Path

import pytest

from erasmus.capability_graph import CapabilityGraph
from erasmus.capability_runtime import CapabilityRequest, CapabilityRuntime, validate_json_schema
from erasmus.missions import MissionEngine, MissionError
from erasmus.cli.main import main
from erasmus.store import Store


MANIFEST = Path("capabilities/okf/pr-governance")


def environment(tmp_path, capability="validate_json_schema", implementation="jsonschema_validator", handler=validate_json_schema):
    store = Store(str(tmp_path / "missions.db"))
    store.init()
    CapabilityGraph(store.db).import_bundle(MANIFEST)
    runtime = CapabilityRuntime(store)
    runtime.configure(capability, "1.0.0", implementation, "1.0.0", handler)
    for state in ("implemented", "isolated_test", "adversarial_review", "approved", "active"):
        runtime.transition(capability, "1.0.0", state)
    return store, runtime, MissionEngine(store, runtime)


def invocation(step_id="validate", **overrides):
    value = {
        "id": step_id,
        "capability_id": "validate_json_schema",
        "version": "1.0.0",
        "inputs": {"schema": {"type": "integer"}, "instance": 1},
        "authorities": ["schema:validate"],
        "provenance": {"caller": "mission-test", "request_id": step_id},
        "side_effects": [],
        "evidence_refs": ["validation_result"],
        "irreversible": False,
    }
    value.update(overrides)
    return value


def contract(steps=None, **overrides):
    value = {
        "version": "1.0.0",
        "title": "Bounded validation",
        "objective": "Validate one deterministic value",
        "success_conditions": ["all declared steps complete"],
        "constraints": ["one step at a time"],
        "authority_envelope": ["schema:validate"],
        "allowed_capabilities": ["validate_json_schema@1.0.0"],
        "evidence_requirements": ["validation_result"],
        "risk_class": "low",
        "stopping_condition": {"type": "all_steps_completed", "max_steps": 1},
        "rollback_plan": {"description": "No state changes"},
        "steps": steps or [invocation()],
    }
    value.update(overrides)
    return value


def authorize(engine, mission_id):
    engine.authorize(mission_id, "Protomentat", ["approval:mission-test"])


def test_authorized_bounded_mission_completes_and_is_auditable(tmp_path):
    store, _, engine = environment(tmp_path)
    mission_id = engine.create(contract())
    proposed = engine.inspect(mission_id)
    assert proposed["state"] == "proposed"
    assert proposed["steps"][0]["result"] is None
    assert "result_json" not in proposed["steps"][0]
    with pytest.raises(MissionError, match="cannot run"):
        engine.run_one(mission_id)
    authorize(engine, mission_id)
    assert engine.run_one(mission_id)["completed"] is True
    inspected = engine.inspect(mission_id)
    assert inspected["state"] == "completed"
    assert [item["to_state"] for item in inspected["transitions"]] == [
        "draft", "proposed", "authorized", "running", "completed"
    ]
    assert inspected["steps"][0]["status"] == "completed"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM mission_transitions WHERE mission_id = ?", (mission_id,))


def test_invalid_transition_and_capability_envelope_fail_closed(tmp_path):
    _, _, engine = environment(tmp_path)
    mission_id = engine.create(contract())
    with pytest.raises(MissionError, match="invalid mission transition"):
        engine.pause(mission_id)
    outside = contract(
        steps=[invocation(capability_id="hash_content")],
        allowed_capabilities=["validate_json_schema@1.0.0"],
    )
    outside_id = engine.create(outside)
    authorize(engine, outside_id)
    with pytest.raises(MissionError, match="outside the mission envelope"):
        engine.run_one(outside_id)
    assert engine.inspect(outside_id)["state"] == "blocked"


def test_creation_and_authorization_are_atomic(tmp_path, monkeypatch):
    store, runtime, engine = environment(tmp_path)

    def interrupted(*args, **kwargs):
        raise RuntimeError("interrupted")

    with monkeypatch.context() as context:
        context.setattr(engine, "_transition_in_transaction", interrupted)
        with pytest.raises(RuntimeError, match="interrupted"):
            engine.create(contract())
    assert store.db.execute("SELECT COUNT(*) FROM missions").fetchone()[0] == 0

    engine = MissionEngine(store, runtime)
    mission_id = engine.create(contract())
    with monkeypatch.context() as context:
        context.setattr(engine, "_transition_in_transaction", interrupted)
        with pytest.raises(RuntimeError, match="interrupted"):
            authorize(engine, mission_id)
    assert engine.inspect(mission_id)["state"] == "proposed"
    assert engine.inspect(mission_id)["approvals"] == []


def test_step_budget_stops_before_second_execution(tmp_path):
    _, _, engine = environment(tmp_path)
    mission_id = engine.create(
        contract(steps=[invocation("one"), invocation("two")])
    )
    authorize(engine, mission_id)
    assert engine.run_one(mission_id)["ok"] is True
    with pytest.raises(MissionError, match="budget exceeded"):
        engine.run_one(mission_id)
    assert engine.inspect(mission_id)["state"] == "failed"


def test_authority_expansion_pauses_and_denial_fails(tmp_path):
    _, _, engine = environment(tmp_path)
    mission_id = engine.create(
        contract(
            steps=[invocation(authorities=["schema:validate", "network:access"])],
            authority_envelope=["schema:validate"],
        )
    )
    authorize(engine, mission_id)
    paused = engine.run_one(mission_id)
    assert paused["approval_required"] is True
    assert engine.inspect(mission_id)["state"] == "awaiting_approval"
    engine.decide_approval(mission_id, paused["approval_id"], False, "Protomentat")
    assert engine.inspect(mission_id)["state"] == "failed"


def test_irreversible_step_requires_explicit_approval(tmp_path):
    _, _, engine = environment(tmp_path)
    mission_id = engine.create(contract(steps=[invocation(irreversible=True)]))
    authorize(engine, mission_id)
    paused = engine.run_one(mission_id)
    assert paused["kind"] == "irreversible_action"
    engine.decide_approval(mission_id, paused["approval_id"], True, "Protomentat")
    assert engine.run_one(mission_id)["completed"] is True


def test_recovery_does_not_repeat_a_committed_invocation(tmp_path):
    calls = []

    def build(inputs):
        calls.append(inputs["head_sha"])
        return {"build_result": {"head_sha": inputs["head_sha"]}}

    store, runtime, engine = environment(
        tmp_path, "compile_build", "python_builder", build
    )
    build_step = invocation(
        capability_id="compile_build",
        inputs={"head_sha": "abc123"},
        authorities=["process:execute"],
        provenance={"head_sha": "abc123", "command": "build", "tool_version": "1"},
        side_effects=["writes_build_artifacts"],
        evidence_refs=["build_log"],
    )
    mission_id = engine.create(
        contract(
            steps=[build_step],
            authority_envelope=["process:execute"],
            allowed_capabilities=["compile_build@1.0.0"],
            evidence_requirements=["build_log"],
        )
    )
    authorize(engine, mission_id)
    engine._transition(mission_id, "running", "simulated_start")
    store.db.execute(
        "UPDATE mission_steps SET status = 'running' WHERE mission_id = ?", (mission_id,)
    )
    result = runtime.invoke(
        CapabilityRequest(
            "compile_build", "1.0.0", {"head_sha": "abc123"},
            frozenset({"process:execute"}),
            {"head_sha": "abc123", "command": "build", "tool_version": "1", "mission_id": mission_id, "step_id": "validate"},
            frozenset({"writes_build_artifacts"}), ("build_log",),
        )
    )
    assert result.ok and calls == ["abc123"]
    assert engine.recover(mission_id)["completed"] == 1
    assert engine.run_one(mission_id)["completed"] is True
    assert calls == ["abc123"]


def test_interrupted_unrecorded_side_effect_fails_safe(tmp_path):
    store, _, engine = environment(tmp_path)
    mission_id = engine.create(contract())
    authorize(engine, mission_id)
    engine._transition(mission_id, "running", "simulated_start")
    request_data = json.loads(store.db.execute(
        "SELECT request_json FROM mission_steps WHERE mission_id = ?", (mission_id,)
    ).fetchone()[0])
    request_data["side_effects"] = ["unknown:write"]
    store.db.execute(
        "UPDATE mission_steps SET status = 'running', request_json = ? WHERE mission_id = ?",
        (json.dumps(request_data), mission_id),
    )
    assert engine.recover(mission_id)["uncertain"] == 1
    assert engine.inspect(mission_id)["state"] == "blocked"


def test_rollback_executes_only_declared_actions_and_reports_others(tmp_path):
    calls = []

    def build(inputs):
        calls.append(inputs["head_sha"])
        return {"build_result": {"head_sha": inputs["head_sha"]}}

    _, _, engine = environment(tmp_path, "compile_build", "python_builder", build)
    rollback = {
        "capability_id": "compile_build",
        "version": "1.0.0",
        "inputs": {"head_sha": "rollback"},
        "authorities": ["process:execute"],
        "provenance": {"head_sha": "rollback", "command": "rollback", "tool_version": "1"},
        "side_effects": ["writes_build_artifacts"],
        "evidence_refs": ["build_log"],
    }
    reversible = invocation(
        "reversible", capability_id="compile_build", inputs={"head_sha": "forward"},
        authorities=["process:execute"],
        provenance={"head_sha": "forward", "command": "build", "tool_version": "1"},
        side_effects=["writes_build_artifacts"], evidence_refs=["build_log"], rollback=rollback,
    )
    mission_id = engine.create(contract(
        steps=[reversible], authority_envelope=["process:execute"],
        allowed_capabilities=["compile_build@1.0.0"], evidence_requirements=["build_log"],
    ))
    authorize(engine, mission_id)
    assert engine.run_one(mission_id)["completed"] is True
    report = engine.rollback(mission_id)
    assert [*calls] == ["forward", "rollback"]
    assert report["rolled_back"] and not report["failed"]
    assert engine.inspect(mission_id)["state"] == "rolled_back"


def test_cli_create_inspect_authorize_and_cancel(tmp_path, monkeypatch, capsys):
    database = tmp_path / "cli.db"
    fixture = Path("contracts/fixtures/valid_mission.json")
    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", str(database), "mission-create", "--contract", str(fixture)]
    )
    main()
    mission_id = int(capsys.readouterr().out)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus", "--db", str(database), "mission-authorize", str(mission_id),
            "--actor", "Protomentat", "--evidence", "approval:manual",
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["state"] == "authorized"

    monkeypatch.setattr(
        sys, "argv", ["erasmus", "--db", str(database), "mission-cancel", str(mission_id)]
    )
    main()
    assert json.loads(capsys.readouterr().out)["state"] == "cancelled"


def test_rollback_cannot_escape_mission_authority(tmp_path):
    _, _, engine = environment(tmp_path)
    step = invocation(
        rollback={
            "capability_id": "validate_json_schema",
            "version": "1.0.0",
            "inputs": {"schema": {"type": "integer"}, "instance": 1},
            "authorities": ["network:access"],
            "provenance": {"caller": "mission-test", "request_id": "rollback"},
            "side_effects": [],
            "evidence_refs": ["validation_result"],
        }
    )
    mission_id = engine.create(contract(steps=[step]))
    authorize(engine, mission_id)
    assert engine.run_one(mission_id)["completed"] is True
    report = engine.rollback(mission_id)
    assert report["failed"][0]["reason"] == "rollback outside mission envelope"
    assert engine.inspect(mission_id)["state"] == "completed"
