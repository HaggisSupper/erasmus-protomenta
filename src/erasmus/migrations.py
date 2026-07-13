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
        ALTER TABLE experience_candidates ADD COLUMN created_at TEXT NOT NULL DEFAULT ''
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
    (
        4,
        # Minimal OKF-backed capability graph. Manifests remain the portable
        # source of truth; these tables are the deterministic projection used
        # for validation, planning, execution evidence, and rebuilds.
        """
        CREATE TABLE capability_manifest_sets(
            profile       TEXT PRIMARY KEY,
            manifest_json TEXT NOT NULL,
            imported_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE capability_okf_documents(
            path    TEXT PRIMARY KEY,
            content TEXT NOT NULL
        );
        CREATE TABLE capabilities(
            id                  TEXT NOT NULL,
            version             TEXT NOT NULL,
            purpose             TEXT NOT NULL,
            classification      TEXT NOT NULL,
            goals_json          TEXT NOT NULL,
            authority_json      TEXT NOT NULL,
            side_effects_json   TEXT NOT NULL,
            provenance_json     TEXT NOT NULL,
            failure_behavior    TEXT NOT NULL,
            rollback_behavior   TEXT,
            cost_json           TEXT NOT NULL,
            evidence_json       TEXT NOT NULL,
            implementations_json TEXT NOT NULL,
            tenth_man_json      TEXT NOT NULL,
            PRIMARY KEY(id, version)
        );
        CREATE TABLE capability_ports(
            capability_id      TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            direction          TEXT NOT NULL CHECK(direction IN ('input', 'output')),
            name               TEXT NOT NULL,
            schema_json        TEXT NOT NULL,
            PRIMARY KEY(capability_id, capability_version, direction, name),
            FOREIGN KEY(capability_id, capability_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE
        );
        CREATE TABLE capability_edges(
            source_id      TEXT NOT NULL,
            source_version TEXT NOT NULL,
            edge_type      TEXT NOT NULL,
            target_id      TEXT NOT NULL,
            target_version TEXT NOT NULL,
            PRIMARY KEY(source_id, source_version, edge_type, target_id, target_version),
            FOREIGN KEY(source_id, source_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE,
            FOREIGN KEY(target_id, target_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE
        );
        CREATE TABLE capability_implementations(
            id                 TEXT NOT NULL,
            version            TEXT NOT NULL,
            capability_id      TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            PRIMARY KEY(id, version),
            FOREIGN KEY(capability_id, capability_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE
        );
        CREATE TABLE capability_authorities(
            capability_id      TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            authority          TEXT NOT NULL,
            PRIMARY KEY(capability_id, capability_version, authority),
            FOREIGN KEY(capability_id, capability_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE
        );
        CREATE TABLE capability_plans(
            id               INTEGER PRIMARY KEY,
            goal             TEXT NOT NULL,
            authority_json   TEXT NOT NULL,
            head_sha         TEXT,
            status           TEXT NOT NULL,
            created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE capability_execution_steps(
            plan_id            INTEGER NOT NULL,
            position           INTEGER NOT NULL,
            capability_id      TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            implementation_id  TEXT NOT NULL,
            implementation_version TEXT NOT NULL,
            PRIMARY KEY(plan_id, position),
            FOREIGN KEY(plan_id) REFERENCES capability_plans(id) ON DELETE CASCADE
        );
        CREATE TABLE capability_evidence(
            id                     INTEGER PRIMARY KEY,
            capability_id          TEXT NOT NULL,
            capability_version     TEXT NOT NULL,
            implementation_id      TEXT NOT NULL,
            implementation_version TEXT NOT NULL,
            inputs_json            TEXT NOT NULL,
            outputs_json           TEXT NOT NULL,
            head_sha               TEXT,
            result                 TEXT NOT NULL,
            created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        5,
        """
        CREATE TABLE tool_publishers(
            key_id     TEXT PRIMARY KEY,
            public_key TEXT NOT NULL,
            owner      TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'trusted'
        );
        CREATE TABLE tool_manifests(
            tool_id       TEXT NOT NULL,
            version       TEXT NOT NULL,
            target        TEXT NOT NULL,
            implementation_id TEXT NOT NULL,
            digest         TEXT NOT NULL,
            manifest_json  TEXT NOT NULL,
            lifecycle      TEXT NOT NULL DEFAULT 'candidate',
            cache_path     TEXT,
            registered_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(tool_id, version, target)
        );
        CREATE TABLE tool_capabilities(
            tool_id            TEXT NOT NULL,
            tool_version       TEXT NOT NULL,
            target             TEXT NOT NULL,
            capability_id      TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            PRIMARY KEY(tool_id, tool_version, target, capability_id, capability_version),
            FOREIGN KEY(tool_id, tool_version, target)
                REFERENCES tool_manifests(tool_id, version, target) ON DELETE CASCADE
        );
        CREATE TABLE tool_audit(
            id         INTEGER PRIMARY KEY,
            event      TEXT NOT NULL,
            tool_id    TEXT NOT NULL,
            version    TEXT NOT NULL,
            target     TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        6,
        # SQLite cannot add a CHECK constraint in place, so rebuild the edge
        # projection while preserving every valid row from migration 4.
        """
        DROP TABLE IF EXISTS capability_edges_v6;
        CREATE TABLE capability_edges_v6(
            source_id      TEXT NOT NULL,
            source_version TEXT NOT NULL,
            edge_type      TEXT NOT NULL CHECK(edge_type IN (
                'requires', 'produces', 'validates', 'implements',
                'authorized_by', 'conflicts_with', 'may_follow',
                'can_rollback', 'escalates_to'
            )),
            target_id      TEXT NOT NULL,
            target_version TEXT NOT NULL,
            PRIMARY KEY(source_id, source_version, edge_type, target_id, target_version),
            FOREIGN KEY(source_id, source_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE,
            FOREIGN KEY(target_id, target_version)
                REFERENCES capabilities(id, version) ON DELETE CASCADE
        );
        INSERT INTO capability_edges_v6(
            source_id, source_version, edge_type, target_id, target_version
        )
        SELECT source_id, source_version, edge_type, target_id, target_version
        FROM capability_edges;
        DROP TABLE capability_edges;
        ALTER TABLE capability_edges_v6 RENAME TO capability_edges
        """,
    ),
    (
        7,
        # Enforce the same evidence states at the database boundary that the
        # planner accepts through CapabilityGraph.record_evidence.
        """
        DROP TABLE IF EXISTS capability_evidence_v7;
        CREATE TABLE capability_evidence_v7(
            id                     INTEGER PRIMARY KEY,
            capability_id          TEXT NOT NULL,
            capability_version     TEXT NOT NULL,
            implementation_id      TEXT NOT NULL,
            implementation_version TEXT NOT NULL,
            inputs_json            TEXT NOT NULL,
            outputs_json           TEXT NOT NULL,
            head_sha               TEXT,
            result                 TEXT NOT NULL CHECK(result IN ('success', 'failure')),
            created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO capability_evidence_v7(
            id, capability_id, capability_version, implementation_id,
            implementation_version, inputs_json, outputs_json, head_sha,
            result, created_at
        )
        SELECT id, capability_id, capability_version, implementation_id,
               implementation_version, inputs_json, outputs_json, head_sha,
               result, created_at
        FROM capability_evidence;
        DROP TABLE capability_evidence;
        ALTER TABLE capability_evidence_v7 RENAME TO capability_evidence
        """,
    ),
    (
        8,
        # Runtime lifecycle state and immutable invocation evidence. Runtime
        # configuration remains local; this is not a second tool registry.
        """
        CREATE TABLE capability_runtime_state (
            capability_id TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            implementation_id TEXT NOT NULL,
            implementation_version TEXT NOT NULL,
            lifecycle TEXT NOT NULL CHECK (
                lifecycle IN (
                    'proposed', 'implemented', 'isolated_test', 'adversarial_review',
                    'approved', 'active', 'suspended', 'retired'
                )
            ),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (capability_id, capability_version)
        );
        CREATE TABLE capability_invocations (
            invocation_id TEXT PRIMARY KEY,
            capability_id TEXT NOT NULL,
            capability_version TEXT NOT NULL,
            implementation_id TEXT,
            implementation_version TEXT,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('success', 'failure')),
            started_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
            provenance_json TEXT NOT NULL,
            side_effects_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL
        );
        CREATE TRIGGER capability_invocations_no_update
        BEFORE UPDATE ON capability_invocations
        BEGIN
            SELECT RAISE(ABORT, 'capability invocations are append-only');
        END;
        CREATE TRIGGER capability_invocations_no_delete
        BEFORE DELETE ON capability_invocations
        BEGIN
            SELECT RAISE(ABORT, 'capability invocations are append-only');
        END;
        """,
    ),
    (
        9,
        # Versioned bounded missions, durable step progress, human approvals,
        # and append-only transition history.
        """
        CREATE TABLE IF NOT EXISTS missions(
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            success_condition TEXT NOT NULL,
            risk REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE missions ADD COLUMN contract_version TEXT;
        ALTER TABLE missions ADD COLUMN contract_json TEXT;
        ALTER TABLE missions ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
        CREATE TABLE mission_steps (
            mission_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            step_id TEXT NOT NULL,
            request_json TEXT NOT NULL,
            rollback_json TEXT,
            irreversible INTEGER NOT NULL CHECK(irreversible IN (0, 1)),
            status TEXT NOT NULL CHECK(status IN (
                'pending', 'running', 'completed', 'failed', 'uncertain',
                'rollback_running', 'rolled_back'
            )),
            invocation_id TEXT,
            result_json TEXT,
            PRIMARY KEY(mission_id, position),
            UNIQUE(mission_id, step_id),
            FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
        );
        CREATE TABLE mission_transitions (
            id INTEGER PRIMARY KEY,
            mission_id INTEGER NOT NULL,
            from_state TEXT,
            to_state TEXT NOT NULL,
            reason TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
        );
        CREATE TABLE mission_approvals (
            id INTEGER PRIMARY KEY,
            mission_id INTEGER NOT NULL,
            request_key TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN (
                'initial_authorization', 'authority_expansion', 'irreversible_action'
            )),
            decision TEXT NOT NULL CHECK(decision IN ('requested', 'approved', 'denied')),
            detail_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
        );
        CREATE TRIGGER mission_transitions_no_update
        BEFORE UPDATE ON mission_transitions BEGIN
            SELECT RAISE(ABORT, 'mission transitions are append-only');
        END;
        CREATE TRIGGER mission_transitions_no_delete
        BEFORE DELETE ON mission_transitions BEGIN
            SELECT RAISE(ABORT, 'mission transitions are append-only');
        END;
        CREATE TRIGGER mission_approvals_no_update
        BEFORE UPDATE ON mission_approvals BEGIN
            SELECT RAISE(ABORT, 'mission approvals are append-only');
        END;
        CREATE TRIGGER mission_approvals_no_delete
        BEFORE DELETE ON mission_approvals BEGIN
            SELECT RAISE(ABORT, 'mission approvals are append-only');
        END;
        """,
    ),
]


def _split_statements(sql: str) -> list[str]:
    """Split SQL while preserving compound statements such as triggers."""
    statements: list[str] = []
    pending = ""
    for line in sql.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            statements.append(pending.strip())
            pending = ""
    if pending.strip():
        statements.append(pending.strip())
    return statements


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
            db.execute("BEGIN")
            for stmt in _split_statements(sql):
                db.execute(stmt)
            db.execute(
                "INSERT INTO schema_version(version) VALUES(?)",
                (version,),
            )
        newly_applied.append(version)

    return newly_applied
