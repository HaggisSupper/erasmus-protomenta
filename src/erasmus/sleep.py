"""Recoverable, deterministic sleep consolidation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from erasmus.store import Store


VERSION = "1.0.0"
STAGES = ("quarantine", "extract", "reconcile", "validate", "promote_defer", "checkpoint")
FAILURE_STAGES = frozenset(STAGES[:-1])
CANDIDATE_TYPES = frozenset(
    {
        "rag_insert", "proposition_change", "tangible_wrongness",
        "behavioral_lesson", "immune_signature",
    }
)
SOURCE_CLASSES = {
    "protomentat_input": "protomentat",
    "erasmus_output": "erasmus",
    "tool_output": "tool",
    "external_content": "external",
    "deterministic_result": "deterministic",
    "reviewer_decision": "reviewer",
    "correction": "reviewer",
}


class SleepError(RuntimeError):
    """Raised when consolidation or a promotion decision fails closed."""


def consolidate(store: Store, *, fail_after_stage: str | None = None) -> dict[str, Any]:
    """Classify all pending events exactly once and checkpoint atomically.

    ``fail_after_stage`` is a deterministic recovery-test seam. Production
    callers leave it unset.
    """
    if fail_after_stage is not None and fail_after_stage not in FAILURE_STAGES:
        raise SleepError(f"invalid failure stage: {fail_after_stage}")
    last_id = _last_event_id(store)
    rows = store.db.execute(
        "SELECT id, kind, payload FROM events WHERE id > ? ORDER BY id", (last_id,)
    ).fetchall()
    counts: dict[str, Any] = {
        "events": len(rows),
        "experience_candidates": 0,
        "last_event_id": last_id,
        "run_id": None,
    }
    if not rows:
        return counts

    run_id = _open_or_resume_run(store, last_id + 1, rows[-1]["id"])
    counts["run_id"] = run_id
    try:
        if fail_after_stage == "quarantine":
            raise SleepError("injected failure after quarantine")
        _stage(store, run_id, "extract", {"events": len(rows)})
        if fail_after_stage == "extract":
            raise SleepError("injected failure after extract")

        classified = _reconcile(store, run_id, rows)
        _stage(store, run_id, "reconcile", {"classified": classified})
        if fail_after_stage == "reconcile":
            raise SleepError("injected failure after reconcile")

        _stage(store, run_id, "validate", {"conflicts_checked": len(rows)})
        if fail_after_stage == "validate":
            raise SleepError("injected failure after validate")

        counts["experience_candidates"] = _defer_adaptations(store, run_id)
        _stage(
            store, run_id, "promote_defer",
            {"experience_candidates": counts["experience_candidates"]},
        )
        if fail_after_stage == "promote_defer":
            raise SleepError("injected failure after promote_defer")

        new_last_id = rows[-1]["id"]
        with store.db:
            store.db.execute(
                """
                INSERT INTO sleep_progress(id, last_event_id) VALUES(1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_event_id = excluded.last_event_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (new_last_id,),
            )
            store.db.execute(
                """
                UPDATE sleep_runs SET status = 'completed', current_stage = 'checkpoint',
                    failure_reason = NULL, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (run_id,),
            )
            store.db.execute(
                "INSERT INTO sleep_run_stages(run_id, stage, detail_json) VALUES(?, 'checkpoint', ?)",
                (run_id, _json({"last_event_id": new_last_id})),
            )
        counts["last_event_id"] = new_last_id
    except Exception as error:
        _fail(store, run_id, str(error))
        raise
    return counts | {"report": sleep_report(store, run_id)}


def decide_candidate(
    store: Store,
    candidate_id: int,
    decision: str,
    target: str,
    evidence_id: int,
    actor: str,
    authority: str,
    reason: str,
) -> int:
    """Record an explicit human promotion decision without mutating canonical state."""
    if authority != "sleep:promote":
        raise SleepError("authority denied: expected sleep:promote")
    if decision not in {"approved", "rejected"}:
        raise SleepError("decision must be approved or rejected")
    if target not in {"belief", "skill"}:
        raise SleepError("target must be belief or skill")
    if (
        not isinstance(actor, str) or not actor.strip()
        or not isinstance(reason, str) or not reason.strip()
    ):
        raise SleepError("actor and reason are required")
    candidate = store.db.execute(
        "SELECT * FROM sleep_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    if candidate is None:
        raise SleepError(f"sleep candidate not found: {candidate_id}")
    if not _normalize_content(candidate["content"]):
        raise SleepError("candidate content is invalid after normalization")
    expected_target = {
        "proposition_change": "belief",
        "behavioral_lesson": "skill",
    }.get(candidate["candidate_type"])
    if expected_target != target:
        raise SleepError("candidate type does not match promotion target")
    if candidate["initial_disposition"] in {"quarantined", "rejected"}:
        raise SleepError("quarantined or rejected candidates cannot be promoted")
    if store.db.execute(
        "SELECT 1 FROM epistemic_evidence WHERE id = ?", (evidence_id,)
    ).fetchone() is None:
        raise SleepError(f"promotion evidence not found: {evidence_id}")
    try:
        with store.db:
            cursor = store.db.execute(
                """
                INSERT INTO sleep_promotions(
                    candidate_id, decision, target, evidence_id, actor, authority, reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, decision, target, evidence_id, actor, authority, reason),
            )
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise SleepError("candidate already has a decision for this target") from error
        raise
    return int(cursor.lastrowid)


