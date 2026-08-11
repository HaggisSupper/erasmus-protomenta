import json

from erasmus.mcp_server import ErasmusMcpServer
from erasmus.status_surface import collect_status_snapshot
from erasmus.store import Store


def test_collect_status_snapshot_prefers_latest_proposition_transition(tmp_path):
    store = Store(str(tmp_path / "status.db"))
    store.init()

    with store.db:
        old_prop = store.db.execute(
            "INSERT INTO propositions(statement, status) VALUES('bounded claim', 'established')"
        ).lastrowid
        new_prop = store.db.execute(
            "INSERT INTO propositions(statement, status) VALUES('evolving claim', 'speculative')"
        ).lastrowid
        evidence_id = store.db.execute(
            """
            INSERT INTO epistemic_evidence(
                record_type, content, source_kind, provenance_json, trust_class,
                effective_date, scope, actor
            ) VALUES('evidence', 'evidence', 'test', '{}', 'primary', '2026-08-10', 'global', 'test')
            """
        ).lastrowid
        store.db.execute(
            """
            INSERT INTO proposition_transitions(
                proposition_id, operation, prior_status, new_status, evidence_id,
                actor, scope, reason
            ) VALUES(?, 'support', 'speculative', 'supported', ?, 'reviewer', 'global', 'evidence promoted')
            """,
            (new_prop, evidence_id),
        )
        store.db.execute(
            """
            INSERT INTO proposition_transitions(
                proposition_id, operation, prior_status, new_status, evidence_id,
                actor, scope, reason
            ) VALUES(?, 'support', 'established', 'contradicted', ?, 'reviewer', 'global', 'stale path')
            """,
            (old_prop, evidence_id),
        )
        store.db.execute(
            """
            INSERT INTO propositions(statement, status) VALUES('no-opinion claim', 'plausible')
            """
        )
        store.db.execute(
            """
            INSERT INTO tool_manifests(
                tool_id, version, target, implementation_id, digest, manifest_json, lifecycle
            ) VALUES('tool-good', '1.0.0', 'local', 'impl', 'sha', '{}', 'candidate'),
                   ('tool-quarantined', '1.0.0', 'local', 'impl', 'sha', '{}', 'quarantined'),
                   ('tool-revoked', '1.0.0', 'local', 'impl', 'sha', '{}', 'revoked'),
                   ('tool-deprecated', '1.0.0', 'local', 'impl', 'sha', '{}', 'deprecated')
            """
        )

    snapshot = collect_status_snapshot(store.db)
    assert snapshot["knowledge"]["proposition_status"]["supported"] == 1
    assert snapshot["knowledge"]["proposition_status"]["contradicted"] == 1
    assert snapshot["knowledge"]["proposition_status"]["plausible"] == 1
    assert snapshot["blocks"]["quarantined_or_restricted_tools"] == {
        "quarantined": 1,
        "revoked": 1,
        "deprecated": 1,
    }


def test_collect_status_snapshot_filters_rollback_candidates_by_contract_and_step_safety(tmp_path):
    store = Store(str(tmp_path / "status.db"))
    store.init()

    with store.db:
        store.db.execute(
            """
            INSERT INTO missions(title, objective, success_condition, risk, status, updated_at, contract_json)
            VALUES('ready-rollback', 'rollback', 'done', 0.1, 'completed', '2026-08-10T00:00:01', '{}')
            """
        )
        mission_ready = store.db.execute("SELECT id FROM missions WHERE title = 'ready-rollback'").fetchone()["id"]
        store.db.execute(
            """
            INSERT INTO mission_steps(
                mission_id, position, step_id, request_json, rollback_json, irreversible, status
            ) VALUES(?, 1, 'rollbackable', '{}', NULL, 0, 'completed')
            """,
            (mission_ready,),
        )

        store.db.execute(
            """
            INSERT INTO missions(title, objective, success_condition, risk, status, updated_at, contract_json)
            VALUES('no-side-effects', 'rollback', 'done', 0.1, 'failed', '2026-08-10T00:00:02', '{}')
            """
        )
        mission_no_side_effect = store.db.execute("SELECT id FROM missions WHERE title = 'no-side-effects'").fetchone()["id"]
        store.db.execute(
            """
            INSERT INTO mission_steps(
                mission_id, position, step_id, request_json, rollback_json, irreversible, status
            ) VALUES(?, 1, 'writes', '{\"side_effects\":[\"writes_file\"]}', NULL, 0, 'failed')
            """,
            (mission_no_side_effect,),
        )

        store.db.execute(
            """
            INSERT INTO missions(title, objective, success_condition, risk, status, updated_at, contract_json)
            VALUES('bad-contract', 'rollback', 'done', 0.1, 'completed', '2026-08-10T00:00:03', 'not-json')
            """
        )
        mission_bad_contract = store.db.execute("SELECT id FROM missions WHERE title = 'bad-contract'").fetchone()["id"]
        store.db.execute(
            """
            INSERT INTO mission_steps(
                mission_id, position, step_id, request_json, rollback_json, irreversible, status
            ) VALUES(?, 1, 'oops', '{}', NULL, 0, 'completed')
            """,
            (mission_bad_contract,),
        )

        candidates = collect_status_snapshot(store.db)["plans"]["rollback_ready_missions"]
        assert [row["id"] for row in candidates] == [mission_ready]


def test_mcp_status_tool_reports_authority_and_schema_defaults(tmp_path):
    db = tmp_path / "erasmus.db"
    with db.open("x", encoding="utf-8"):
        pass
    store = Store(str(db))
    store.init()
    with store.db:
        store.db.execute(
            """
            INSERT INTO missions(title, objective, success_condition, risk, status, updated_at)
            VALUES('snapshot test', 'test', 'done', 0.0, 'running', '2026-08-10T00:00:00')
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
    assert payload["authority"] == "erasmus"
    assert payload["read_only"] is True
    assert payload["plans"]["mission_status"]["running"] == 1
