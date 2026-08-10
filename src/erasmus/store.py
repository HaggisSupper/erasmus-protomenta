from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import apply_migrations
from .phase3_migrations import apply_phase3_migrations


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
        """Apply the established kernel migrations exactly once."""
        apply_migrations(self.db)

    def init_phase3(self) -> list[int]:
        """Explicitly activate the additive Phase 3 schema.

        Callers that instantiate the Phase 3 knowledge runtime must invoke this
        after ``init()``. The operation is idempotent and records migrations in
        the same auditable schema-version ledger.
        """
        return apply_phase3_migrations(self.db)

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
