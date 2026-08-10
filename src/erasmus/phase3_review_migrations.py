from __future__ import annotations

import sqlite3


REVIEW_MIGRATIONS: list[tuple[int, str]] = [
    (
        23,
        """
        CREATE TABLE knowledge_candidate_transitions(
            transition_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            from_disposition TEXT NOT NULL CHECK(from_disposition IN (
                'quarantined','admissible','duplicate','insufficient_evidence','rejected'
            )),
            to_disposition TEXT NOT NULL CHECK(to_disposition IN (
                'quarantined','admissible','duplicate','insufficient_evidence','rejected'
            )),
            mission_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            policy_receipt_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_id) REFERENCES knowledge_candidates(candidate_id),
            FOREIGN KEY(policy_receipt_id) REFERENCES knowledge_policy_receipts(receipt_id)
        );
        CREATE TRIGGER knowledge_candidate_transitions_no_update
        BEFORE UPDATE ON knowledge_candidate_transitions
        BEGIN SELECT RAISE(ABORT, 'candidate transitions are append-only'); END;
        CREATE TRIGGER knowledge_candidate_transitions_no_delete
        BEFORE DELETE ON knowledge_candidate_transitions
        BEGIN SELECT RAISE(ABORT, 'candidate transitions are append-only'); END;

        CREATE TABLE knowledge_snapshot_claims(
            snapshot_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            statement TEXT NOT NULL,
            epistemic_status TEXT NOT NULL CHECK(epistemic_status IN (
                'established','supported','plausible','speculative','analogy',
                'leap','contradicted','falsified','unresolved'
            )),
            confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
            evidence_json TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            captured_transition_id INTEGER,
            PRIMARY KEY(snapshot_id, claim_id),
            FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(snapshot_id),
            FOREIGN KEY(revision_id) REFERENCES knowledge_concept_revisions(revision_id),
            FOREIGN KEY(concept_id) REFERENCES knowledge_concepts(concept_id),
            FOREIGN KEY(claim_id) REFERENCES propositions(id)
        );
        CREATE TRIGGER knowledge_snapshot_claims_no_update
        BEFORE UPDATE ON knowledge_snapshot_claims
        BEGIN SELECT RAISE(ABORT, 'snapshot claims are immutable'); END;
        CREATE TRIGGER knowledge_snapshot_claims_no_delete
        BEFORE DELETE ON knowledge_snapshot_claims
        BEGIN SELECT RAISE(ABORT, 'snapshot claims are immutable'); END;

        CREATE TABLE knowledge_mutation_audit(
            audit_id TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            mission_id INTEGER,
            idempotency_key TEXT,
            policy_receipt_id TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('accepted','rejected','noop')),
            detail_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(policy_receipt_id) REFERENCES knowledge_policy_receipts(receipt_id)
        );
        CREATE TRIGGER knowledge_mutation_audit_no_update
        BEFORE UPDATE ON knowledge_mutation_audit
        BEGIN SELECT RAISE(ABORT, 'knowledge mutation audit is append-only'); END;
        CREATE TRIGGER knowledge_mutation_audit_no_delete
        BEFORE DELETE ON knowledge_mutation_audit
        BEGIN SELECT RAISE(ABORT, 'knowledge mutation audit is append-only'); END;

        ALTER TABLE knowledge_sources ADD COLUMN policy_receipt_id TEXT
            REFERENCES knowledge_policy_receipts(receipt_id);
        ALTER TABLE knowledge_sources ADD COLUMN mission_id INTEGER;

        CREATE INDEX knowledge_snapshot_claims_revision
            ON knowledge_snapshot_claims(snapshot_id, revision_id);
        CREATE INDEX knowledge_candidate_transition_latest
            ON knowledge_candidate_transitions(candidate_id, created_at);
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


def apply_phase3_review_migrations(db: sqlite3.Connection) -> list[int]:
    applied = {row[0] for row in db.execute("SELECT version FROM schema_version")}
    newly_applied: list[int] = []
    for version, sql in REVIEW_MIGRATIONS:
        if version in applied:
            continue
        with db:
            db.execute("BEGIN")
            for statement in _split_statements(sql):
                db.execute(statement)
            db.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        newly_applied.append(version)
    return newly_applied
