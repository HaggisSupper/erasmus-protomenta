from __future__ import annotations

import sqlite3


PHASE3_MIGRATIONS: list[tuple[int, str]] = [
    (
        17,
        """
        CREATE TABLE knowledge_policy_sets(
            policy_set_id TEXT PRIMARY KEY,
            digest TEXT NOT NULL UNIQUE,
            rules_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('inactive','active','retired')) DEFAULT 'inactive',
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_policy_receipts(
            receipt_id TEXT PRIMARY KEY,
            policy_set_id TEXT,
            policy_digest TEXT,
            operation TEXT NOT NULL,
            actor TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('permit','deny')),
            matched_rules_json TEXT NOT NULL,
            dry_run INTEGER NOT NULL CHECK(dry_run IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_semantic_registry(
            registry_id TEXT PRIMARY KEY,
            digest TEXT NOT NULL UNIQUE,
            definitions_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('inactive','active','retired')) DEFAULT 'inactive',
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_publication_channels(
            channel_id TEXT PRIMARY KEY,
            scope_json TEXT NOT NULL,
            audience TEXT NOT NULL,
            current_snapshot_id TEXT,
            state TEXT NOT NULL CHECK(state IN ('active','suspended','retired')) DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_jobs(
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            request_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('queued','running','completed','failed','cancelled')),
            result_json TEXT,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );
        """,
    ),
    (
        18,
        """
        CREATE TABLE knowledge_sources(
            source_id TEXT PRIMARY KEY,
            digest TEXT NOT NULL UNIQUE,
            locator TEXT NOT NULL,
            media_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
            scope_json TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            tombstoned INTEGER NOT NULL CHECK(tombstoned IN (0,1)) DEFAULT 0,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_source_spans(
            span_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            coordinate_json TEXT NOT NULL,
            text_digest TEXT NOT NULL,
            extracted_text TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id)
        );
        CREATE TABLE knowledge_candidates(
            candidate_id TEXT PRIMARY KEY,
            producer TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_ids_json TEXT NOT NULL,
            source_span_ids_json TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            candidate_disposition TEXT NOT NULL CHECK(candidate_disposition IN ('quarantined','admissible','duplicate','insufficient_evidence','rejected')),
            content_digest TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX knowledge_candidates_content_identity
            ON knowledge_candidates(producer, content_digest, scope_json);
        CREATE TABLE knowledge_candidate_claims(
            candidate_claim_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            statement TEXT NOT NULL,
            source_span_ids_json TEXT NOT NULL,
            qualifiers_json TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            risk_class TEXT NOT NULL CHECK(risk_class IN ('routine','consequential','protected')),
            content_digest TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, content_digest),
            FOREIGN KEY(candidate_id) REFERENCES knowledge_candidates(candidate_id)
        );
        CREATE TABLE knowledge_entities(
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            retired INTEGER NOT NULL CHECK(retired IN (0,1)) DEFAULT 0,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_entity_aliases(
            alias_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            namespace TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(entity_id) REFERENCES knowledge_entities(entity_id)
        );
        CREATE INDEX knowledge_entity_alias_lookup ON knowledge_entity_aliases(alias, namespace);
        CREATE TABLE knowledge_identity_decisions(
            decision_id TEXT PRIMARY KEY,
            left_entity_id TEXT NOT NULL,
            right_entity_id TEXT NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('same_entity','distinct_entity','alias_of','successor_of','version_of','part_of','unresolved')),
            rationale TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(left_entity_id) REFERENCES knowledge_entities(entity_id),
            FOREIGN KEY(right_entity_id) REFERENCES knowledge_entities(entity_id)
        );
        """,
    ),
    (
        19,
        """
        CREATE TABLE knowledge_reconciliation_decisions(
            decision_id TEXT PRIMARY KEY,
            candidate_claim_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('create','corroborate','amend','contradict','supersede','duplicate','reject','insufficient_evidence')),
            target_proposition_ids_json TEXT NOT NULL,
            mission_id INTEGER NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            actor TEXT NOT NULL,
            authority TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_claim_id) REFERENCES knowledge_candidate_claims(candidate_claim_id)
        );
        CREATE TABLE knowledge_claim_bindings(
            binding_id TEXT PRIMARY KEY,
            candidate_claim_id TEXT NOT NULL,
            proposition_id INTEGER NOT NULL,
            relation TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(candidate_claim_id) REFERENCES knowledge_candidate_claims(candidate_claim_id),
            FOREIGN KEY(proposition_id) REFERENCES propositions(id),
            FOREIGN KEY(decision_id) REFERENCES knowledge_reconciliation_decisions(decision_id)
        );
        CREATE TABLE knowledge_concepts(
            concept_id TEXT PRIMARY KEY,
            concept_type TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            concept_lifecycle TEXT NOT NULL CHECK(concept_lifecycle IN ('provisional','reviewed','validated','contested','canonical','superseded','rejected','deprecated')) DEFAULT 'provisional',
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_concept_revisions(
            revision_id TEXT PRIMARY KEY,
            concept_id TEXT NOT NULL,
            revision_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            claim_ids_json TEXT NOT NULL,
            relationship_ids_json TEXT NOT NULL,
            okf_path TEXT NOT NULL,
            content_digest TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(concept_id, revision_number),
            FOREIGN KEY(concept_id) REFERENCES knowledge_concepts(concept_id)
        );
        CREATE TABLE knowledge_relationships(
            relationship_id TEXT PRIMARY KEY,
            source_concept_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            target_concept_id TEXT NOT NULL,
            qualifiers_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_concept_id) REFERENCES knowledge_concepts(concept_id),
            FOREIGN KEY(target_concept_id) REFERENCES knowledge_concepts(concept_id)
        );
        CREATE TABLE knowledge_reviews(
            review_id TEXT PRIMARY KEY,
            revision_id TEXT NOT NULL,
            review_type TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('pass','pass_with_conditions','fail','insufficient_evidence')),
            reviewer TEXT NOT NULL,
            producer TEXT NOT NULL,
            inputs_digest TEXT NOT NULL,
            authority TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(revision_id) REFERENCES knowledge_concept_revisions(revision_id)
        );
        CREATE TABLE knowledge_questions(
            question_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            related_claim_ids_json TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            question_state TEXT NOT NULL CHECK(question_state IN ('open','researching','blocked','answered','rejected')) DEFAULT 'open',
            answer_claim_ids_json TEXT NOT NULL DEFAULT '[]',
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_syntheses(
            synthesis_id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            input_claim_ids_json TEXT NOT NULL,
            interpretations_json TEXT NOT NULL,
            claim_states_json TEXT NOT NULL,
            scope_json TEXT NOT NULL,
            synthesis_lifecycle TEXT NOT NULL CHECK(synthesis_lifecycle IN ('provisional','reviewed','validated','canonical','superseded','rejected')) DEFAULT 'provisional',
            inputs_digest TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
    (
        20,
        """
        CREATE TABLE knowledge_snapshots(
            snapshot_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            revision_ids_json TEXT NOT NULL,
            root_path TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            snapshot_state TEXT NOT NULL CHECK(snapshot_state IN ('building','validated','approved','published','withdrawn','failed')),
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, sequence),
            FOREIGN KEY(channel_id) REFERENCES knowledge_publication_channels(channel_id)
        );
        CREATE TABLE knowledge_projection_manifests(
            projection_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK(kind IN ('fts','vector','graph','cache','ui')),
            source_snapshot_id TEXT NOT NULL,
            projection_state TEXT NOT NULL CHECK(projection_state IN ('queued','building','ready','failed','stale','retired')),
            configuration_json TEXT NOT NULL,
            artifact_digest TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_snapshot_id) REFERENCES knowledge_snapshots(snapshot_id)
        );
        CREATE TABLE knowledge_fts_documents(
            snapshot_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            PRIMARY KEY(snapshot_id, revision_id, claim_id),
            FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(snapshot_id)
        );
        CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            snapshot_id UNINDEXED,
            revision_id UNINDEXED,
            concept_id UNINDEXED,
            claim_id UNINDEXED,
            title,
            body
        );
        CREATE TABLE knowledge_serving_directives(
            directive_id TEXT PRIMARY KEY,
            action TEXT NOT NULL CHECK(action IN ('qualify','exclude','block','channel_suspend')),
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            channel_id TEXT,
            reason TEXT NOT NULL,
            active INTEGER NOT NULL CHECK(active IN (0,1)) DEFAULT 1,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_use_receipts(
            receipt_id TEXT PRIMARY KEY,
            packet_id TEXT NOT NULL UNIQUE,
            channel_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            item_ids_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE knowledge_invalidation_events(
            invalidation_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TRIGGER knowledge_policy_receipts_no_update BEFORE UPDATE ON knowledge_policy_receipts
        BEGIN SELECT RAISE(ABORT, 'knowledge policy receipts are append-only'); END;
        CREATE TRIGGER knowledge_policy_receipts_no_delete BEFORE DELETE ON knowledge_policy_receipts
        BEGIN SELECT RAISE(ABORT, 'knowledge policy receipts are append-only'); END;
        CREATE TRIGGER knowledge_identity_decisions_no_update BEFORE UPDATE ON knowledge_identity_decisions
        BEGIN SELECT RAISE(ABORT, 'identity decisions are append-only'); END;
        CREATE TRIGGER knowledge_reconciliation_decisions_no_update BEFORE UPDATE ON knowledge_reconciliation_decisions
        BEGIN SELECT RAISE(ABORT, 'reconciliation decisions are append-only'); END;
        CREATE TRIGGER knowledge_reviews_no_update BEFORE UPDATE ON knowledge_reviews
        BEGIN SELECT RAISE(ABORT, 'knowledge reviews are append-only'); END;
        CREATE TRIGGER knowledge_snapshots_no_update BEFORE UPDATE ON knowledge_snapshots
        BEGIN SELECT RAISE(ABORT, 'knowledge snapshots are immutable'); END;
        CREATE TRIGGER knowledge_use_receipts_no_update BEFORE UPDATE ON knowledge_use_receipts
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


def apply_phase3_migrations(db: sqlite3.Connection) -> list[int]:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version(
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()
    applied = {row[0] for row in db.execute("SELECT version FROM schema_version")}
    newly_applied: list[int] = []
    for version, sql in PHASE3_MIGRATIONS:
        if version in applied:
            continue
        with db:
            db.execute("BEGIN")
            for statement in _split_statements(sql):
                db.execute(statement)
            db.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        newly_applied.append(version)
    return newly_applied