def sleep_report(store: Store, run_id: int) -> dict[str, Any]:
    run = store.db.execute("SELECT * FROM sleep_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise SleepError(f"sleep run not found: {run_id}")
    items = store.db.execute(
        """
        SELECT i.*, c.id AS candidate_id, c.content, c.provenance_json,
               p.decision, p.target, p.evidence_id AS promotion_evidence_id,
               p.actor AS decision_actor, p.reason AS decision_reason
        FROM sleep_items i
        LEFT JOIN sleep_candidates c ON c.event_id = i.event_id
        LEFT JOIN sleep_promotions p ON p.candidate_id = c.id
        WHERE i.run_id = ? ORDER BY i.event_id
        """,
        (run_id,),
    ).fetchall()
    summary = {
        disposition: sum(row["disposition"] == disposition for row in items)
        for disposition in ("accepted", "deferred", "quarantined", "rejected", "discarded")
    }
    decoded = []
    for row in items:
        value = dict(row)
        provenance_json = value.pop("provenance_json")
        value["provenance"] = json.loads(provenance_json) if provenance_json else None
        decoded.append(value)
    stages = [
        {**dict(row), "detail": json.loads(row["detail_json"])}
        for row in store.db.execute(
            "SELECT * FROM sleep_run_stages WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
    ]
    return {"run": dict(run), "summary": summary, "items": decoded, "stages": stages}


def _reconcile(store: Store, run_id: int, rows) -> int:
    classified = 0
    with store.db:
        for row in rows:
            if store.db.execute(
                "SELECT 1 FROM sleep_items WHERE event_id = ?", (row["id"],)
            ).fetchone():
                continue
            source, candidate_type, content, provenance, disposition, reason = _classify(
                row["id"], row["kind"], row["payload"]
            )
            if candidate_type is not None and disposition not in {"quarantined", "rejected"}:
                conflict = _conflict(store, row["id"], candidate_type, content)
                if conflict:
                    disposition, reason = "rejected", conflict
            store.db.execute(
                """
                INSERT INTO sleep_items(
                    run_id, event_id, source_class, candidate_type, disposition, reason
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (run_id, row["id"], source, candidate_type, disposition, reason),
            )
            if candidate_type is not None and content:
                store.db.execute(
                    """
                    INSERT INTO sleep_candidates(
                        event_id, candidate_type, content, provenance_json,
                        initial_disposition
                    ) VALUES(?, ?, ?, ?, ?)
                    """,
                    (row["id"], candidate_type, content, _json(provenance), disposition),
                )
            classified += 1
    return classified


def _classify(event_id: int, kind: str, raw_payload: str):
    source = SOURCE_CLASSES.get(kind, "unknown")
    payload: Mapping[str, Any] | None = None
    try:
        parsed = json.loads(raw_payload)
        if isinstance(parsed, Mapping):
            payload = parsed
    except (TypeError, json.JSONDecodeError):
        pass

    if kind == "correction":
        content = _normalize_content(raw_payload)
        if not content:
            return source, None, "", {}, "rejected", "candidate content is required"
        return (
            source, "behavioral_lesson", content,
            {"source_event_id": event_id, "source_class": source},
            "deferred", "legacy correction retained as a deferred lesson",
        )
    if payload is None:
        content = _normalize_content(raw_payload)
        if not content:
            return source, None, "", {}, "rejected", "candidate content is required"
        if source in {"external", "erasmus"}:
            return (
                source, "rag_insert", content,
                {"source_event_id": event_id, "source_class": source, "trust": "untrusted"},
                "quarantined", "external or model content defaults to quarantine",
            )
        if source == "protomentat":
            return (
                source, "rag_insert", content,
                {"source_event_id": event_id, "source_class": source},
                "accepted", "explicit human input accepted only as memory candidate",
            )
        return source, None, "", {}, "discarded", "no typed consolidation candidate"

    candidate_type = payload.get("candidate_type")
    raw_content = payload.get("content")
    content = _normalize_content(raw_content) if isinstance(raw_content, str) else ""
    if candidate_type not in CANDIDATE_TYPES or not content:
        return source, None, "", {}, "rejected", "candidate type and content are required"
    provenance = {
        "source_event_id": event_id,
        "source_class": source,
        **(payload.get("provenance") if isinstance(payload.get("provenance"), Mapping) else {}),
    }
    if source in {"external", "erasmus"}:
        return (
            source, candidate_type, content, provenance, "quarantined",
            "external or model content cannot cross a canonical boundary",
        )
    if candidate_type == "behavioral_lesson" and source not in {"reviewer"}:
        return (
            source, candidate_type, content, provenance, "quarantined",
            "raw content cannot become adaptive training",
        )
    if candidate_type in {"proposition_change", "behavioral_lesson", "immune_signature"}:
        return (
            source, candidate_type, content, provenance, "deferred",
            "candidate requires explicit review and promotion",
        )
    return source, candidate_type, content, provenance, "accepted", "candidate accepted for review"


def _conflict(store: Store, event_id: int, candidate_type: str, content: str) -> str | None:
    normalized = _normalize_content(content)
    if candidate_type == "proposition_change":
        statements = store.db.execute("SELECT statement FROM propositions").fetchall()
        if any(_normalize_content(row["statement"]) == normalized for row in statements):
            return "current ledger already contains this proposition"
    prior = store.db.execute(
        """
        SELECT 1 FROM sleep_candidates c
        JOIN sleep_items i ON i.event_id = c.event_id
        WHERE c.event_id != ? AND c.candidate_type = ?
          AND i.disposition IN ('accepted', 'deferred')
          AND c.content = ?
        """,
        (event_id, candidate_type, normalized),
    ).fetchone()
    if prior is not None:
        return "prior consolidated material already contains this candidate"
    legacy = store.db.execute(
        """
        SELECT c.content FROM sleep_candidates c
        JOIN sleep_items i ON i.event_id = c.event_id
        WHERE c.event_id != ? AND c.candidate_type = ?
          AND i.disposition IN ('accepted', 'deferred')
          AND c.content != ?
        """,
        (event_id, candidate_type, normalized),
    ).fetchall()
    if any(_normalize_content(row["content"]) == normalized for row in legacy):
        return "prior consolidated material already contains this candidate"
    return None


def _defer_adaptations(store: Store, run_id: int) -> int:
    created = 0
    rows = store.db.execute(
        """
        SELECT c.event_id, c.content FROM sleep_candidates c
        JOIN sleep_items i ON i.event_id = c.event_id
        WHERE i.run_id = ? AND c.candidate_type = 'behavioral_lesson'
          AND i.disposition IN ('accepted', 'deferred')
        """,
        (run_id,),
    ).fetchall()
    with store.db:
        for row in rows:
            lesson = _normalize_content(row["content"])
            if not lesson:
                continue
            cursor = store.db.execute(
                """
                INSERT OR IGNORE INTO experience_candidates(
                    lesson, status, created_at, source_event_id
                ) VALUES(?, 'candidate', CURRENT_TIMESTAMP, ?)
                """,
                (lesson, row["event_id"]),
            )
            created += cursor.rowcount
    return created


def _open_or_resume_run(store: Store, start_event_id: int, end_event_id: int) -> int:
    try:
        store.db.execute("BEGIN IMMEDIATE")
        resumable = store.db.execute(
            """
            SELECT id FROM sleep_runs
            WHERE status IN ('failed', 'running') AND version = ? AND start_event_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (VERSION, start_event_id),
        ).fetchone()
        if resumable is not None:
            run_id = int(resumable["id"])
            store.db.execute(
                """
                UPDATE sleep_runs SET status = 'running', current_stage = 'quarantine',
                    end_event_id = ?, failure_reason = NULL, completed_at = NULL
                WHERE id = ?
                """,
                (end_event_id, run_id),
            )
        else:
            cursor = store.db.execute(
                """
                INSERT INTO sleep_runs(
                    version, status, current_stage, start_event_id, end_event_id
                ) VALUES(?, 'running', 'quarantine', ?, ?)
                """,
                (VERSION, start_event_id, end_event_id),
            )
            run_id = int(cursor.lastrowid)
        store.db.execute(
            "INSERT INTO sleep_run_stages(run_id, stage, detail_json) VALUES(?, 'quarantine', ?)",
            (run_id, _json({"start_event_id": start_event_id, "end_event_id": end_event_id})),
        )
        store.db.commit()
    except Exception:
        store.db.rollback()
        raise
    return run_id


def _stage(store: Store, run_id: int, stage: str, detail: Mapping[str, Any]) -> None:
    with store.db:
        store.db.execute(
            "UPDATE sleep_runs SET status = 'running', current_stage = ? WHERE id = ?",
            (stage, run_id),
        )
        store.db.execute(
            "INSERT INTO sleep_run_stages(run_id, stage, detail_json) VALUES(?, ?, ?)",
            (run_id, stage, _json(detail)),
        )


def _fail(store: Store, run_id: int, reason: str) -> None:
    with store.db:
        store.db.execute(
            """
            UPDATE sleep_runs SET status = 'failed', current_stage = 'failed',
                failure_reason = ? WHERE id = ?
            """,
            (reason, run_id),
        )
        store.db.execute(
            "INSERT INTO sleep_run_stages(run_id, stage, detail_json) VALUES(?, 'failed', ?)",
            (run_id, _json({"reason": reason})),
        )


def _last_event_id(store: Store) -> int:
    row = store.db.execute(
        "SELECT last_event_id FROM sleep_progress WHERE id = 1"
    ).fetchone()
    return int(row["last_event_id"]) if row is not None else 0


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_content(content: Any) -> str:
    if not isinstance(content, str):
        return ""
    return " ".join(content.split())
