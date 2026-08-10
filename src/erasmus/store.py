from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import apply_migrations
from .phase3_completion_migrations import apply_phase3_completion
from .phase3_hardening import apply_phase3_hardening
from .phase3_migrations import apply_phase3_migrations
from .phase3_review_migrations import apply_phase3_review_migrations


class Store:
    """Durable SQLite-backed state store for the Erasmus cognitive kernel.

    ``init()`` preserves the established kernel schema boundary. Phase 3 is an
    additive, explicitly activated subsystem and therefore uses
    ``init_phase3()`` rather than silently broadening every Store consumer.
    """

    def __init__(self, path: str = "state/erasmus.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")

    def init(self) -> None:
        """Apply any unapplied established-kernel migrations."""
        apply_migrations(self.db)

    def init_phase3(self) -> list[int]:
        """Explicitly activate the complete additive Phase 3 schema.

        Callers invoke this after ``init()``. All Phase 3 migration runners are
        idempotent and use the shared auditable schema-version ledger.
        """
        applied = apply_phase3_migrations(self.db)
        applied.extend(apply_phase3_hardening(self.db))
        applied.extend(apply_phase3_completion(self.db))
        applied.extend(apply_phase3_review_migrations(self.db))
        return applied

    def add_event(self, kind: str, payload: str) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO events(kind, payload) VALUES(?, ?)",
                (kind, payload),
            )
        return int(cur.lastrowid)

    def start_session(self) -> int:
        with self.db:
            cur = self.db.execute("INSERT INTO sessions(status) VALUES('active')")
        return int(cur.lastrowid)

    def end_session(self, session_id: int) -> None:
        with self.db:
            rowcount = self.db.execute(
                """
                UPDATE sessions
                SET status = 'ended', ended_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (session_id,),
            ).rowcount
        if rowcount == 0:
            raise ValueError(f"session {session_id!r} not found")

    def interrupted_sessions(self) -> list[int]:
        rows = self.db.execute(
            "SELECT id FROM sessions WHERE status = 'active' AND ended_at IS NULL"
        ).fetchall()
        return [row["id"] for row in rows]

    def integrity_check(self) -> list[str]:
        rows = self.db.execute("PRAGMA integrity_check").fetchall()
        return [row[0] for row in rows]
