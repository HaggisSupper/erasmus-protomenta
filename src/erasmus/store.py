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

    def integrity_check(self) -> list[str]:
        """Run SQLite's built-in integrity check and return the result lines.

        Returns ``['ok']`` when the database is clean.
        """
        rows = self.db.execute("PRAGMA integrity_check").fetchall()
        return [row[0] for row in rows]
