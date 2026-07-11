"""Versioned SQLite migration runner.

Each migration is identified by an integer version number.  The runner
creates a ``schema_version`` table on first use and applies only the
migrations that have not yet been recorded there.  Every migration is
wrapped in a single database transaction so a partial failure leaves the
database unchanged and the version is not recorded.

Consumers call :func:`apply_migrations` after opening a connection.
"""
from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# Migration catalogue
# ---------------------------------------------------------------------------
# Each entry is (version: int, sql: str).  The SQL may contain multiple
# statements separated by semicolons; blank statements are skipped.
# PRAGMA statements that cannot run inside a transaction must be called
# separately (see Store.__init__).  Do NOT include PRAGMA journal_mode here.
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        # Initial schema: mirrors the original SCHEMA constant verbatim so
        # that the runner is safe to apply against an already-initialised DB.
        """
        CREATE TABLE IF NOT EXISTS events(
            id      INTEGER PRIMARY KEY,
            ts      TEXT    DEFAULT CURRENT_TIMESTAMP,
            kind    TEXT    NOT NULL,
            payload TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS propositions(
            id         INTEGER PRIMARY KEY,
            statement  TEXT    NOT NULL UNIQUE,
            status     TEXT    NOT NULL,
            confidence REAL    NOT NULL DEFAULT 0.5,
            updated_at TEXT    DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS missions(
            id                INTEGER PRIMARY KEY,
            title             TEXT NOT NULL,
            objective         TEXT NOT NULL,
            success_condition TEXT NOT NULL,
            risk              REAL NOT NULL DEFAULT 0,
            status            TEXT NOT NULL DEFAULT 'proposed',
            created_at        TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS experience_candidates(
            id             INTEGER PRIMARY KEY,
            lesson         TEXT    NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            status         TEXT    NOT NULL DEFAULT 'candidate'
        );
        CREATE TABLE IF NOT EXISTS immune_state(
            id         INTEGER PRIMARY KEY,
            agent_id   TEXT NOT NULL,
            signature  TEXT NOT NULL,
            state_json TEXT NOT NULL,
            wake_json  TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'sleeping',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS checkpoints(
            id         INTEGER PRIMARY KEY,
            frontier   TEXT NOT NULL,
            next_move  TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        2,
        # Continuity enhancements:
        #   - sessions table for lifecycle provenance
        #   - sleep_progress table for idempotent consolidation
        #   - new columns on checkpoints for full cognitive frontier model
        #   - created_at provenance on experience_candidates
        #
        # ALTER TABLE ADD COLUMN defaults must be literals (SQLite restriction).
        """
        CREATE TABLE IF NOT EXISTS sessions(
            id         INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at   TEXT,
            status     TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS sleep_progress(
            id            INTEGER PRIMARY KEY CHECK (id = 1),
            last_event_id INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE checkpoints ADD COLUMN proposition              TEXT NOT NULL DEFAULT '';
        ALTER TABLE checkpoints ADD COLUMN strongest_support        TEXT NOT NULL DEFAULT '';
        ALTER TABLE checkpoints ADD COLUMN strongest_contradiction   TEXT NOT NULL DEFAULT '';
        ALTER TABLE checkpoints ADD COLUMN unresolved_tension       TEXT NOT NULL DEFAULT '';
        ALTER TABLE checkpoints ADD COLUMN active_mode              TEXT NOT NULL DEFAULT 'dialogue';
        ALTER TABLE checkpoints ADD COLUMN pending_leap             TEXT;
        ALTER TABLE checkpoints ADD COLUMN relevant_tangible_wrongness TEXT;
        ALTER TABLE checkpoints ADD COLUMN source_event_ids         TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE experience_candidates ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        """,
    ),
    (
        3,
        # Repair any experience_candidates rows that received an empty
        # created_at string from a pre-fix migration 2 DEFAULT ''.
        # Also back-fills sessions.ended_at semantics: rows that were
        # active before migration 3 but have no ended_at are left as-is
        # so interrupted_sessions() can detect them.
        """
        UPDATE experience_candidates
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL OR created_at = ''
        """,
    ),
]


def _split_statements(sql: str) -> list[str]:
    """Split a semicolon-delimited SQL string into individual statements."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def apply_migrations(db: sqlite3.Connection) -> list[int]:
    """Apply any unapplied migrations to *db* and return the versions applied.

    Creates the ``schema_version`` table if it does not yet exist.  Each
    migration is applied atomically: either all of its statements succeed and
    the version is recorded, or the transaction is rolled back and the version
    is not recorded.

    Calling this function multiple times on the same database is safe; already-
    applied migrations are skipped.

    Args:
        db: An open :class:`sqlite3.Connection`.  ``row_factory`` is not
            required; the function sets it locally for its own queries.

    Returns:
        A list of version numbers that were applied during this call (empty
        list if everything was already up to date).
    """
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version(
            version    INTEGER PRIMARY KEY,
            applied_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()

    rows = db.execute("SELECT version FROM schema_version").fetchall()
    applied_versions: set[int] = {row[0] for row in rows}

    newly_applied: list[int] = []
    for version, sql in MIGRATIONS:
        if version in applied_versions:
            continue
        with db:
            for stmt in _split_statements(sql):
                db.execute(stmt)
            db.execute(
                "INSERT INTO schema_version(version) VALUES(?)",
                (version,),
            )
        newly_applied.append(version)

    return newly_applied
