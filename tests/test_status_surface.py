import io
import json
from pathlib import Path

from erasmus.mcp_server import ErasmusMcpServer
from erasmus.status_surface import collect_status_snapshot
from erasmus.store import Store


def test_collect_status_snapshot_includes_plan_knowledge_verification_and_recovery_sections(tmp_path):
    store = Store(str(tmp_path / "status.db"))
    store.init()

    with store.db:
        store.db.execute(
            """
            INSERT INTO missions(id, title, objective, success_condition, risk, status, updated_at)
            VALUES(1, 'bounded plan', 'validate phase 2', 'status command', 0.1, 'blocked', '2026-08-10T00:00:00')
            """
        )
        store.db.execute(
            "INSERT INTO propositions(statement, status) VALUES('bounded claim', 'established')"
        )
        store.db.execute(
            """
            INSERT INTO epistemic_evidence(record_type, content, source_kind, provenance_json, trust_class, effective_date, scope, actor)
            VALUES('evidence', 'evidence', 'test', '{}', 'primary', '2026-08-10', 'global', 'test')
            """
        )
        store.db.execute(
            """
            INSERT INTO local_runtime_sessions(endpoint, runtime_kind, model, capabilities_json, context_json, retrieved_refs_json, status)
            VALUES('http://localhost', 'local', 'model', '[]', '[]', '[]', 'success')
            """
        )

    snapshot = collect_status_snapshot(store.db)
    assert snapshot["read_only"] is True
    assert "plans" in snapshot
    assert snapshot["plans"]["mission_status"]["blocked"] == 1
    assert snapshot["knowledge"]["proposition_status"]["established"] == 1
    assert snapshot["verification"]["runtime_status"]["success"] == 1
    assert snapshot["plans"]["rollback_ready_missions"]


def test_mcp_status_tool_uses_status_snapshot(tmp_path):
    db = tmp_path / "erasmus.db"
    with open(db, "x", encoding="utf-8"):
        pass
    store = Store(str(db))
    store.init()
    with store.db:
        store.db.execute(
            """
            INSERT INTO missions(id, title, objective, success_condition, risk, status, updated_at)
            VALUES(2, 'snapshot test', 'test', 'done', 0.0, 'running', '2026-08-10T00:00:00')
            """
        )

    server = ErasmusMcpServer((tmp_path,))
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "erasmus_status"},
        }
    )
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["state"] == "ready"
    assert payload["read_only"] is True
    assert payload["plans"]["mission_status"]["running"] == 1
