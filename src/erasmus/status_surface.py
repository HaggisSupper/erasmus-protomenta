"""Bounded observability snapshot for operator status surfaces."""

import json
import sqlite3
from typing import Any


TABLES = (
    "events",
    "propositions",
    "epistemic_evidence",
    "proposition_transitions",
    "missions",
    "experience_candidates",
    "sleep_runs",
    "sleep_items",
    "sleep_candidates",
    "immune_state",
    "immune_incidents",
    "immune_findings",
    "checkpoints",
    "local_runtime_sessions",
    "runtime_identity_changes",
    "divergence_windows",
    "divergence_calibrations",
    "divergence_recommendations",
    "divergence_evaluations",
    "skill_observations",
    "skill_artifacts",
    "skill_transitions",
    "skill_evaluations",
    "adapter_readiness_exports",
    "sessions",
    "capabilities",
    "capability_plans",
    "capability_evidence",
    "capability_invocations",
    "tool_manifests",
    "tool_audit",
)

RESTRICTED_TOOL_LIFECYCLES = frozenset({"quarantined", "deprecated", "revoked"})


def _counts_for_status(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) AS count FROM {table} GROUP BY {column}"  # noqa: S608
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _proposition_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT COALESCE(latest.new_status, p.status) AS status, COUNT(*) AS count
        FROM propositions p
        LEFT JOIN proposition_transitions latest ON latest.id = (
            SELECT id FROM proposition_transitions
            WHERE proposition_id = p.id ORDER BY id DESC LIMIT 1
        )
        GROUP BY COALESCE(latest.new_status, p.status)
        """
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _restricted_tool_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT lifecycle, COUNT(*) AS count FROM tool_manifests
        WHERE lifecycle IN (?, ?, ?)
        GROUP BY lifecycle
        """,
        tuple(RESTRICTED_TOOL_LIFECYCLES),
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _step_rolls_back_eligible(step: sqlite3.Row) -> bool:
    try:
        request = json.loads(step["request_json"])
    except (TypeError, json.JSONDecodeError):
        return False
    if step["rollback_json"] is None:
        return not request.get("side_effects")
    try:
        json.loads(step["rollback_json"])
    except (TypeError, json.JSONDecodeError):
        return False
    return True


def _mission_is_rollback_ready(conn: sqlite3.Connection, mission: sqlite3.Row) -> bool:
    try:
        json.loads(mission["contract_json"])
    except (TypeError, json.JSONDecodeError):
        return False
    steps = conn.execute(
        """
        SELECT request_json, rollback_json FROM mission_steps
        WHERE mission_id = ? AND status IN ('completed', 'failed', 'rollback_running')
        """,
        (mission["id"],),
    ).fetchall()
    return all(_step_rolls_back_eligible(step) for step in steps)


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
        for table in TABLES
    }


def _schema_versions(conn: sqlite3.Connection) -> list[int]:
    return [int(row[0]) for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]


def collect_status_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Collect a bounded operational status snapshot for CLI and MCP callers."""
    conn.row_factory = sqlite3.Row
    missions_by_status = _counts_for_status(conn, "missions", "status")
    proposition_status = _proposition_status_counts(conn)
    evidence_trust = _counts_for_status(conn, "epistemic_evidence", "trust_class")
    runtime_status = _counts_for_status(conn, "local_runtime_sessions", "status")
    invocation_status = _counts_for_status(conn, "capability_invocations", "status")

    blocked_missions = [
        {"id": row["id"], "status": row["status"], "title": row["title"], "updated_at": row["updated_at"]}
        for row in conn.execute(
            "SELECT id, status, title, updated_at FROM missions "
            "WHERE status IN ('blocked', 'awaiting_approval') "
            "ORDER BY updated_at DESC, id DESC LIMIT 5"
        ).fetchall()
    ]

    recovery_candidates = [
        {"id": row["id"], "status": row["status"], "risk": row["risk"]}
        for row in conn.execute(
            "SELECT id, status, risk, contract_json FROM missions "
            "WHERE status IN ('completed', 'failed', 'cancelled', 'blocked') "
            "ORDER BY updated_at DESC, id DESC LIMIT 10"
        ).fetchall()
        if _mission_is_rollback_ready(conn, row)
    ]

    return {
        "read_only": True,
        "tables": _table_counts(conn),
        "schema_versions": _schema_versions(conn),
        "plans": {
            "mission_status": missions_by_status,
            "blocked": blocked_missions,
            "rollback_ready_missions": recovery_candidates,
        },
        "knowledge": {
            "proposition_status": proposition_status,
            "evidence_trust": evidence_trust,
        },
        "verification": {
            "runtime_status": runtime_status,
            "capability_invocations": invocation_status,
            "tool_lifecycles": _counts_for_status(conn, "tool_manifests", "lifecycle"),
        },
        "blocks": {
            "quarantined_or_restricted_tools": _restricted_tool_counts(conn),
            "critical_findings": int(
                conn.execute(
                    "SELECT COUNT(*) FROM immune_findings WHERE outcome IN ('quarantine', 'escalate', 'lower_confidence_recommendation')"
                ).fetchone()[0]
            ),
            "interrupted_sessions": int(
                conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE status = 'active' AND ended_at IS NULL"
                ).fetchone()[0]
            ),
        },
    }
