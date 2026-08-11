"""Bounded observability snapshot for operator status surfaces."""

from __future__ import annotations

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
    "tool_manifests",
    "tool_audit",
)


def _counts_for_status(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) AS count FROM {table} GROUP BY {column}"
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


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
    proposition_status = _counts_for_status(conn, "propositions", "status")
    evidence_trust = _counts_for_status(conn, "epistemic_evidence", "trust_class")
    runtime_status = _counts_for_status(conn, "local_runtime_sessions", "status")
    invocation_status = _counts_for_status(conn, "capability_invocations", "status")
    tool_states = _counts_for_status(conn, "tool_manifests", "lifecycle")

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
            "SELECT id, status, risk FROM missions "
            "WHERE status IN ('completed', 'failed', 'cancelled', 'blocked') "
            "ORDER BY updated_at DESC, id DESC LIMIT 10"
        ).fetchall()
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
            "tool_lifecycles": tool_states,
        },
        "blocks": {
            "quarantined_or_restricted_tools": _counts_for_status(
                conn, "tool_manifests", "lifecycle"
            ),
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
