from __future__ import annotations

import sqlite3


HARDENING_MIGRATIONS: list[tuple[int, str]] = [
    (
        21,
        """
        ALTER TABLE knowledge_sources
            ADD COLUMN authority TEXT NOT NULL DEFAULT 'knowledge:source-register';
        ALTER TABLE knowledge_sources
            ADD COLUMN idempotency_key TEXT;
        UPDATE knowledge_sources
            SET idempotency_key = source_id
            WHERE idempotency_key IS NULL;
        CREATE UNIQUE INDEX knowledge_sources_idempotency
            ON knowledge_sources(idempotency_key);

        CREATE TRIGGER knowledge_sources_fill_idempotency
        AFTER INSERT ON knowledge_sources
        WHEN NEW.idempotency_key IS NULL
        BEGIN
            UPDATE knowledge_sources
            SET idempotency_key = NEW.source_id
            WHERE source_id = NEW.source_id;
        END;

        CREATE TRIGGER knowledge_sources_scope_conflict
        BEFORE INSERT ON knowledge_sources
        WHEN EXISTS(
            SELECT 1 FROM knowledge_sources existing
            WHERE existing.source_id = NEW.source_id
              AND existing.scope_json != NEW.scope_json
        )
        BEGIN
            SELECT RAISE(ABORT, 'source digest is already registered in a different scope');
        END;

        CREATE TRIGGER knowledge_source_spans_scope_conflict
        BEFORE INSERT ON knowledge_source_spans
        WHEN EXISTS(
            SELECT 1 FROM knowledge_sources source
            WHERE source.source_id = NEW.source_id
              AND source.scope_json != NEW.scope_json
        ) OR EXISTS(
            SELECT 1 FROM knowledge_source_spans existing
            WHERE existing.span_id = NEW.span_id
              AND existing.scope_json != NEW.scope_json
        )
        BEGIN
            SELECT RAISE(ABORT, 'source span scope must match its immutable source scope');
        END;

        CREATE TRIGGER knowledge_identity_decisions_no_delete
        BEFORE DELETE ON knowledge_identity_decisions
        BEGIN SELECT RAISE(ABORT, 'identity decisions are append-only'); END;
        CREATE TRIGGER knowledge_reconciliation_decisions_no_delete
        BEFORE DELETE ON knowledge_reconciliation_decisions
        BEGIN SELECT RAISE(ABORT, 'reconciliation decisions are append-only'); END;
        CREATE TRIGGER knowledge_reviews_no_delete
        BEFORE DELETE ON knowledge_reviews
        BEGIN SELECT RAISE(ABORT, 'knowledge reviews are append-only'); END;
        CREATE TRIGGER knowledge_snapshots_no_delete
        BEFORE DELETE ON knowledge_snapshots
        BEGIN SELECT RAISE(ABORT, 'knowledge snapshots are immutable'); END;
        CREATE TRIGGER knowledge_use_receipts_no_delete
        BEFORE DELETE ON knowledge_use_receipts
        BEGIN SELECT RAISE(ABORT, 'knowledge use receipts are append-only'); END;
        """,
    ),
]


def _split_statements(sql: str) -> list[str]:
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


def apply_phase3_hardening(db: sqlite3.Connection) -> list[int]:
    applied = {row[0] for row in db.execute("SELECT version FROM schema_version")}
    newly_applied: list[int] = []
    for version, sql in HARDENING_MIGRATIONS:
        if version in applied:
            continue
        with db:
            db.execute("BEGIN")
            for statement in _split_statements(sql):
                db.execute(statement)
            db.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        newly_applied.append(version)
    return newly_applied
