from __future__ import annotations

import sqlite3
from pathlib import Path

from .migrations import apply_migrations


class Store:
    """Durable SQLite-backed state store for the Erasmus cognitive kernel.

    Opens the database with WAL journal mode and foreign-key enforcement,
    then applies all pending schema migrations via :func:`apply_migrations`.

    All write operations are transactional: a failure leaves the database in
    its previous committed state.
    """

    def __init__(self, path: str = "state/erasmus.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        # WAL mode survives process termination without journal replay.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")

    def init(self) -> None:
        """Apply all pending schema migrations.

        Safe to call multiple times; already-applied migrations are skipped.
        """
        apply_migrations(self.db)

    def add_event(self, kind: str, payload: str) -> int:
        """Insert an event record and return its id.

        The write is atomic: either the row is committed or the database is
        unchanged.
        """
        with self.db:
            cur = self.db.execute(
                "INSERT INTO events(kind, payload) VALUES(?, ?)",
                (kind, payload),
            )
        return int(cur.lastrowid)

    def start_session(self) -> int:
        """Open a new session record and return its id.

        Records the wall-clock start time.  Call :meth:`end_session` when the
        process exits cleanly; sessions whose ``ended_at`` is NULL represent
        interrupted runs and can be detected on the next startup.
        """
        with self.db:
            cur = self.db.execute(
                "INSERT INTO sessions(status) VALUES('active')"
            )
        return int(cur.lastrowid)

    def end_session(self, session_id: int) -> None:
        """Mark *session_id* as ended and record the wall-clock finish time.

        Raises:
            ValueError: If *session_id* does not exist in the sessions table.
        """
        with self.db:
            rowcount = self.db.execute(
                """
                UPDATE sessions
                SET    status   = 'ended',
                       ended_at = CURRENT_TIMESTAMP
                WHERE  id = ?
                """,
                (session_id,),
            ).rowcount
        if rowcount == 0:
            raise ValueError(f"session {session_id!r} not found")

    def interrupted_sessions(self) -> list[int]:
        """Return ids of sessions that were never cleanly ended.

        These are rows where ``ended_at IS NULL`` and ``status = 'active'``.
        Used on startup to detect prior unclean termination.
        """
        rows = self.db.execute(
            "SELECT id FROM sessions WHERE status = 'active' AND ended_at IS NULL"
        ).fetchall()
        return [row["id"] for row in rows]

    def integrity_check(self) -> list[str]:
        """Run SQLite's built-in integrity check and return the result lines.

        Returns ``['ok']`` when the database is clean.
        """
        rows = self.db.execute("PRAGMA integrity_check").fetchall()
        return [row[0] for row in rows]
