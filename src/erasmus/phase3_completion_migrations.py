from __future__ import annotations

import sqlite3


COMPLETION_MIGRATIONS: list[tuple[int, str]] = [
    (
        22,
        """
        CREATE TABLE knowledge_concept_transitions(
            transition_id TEXT PRIMARY KEY,
            concept_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(concept_id) REFERENCES knowledge_concepts(concept_id),
            FOREIGN KEY(revision_id) REFERENCES knowledge_concept_revisions(revision_id)
        );
        CREATE TRIGGER knowledge_concept_transitions_no_update
        BEFORE UPDATE ON knowledge_concept_transitions
        BEGIN SELECT RAISE(ABORT, 'concept transitions are append-only'); END;
        CREATE TRIGGER knowledge_concept_transitions_no_delete
        BEFORE DELETE ON knowledge_concept_transitions
        BEGIN SELECT RAISE(ABORT, 'concept transitions are append-only'); END;

        CREATE TABLE knowledge_publication_receipts(
            receipt_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL UNIQUE,
            channel_id TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            file_digests_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(snapshot_id)
        );
        CREATE TRIGGER knowledge_publication_receipts_no_update
        BEFORE UPDATE ON knowledge_publication_receipts
        BEGIN SELECT RAISE(ABORT, 'publication receipts are append-only'); END;
        CREATE TRIGGER knowledge_publication_receipts_no_delete
        BEFORE DELETE ON knowledge_publication_receipts
        BEGIN SELECT RAISE(ABORT, 'publication receipts are append-only'); END;

        CREATE TABLE knowledge_vector_rows(
            projection_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            norm REAL NOT NULL CHECK(norm > 0),
            PRIMARY KEY(projection_id, claim_id),
            FOREIGN KEY(projection_id) REFERENCES knowledge_projection_manifests(projection_id) ON DELETE CASCADE,
            FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(snapshot_id)
        );
        CREATE TABLE knowledge_graph_edges(
            projection_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            derived INTEGER NOT NULL CHECK(derived IN (0,1)),
            PRIMARY KEY(projection_id, source_type, source_id, predicate, target_type, target_id),
            FOREIGN KEY(projection_id) REFERENCES knowledge_projection_manifests(projection_id) ON DELETE CASCADE,
            FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(snapshot_id)
        );

        CREATE TABLE knowledge_freshness_assessments(
            assessment_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            freshness_state TEXT NOT NULL CHECK(freshness_state IN (
                'current','approaching_stale','stale','unknown','source_unavailable'
            )),
            materiality TEXT NOT NULL CHECK(materiality IN ('routine','consequential','protected')),
            stale_after TEXT,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id)
        );
        CREATE TRIGGER knowledge_freshness_assessments_no_update
        BEFORE UPDATE ON knowledge_freshness_assessments
        BEGIN SELECT RAISE(ABORT, 'freshness assessments are append-only'); END;
        CREATE TRIGGER knowledge_freshness_assessments_no_delete
        BEFORE DELETE ON knowledge_freshness_assessments
        BEGIN SELECT RAISE(ABORT, 'freshness assessments are append-only'); END;

        CREATE TABLE knowledge_dependencies(
            dependency_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_type, source_id, target_type, target_id, relation)
        );
        CREATE TRIGGER knowledge_dependencies_no_update
        BEFORE UPDATE ON knowledge_dependencies
        BEGIN SELECT RAISE(ABORT, 'knowledge dependencies are append-only'); END;
        CREATE TRIGGER knowledge_dependencies_no_delete
        BEFORE DELETE ON knowledge_dependencies
        BEGIN SELECT RAISE(ABORT, 'knowledge dependencies are append-only'); END;

        CREATE TABLE knowledge_intake_control(
            id INTEGER PRIMARY KEY CHECK(id = 1),
            enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
            actor TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO knowledge_intake_control(id, enabled, actor)
        VALUES(1, 1, 'process:bootstrap');
        CREATE TABLE knowledge_intake_queue(
            intake_id TEXT PRIMARY KEY,
            producer TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            disposition TEXT NOT NULL CHECK(disposition IN ('quarantined','admissible','rejected')),
            state TEXT NOT NULL CHECK(state IN ('queued','processing','completed','failed','cancelled')),
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(producer, payload_digest)
        );

        CREATE TABLE knowledge_route_decisions(
            route_id TEXT PRIMARY KEY,
            selected_route TEXT NOT NULL,
            packet_id TEXT NOT NULL,
            claim_ids_json TEXT NOT NULL,
            source_ids_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_route_outcomes(
            outcome_id TEXT PRIMARY KEY,
            route_id TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome IN ('success','failure','cancelled')),
            detail_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(route_id) REFERENCES knowledge_route_decisions(route_id)
        );
        CREATE TRIGGER knowledge_route_decisions_no_update BEFORE UPDATE ON knowledge_route_decisions
        BEGIN SELECT RAISE(ABORT, 'route decisions are append-only'); END;
        CREATE TRIGGER knowledge_route_decisions_no_delete BEFORE DELETE ON knowledge_route_decisions
        BEGIN SELECT RAISE(ABORT, 'route decisions are append-only'); END;
        CREATE TRIGGER knowledge_route_outcomes_no_update BEFORE UPDATE ON knowledge_route_outcomes
        BEGIN SELECT RAISE(ABORT, 'route outcomes are append-only'); END;
        CREATE TRIGGER knowledge_route_outcomes_no_delete BEFORE DELETE ON knowledge_route_outcomes
        BEGIN SELECT RAISE(ABORT, 'route outcomes are append-only'); END;
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


def apply_phase3_completion(db: sqlite3.Connection) -> list[int]:
    applied = {row[0] for row in db.execute("SELECT version FROM schema_version")}
    newly_applied: list[int] = []
    for version, sql in COMPLETION_MIGRATIONS:
        if version in applied:
            continue
        with db:
            db.execute("BEGIN")
            for statement in _split_statements(sql):
                db.execute(statement)
            db.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        newly_applied.append(version)
    return newly_applied
