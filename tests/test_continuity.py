"""Tests for durable continuity and recovery (Mission 01).

Coverage:
- Migration runner applies exactly once, is auditable, and repair migration runs.
- Checkpoint roundtrip: save and load with all fields intact.
- Checkpoint provenance: source_event_ids must be non-empty and reference real events.
- Resume after simulated process restart (close and reopen DB).
- Invalid checkpoint is rejected before any write.
- Interrupted sleep is idempotent and does not duplicate candidates.
- Partially written checkpoint (rolled-back transaction) does not corrupt state.
- Session lifecycle: start, end, and interrupted-session detection.
- CLI backup and restore reproduce the same active state.
- integrity_check returns 'ok' on a clean database.
- experience_candidates rows carry non-empty created_at timestamps.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from erasmus.checkpoint import Checkpoint, load_latest_checkpoint, save_checkpoint
from erasmus.migrations import apply_migrations
from erasmus.sleep import consolidate
from erasmus.store import Store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path, name: str = "e.db") -> Store:
    store = Store(str(tmp_path / name))
    store.init()
    return store


def _minimal_checkpoint(**overrides) -> Checkpoint:
    """Build a minimal valid Checkpoint.

    Callers that intend to persist the checkpoint via save_checkpoint() MUST
    supply source_event_ids containing ids of real events in the store.
    """
    defaults = dict(
        frontier="active reasoning boundary",
        proposition="X causes Y under condition Z",
        strongest_support="experiment A confirms causal link",
        strongest_contradiction="counterexample B breaks causal chain",
        unresolved_tension="timing ambiguity between A and B unresolved",
        active_mode="dialogue",
        next_move="seek clarifying evidence for timing",
    )
    defaults.update(overrides)
    return Checkpoint(**defaults)


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

class TestMigrations:
    def test_migrations_apply_to_fresh_db(self, tmp_path):
        db = sqlite3.connect(str(tmp_path / "m.db"))
        applied = apply_migrations(db)
        assert 1 in applied
        assert 2 in applied
        assert 3 in applied
        db.close()

    def test_migrations_apply_exactly_once(self, tmp_path):
        db = sqlite3.connect(str(tmp_path / "m.db"))
        first = apply_migrations(db)
        second = apply_migrations(db)
        assert len(first) > 0
        assert second == []
        db.close()

    def test_migrations_auditable_in_schema_version(self, tmp_path):
        db = sqlite3.connect(str(tmp_path / "m.db"))
        db.row_factory = sqlite3.Row
        apply_migrations(db)
        rows = db.execute(
            "SELECT version, applied_at FROM schema_version ORDER BY version"
        ).fetchall()
        versions = [r["version"] for r in rows]
        assert 1 in versions
        assert 2 in versions
        assert 3 in versions
        for row in rows:
            assert row["applied_at"]  # provenance timestamp is present
        db.close()

    def test_migration_2_creates_sessions_and_sleep_progress(self, tmp_path):
        store = _make_store(tmp_path)
        store.db.execute("SELECT id FROM sessions LIMIT 1")
        store.db.execute("SELECT id FROM sleep_progress LIMIT 1")

    def test_migration_2_adds_checkpoint_columns(self, tmp_path):
        store = _make_store(tmp_path)
        cols = {
            row[1]
            for row in store.db.execute("PRAGMA table_info(checkpoints)").fetchall()
        }
        expected = {
            "id", "frontier", "next_move", "created_at",
            "proposition", "strongest_support", "strongest_contradiction",
            "unresolved_tension", "active_mode", "pending_leap",
            "relevant_tangible_wrongness", "source_event_ids",
        }
        assert expected.issubset(cols)

    def test_migration_3_repairs_empty_created_at(self, tmp_path):
        """Migration 3 must update any experience_candidates with empty created_at."""
        db_path = str(tmp_path / "repair.db")
        # Simulate a database that went through the old migration 2 (DEFAULT '').
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS schema_version(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experience_candidates(
                id INTEGER PRIMARY KEY,
                lesson TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'candidate',
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS checkpoints(
                id INTEGER PRIMARY KEY,
                frontier TEXT NOT NULL,
                next_move TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_version(version) VALUES(1);
            INSERT INTO schema_version(version) VALUES(2);
            INSERT INTO experience_candidates(lesson, created_at) VALUES('old lesson', '');
            """
        )
        db.commit()
        db.close()

        # Opening via Store triggers migration 3, which repairs the empty value.
        store = Store(db_path)
        store.init()
        row = store.db.execute(
            "SELECT created_at FROM experience_candidates WHERE lesson = 'old lesson'"
        ).fetchone()
        assert row["created_at"] != ""

    def test_migration_idempotent_on_existing_db(self, tmp_path):
        """Applying migrations to a database that already has the base tables
        must not raise and must not duplicate schema_version rows."""
        db_path = str(tmp_path / "existing.db")
        db = sqlite3.connect(db_path)
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints(
                id INTEGER PRIMARY KEY,
                frontier TEXT NOT NULL,
                next_move TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        db.commit()
        db.close()

        store = Store(db_path)
        store.init()  # must not raise

        count = store.db.execute(
            "SELECT COUNT(*) FROM schema_version"
        ).fetchone()[0]
        assert count == 7  # exactly seven migrations recorded

    def test_real_premission01_upgrade(self, tmp_path):
        """Upgrade from a genuine pre-Mission-01 database with existing data.

        Constructs a real pre-Mission-01 database (migration 1 schema, no
        created_at on experience_candidates), runs the full migration sequence,
        and proves: migration success, timestamp population, schema-version
        auditability, reopen success, and idempotent re-run.
        """
        db_path = str(tmp_path / "premission01.db")

        # Build a genuine pre-Mission-01 database: migration-1 schema only,
        # with an existing experience_candidates row that has no created_at column.
        db = sqlite3.connect(db_path)
        db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS schema_version(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS propositions(
                id INTEGER PRIMARY KEY,
                statement TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS missions(
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                success_condition TEXT NOT NULL,
                risk REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'proposed',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS experience_candidates(
                id INTEGER PRIMARY KEY,
                lesson TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'candidate'
            );
            CREATE TABLE IF NOT EXISTS immune_state(
                id INTEGER PRIMARY KEY,
                agent_id TEXT NOT NULL,
                signature TEXT NOT NULL,
                state_json TEXT NOT NULL,
                wake_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'sleeping',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS checkpoints(
                id INTEGER PRIMARY KEY,
                frontier TEXT NOT NULL,
                next_move TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_version(version) VALUES(1);
            INSERT INTO experience_candidates(lesson) VALUES('pre-mission lesson');
            """
        )
        db.commit()
        db.close()

        # Apply migrations via Store — must not raise.
        store = Store(db_path)
        store.init()

        # Schema-version auditability: all three versions recorded exactly once.
        rows = store.db.execute(
            "SELECT version, applied_at FROM schema_version ORDER BY version"
        ).fetchall()
        versions = [r[0] for r in rows]
        assert versions == [1, 2, 3, 4, 5, 6, 7]
        for r in rows:
            assert r[1]  # applied_at provenance timestamp present

        # Timestamp population: the pre-existing row must have a non-empty created_at.
        row = store.db.execute(
            "SELECT created_at FROM experience_candidates"
            " WHERE lesson = 'pre-mission lesson'"
        ).fetchone()
        assert row is not None
        assert row[0] not in ("", None)

        store.db.close()

        # Reopen success: second Store init must not raise or duplicate rows.
        store2 = Store(db_path)
        store2.init()
        count = store2.db.execute(
            "SELECT COUNT(*) FROM schema_version"
        ).fetchone()[0]
        assert count == 7  # still exactly seven, not duplicated

        # Idempotent re-run: applying migrations again must return empty list.
        applied = apply_migrations(store2.db)
        assert applied == []


# ---------------------------------------------------------------------------
# Checkpoint tests
# ---------------------------------------------------------------------------

class TestCheckpoint:
    def test_checkpoint_roundtrip_all_fields(self, tmp_path):
        store = _make_store(tmp_path)
        event_id = store.add_event("observation", "first observation")

        cp = _minimal_checkpoint(
            pending_leap="leap hypothesis not yet tested",
            relevant_tangible_wrongness="prediction C was falsified last session",
            source_event_ids=[event_id],
        )
        save_checkpoint(store, cp)
        loaded = load_latest_checkpoint(store)

        assert loaded is not None
        assert loaded.frontier == cp.frontier
        assert loaded.proposition == cp.proposition
        assert loaded.strongest_support == cp.strongest_support
        assert loaded.strongest_contradiction == cp.strongest_contradiction
        assert loaded.unresolved_tension == cp.unresolved_tension
        assert loaded.active_mode == cp.active_mode
        assert loaded.next_move == cp.next_move
        assert loaded.pending_leap == cp.pending_leap
        assert loaded.relevant_tangible_wrongness == cp.relevant_tangible_wrongness
        assert loaded.source_event_ids == [event_id]

    def test_checkpoint_optional_text_fields_default_to_none(self, tmp_path):
        """pending_leap and relevant_tangible_wrongness are nullable."""
        store = _make_store(tmp_path)
        event_id = store.add_event("obs", "seed event")
        save_checkpoint(store, _minimal_checkpoint(source_event_ids=[event_id]))
        loaded = load_latest_checkpoint(store)
        assert loaded is not None
        assert loaded.pending_leap is None
        assert loaded.relevant_tangible_wrongness is None

    def test_load_returns_none_when_no_checkpoints(self, tmp_path):
        store = _make_store(tmp_path)
        assert load_latest_checkpoint(store) is None

    def test_load_returns_latest_checkpoint(self, tmp_path):
        store = _make_store(tmp_path)
        id1 = store.add_event("obs", "e1")
        id2 = store.add_event("obs", "e2")
        save_checkpoint(store, _minimal_checkpoint(frontier="first frontier", source_event_ids=[id1]))
        save_checkpoint(store, _minimal_checkpoint(frontier="second frontier", source_event_ids=[id2]))
        loaded = load_latest_checkpoint(store)
        assert loaded is not None
        assert loaded.frontier == "second frontier"

    def test_source_event_ids_are_integers(self, tmp_path):
        store = _make_store(tmp_path)
        ids = [store.add_event("obs", f"event {i}") for i in range(3)]
        save_checkpoint(store, _minimal_checkpoint(source_event_ids=ids))
        loaded = load_latest_checkpoint(store)
        assert loaded is not None
        assert all(isinstance(i, int) for i in loaded.source_event_ids)
        assert loaded.source_event_ids == ids


# ---------------------------------------------------------------------------
# Validation tests (negative)
# ---------------------------------------------------------------------------

class TestCheckpointValidation:
    @pytest.mark.parametrize("field_name", [
        "frontier",
        "proposition",
        "strongest_support",
        "strongest_contradiction",
        "unresolved_tension",
        "active_mode",
        "next_move",
    ])
    def test_empty_required_field_raises(self, tmp_path, field_name):
        store = _make_store(tmp_path)
        event_id = store.add_event("obs", "seed")
        cp = _minimal_checkpoint(source_event_ids=[event_id], **{field_name: ""})
        with pytest.raises(ValueError, match=field_name):
            save_checkpoint(store, cp)

    @pytest.mark.parametrize("field_name", [
        "frontier",
        "proposition",
        "strongest_support",
        "strongest_contradiction",
        "unresolved_tension",
        "active_mode",
        "next_move",
    ])
    def test_whitespace_only_required_field_raises(self, tmp_path, field_name):
        store = _make_store(tmp_path)
        event_id = store.add_event("obs", "seed")
        cp = _minimal_checkpoint(source_event_ids=[event_id], **{field_name: "   "})
        with pytest.raises(ValueError, match=field_name):
            save_checkpoint(store, cp)

    def test_invalid_checkpoint_does_not_write_to_db(self, tmp_path):
        """A rejected checkpoint must not leave any partial row."""
        store = _make_store(tmp_path)
        event_id = store.add_event("obs", "seed")
        with pytest.raises(ValueError):
            save_checkpoint(
                store,
                _minimal_checkpoint(source_event_ids=[event_id], frontier=""),
            )
        assert load_latest_checkpoint(store) is None

    def test_invalid_source_event_ids_type_raises(self, tmp_path):
        store = _make_store(tmp_path)
        cp = _minimal_checkpoint()
        object.__setattr__(cp, "source_event_ids", ["not-an-int"])
        with pytest.raises(ValueError, match="source_event_ids"):
            save_checkpoint(store, cp)

    def test_empty_source_event_ids_raises(self, tmp_path):
        """Saving a checkpoint with no source events must raise."""
        store = _make_store(tmp_path)
        # No events created → source_event_ids=[] must be rejected.
        cp = _minimal_checkpoint(source_event_ids=[])
        with pytest.raises(ValueError, match="source_event_ids"):
            save_checkpoint(store, cp)

    def test_nonexistent_source_event_id_raises(self, tmp_path):
        """Saving a checkpoint that references a non-existent event must raise."""
        store = _make_store(tmp_path)
        real_id = store.add_event("obs", "real event")
        fake_id = real_id + 9999
        cp = _minimal_checkpoint(source_event_ids=[fake_id])
        with pytest.raises(ValueError, match=str(fake_id)):
            save_checkpoint(store, cp)

    def test_partial_nonexistent_source_event_ids_raises(self, tmp_path):
        """Even one missing event id must cause the checkpoint to be rejected."""
        store = _make_store(tmp_path)
        real_id = store.add_event("obs", "real event")
        fake_id = real_id + 1000
        cp = _minimal_checkpoint(source_event_ids=[real_id, fake_id])
        with pytest.raises(ValueError, match=str(fake_id)):
            save_checkpoint(store, cp)


# ---------------------------------------------------------------------------
# Session lifecycle tests
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    def test_start_session_returns_int_id(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.start_session()
        assert isinstance(sid, int)
        assert sid >= 1

    def test_end_session_marks_ended(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.start_session()
        store.end_session(sid)
        row = store.db.execute(
            "SELECT status, ended_at FROM sessions WHERE id = ?", (sid,)
        ).fetchone()
        assert row["status"] == "ended"
        assert row["ended_at"] is not None

    def test_end_session_sets_ended_at_timestamp(self, tmp_path):
        """ended_at must be a non-empty timestamp string."""
        store = _make_store(tmp_path)
        sid = store.start_session()
        store.end_session(sid)
        ended_at = store.db.execute(
            "SELECT ended_at FROM sessions WHERE id = ?", (sid,)
        ).fetchone()["ended_at"]
        assert isinstance(ended_at, str) and len(ended_at) > 0

    def test_end_nonexistent_session_raises(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(ValueError, match="9999"):
            store.end_session(9999)

    def test_interrupted_sessions_detects_active_without_end(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.start_session()
        interrupted = store.interrupted_sessions()
        assert sid in interrupted

    def test_interrupted_sessions_excludes_cleanly_ended(self, tmp_path):
        store = _make_store(tmp_path)
        sid = store.start_session()
        store.end_session(sid)
        interrupted = store.interrupted_sessions()
        assert sid not in interrupted

    def test_session_survives_reopen(self, tmp_path):
        """A session started before a restart must still be visible after reopening."""
        db_path = str(tmp_path / "k.db")
        store1 = Store(db_path)
        store1.init()
        sid = store1.start_session()
        store1.db.close()

        store2 = Store(db_path)
        store2.init()
        interrupted = store2.interrupted_sessions()
        assert sid in interrupted

    def test_multiple_sessions_independent(self, tmp_path):
        store = _make_store(tmp_path)
        s1 = store.start_session()
        s2 = store.start_session()
        store.end_session(s1)
        interrupted = store.interrupted_sessions()
        assert s1 not in interrupted
        assert s2 in interrupted


# ---------------------------------------------------------------------------
# Restart / recovery tests
# ---------------------------------------------------------------------------

class TestRecovery:
    def test_resume_after_process_reopen(self, tmp_path):
        """Closing and reopening the database returns the latest checkpoint."""
        db_path = str(tmp_path / "kernel.db")

        store1 = Store(db_path)
        store1.init()
        eid = store1.add_event("obs", "seed for checkpoint")
        cp = _minimal_checkpoint(
            frontier="frontier after restart",
            next_move="resume from this exact point",
            source_event_ids=[eid],
        )
        save_checkpoint(store1, cp)
        store1.db.close()

        store2 = Store(db_path)
        store2.init()
        loaded = load_latest_checkpoint(store2)
        assert loaded is not None
        assert loaded.frontier == "frontier after restart"
        assert loaded.next_move == "resume from this exact point"

    def test_events_survive_reopen(self, tmp_path):
        db_path = str(tmp_path / "kernel.db")

        store1 = Store(db_path)
        store1.init()
        store1.add_event("correction", "remember to check timestamps")
        store1.db.close()

        store2 = Store(db_path)
        store2.init()
        count = store2.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 1

    def test_partially_written_checkpoint_rolled_back(self, tmp_path):
        """A transaction that is rolled back must not leave a visible checkpoint."""
        store = _make_store(tmp_path)
        eid = store.add_event("obs", "seed event")
        save_checkpoint(
            store,
            _minimal_checkpoint(frontier="committed checkpoint", source_event_ids=[eid]),
        )

        try:
            with store.db:
                store.db.execute(
                    """
                    INSERT INTO checkpoints(
                        frontier, proposition, strongest_support,
                        strongest_contradiction, unresolved_tension,
                        active_mode, next_move, source_event_ids
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "corrupted frontier",
                        "corrupted prop",
                        "bad", "bad", "bad", "bad", "bad", "[]",
                    ),
                )
                raise RuntimeError("simulated crash mid-write")
        except RuntimeError:
            pass  # transaction was rolled back

        loaded = load_latest_checkpoint(store)
        assert loaded is not None
        assert loaded.frontier == "committed checkpoint"

    def test_migrations_reapplied_correctly_on_existing_db_after_restart(
        self, tmp_path
    ):
        """Second init() on an existing DB must not re-apply migrations."""
        db_path = str(tmp_path / "k.db")
        store1 = Store(db_path)
        store1.init()
        store1.db.close()

        store2 = Store(db_path)
        store2.init()
        count = store2.db.execute(
            "SELECT COUNT(*) FROM schema_version"
        ).fetchone()[0]
        assert count == 7  # exactly seven migrations recorded, not duplicated


# ---------------------------------------------------------------------------
# Idempotent sleep tests
# ---------------------------------------------------------------------------

class TestSleep:
    def test_sleep_promotes_corrections(self, tmp_path):
        store = _make_store(tmp_path)
        store.add_event("correction", "lesson alpha")
        store.add_event("correction", "lesson beta")
        result = consolidate(store)
        assert result["experience_candidates"] == 2

    def test_sleep_ignores_non_corrections(self, tmp_path):
        store = _make_store(tmp_path)
        store.add_event("observation", "just watching")
        result = consolidate(store)
        assert result["experience_candidates"] == 0
        assert result["events"] == 1

    def test_sleep_is_idempotent_on_second_call(self, tmp_path):
        """Calling consolidate twice must not double-count corrections."""
        store = _make_store(tmp_path)
        store.add_event("correction", "lesson one")
        store.add_event("correction", "lesson two")

        first = consolidate(store)
        assert first["experience_candidates"] == 2

        second = consolidate(store)
        assert second["experience_candidates"] == 0
        assert second["events"] == 0

        total = store.db.execute(
            "SELECT COUNT(*) FROM experience_candidates"
        ).fetchone()[0]
        assert total == 2

    def test_sleep_resumes_from_last_position_after_reopen(self, tmp_path):
        db_path = str(tmp_path / "sleep.db")

        store1 = Store(db_path)
        store1.init()
        store1.add_event("correction", "pre-restart lesson")
        consolidate(store1)
        store1.db.close()

        store2 = Store(db_path)
        store2.init()
        store2.add_event("correction", "post-restart lesson")
        result = consolidate(store2)

        assert result["experience_candidates"] == 1
        total = store2.db.execute(
            "SELECT COUNT(*) FROM experience_candidates"
        ).fetchone()[0]
        assert total == 2

    def test_sleep_on_empty_db_returns_zeros(self, tmp_path):
        store = _make_store(tmp_path)
        result = consolidate(store)
        assert result["events"] == 0
        assert result["experience_candidates"] == 0

    def test_sleep_candidate_has_non_empty_created_at(self, tmp_path):
        """experience_candidates inserted by consolidate must carry a timestamp."""
        store = _make_store(tmp_path)
        store.add_event("correction", "timestamped lesson")
        consolidate(store)
        row = store.db.execute(
            "SELECT created_at FROM experience_candidates LIMIT 1"
        ).fetchone()
        assert row is not None
        assert isinstance(row["created_at"], str) and row["created_at"].strip() != ""


# ---------------------------------------------------------------------------
# Integrity and backup/restore tests
# ---------------------------------------------------------------------------

class TestIntegrityAndBackup:
    def test_integrity_check_passes_on_clean_db(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.integrity_check()
        assert result == ["ok"]

    def test_backup_and_restore_reproduce_state(self, tmp_path):
        """Backup and restore must yield an identical active state."""
        db_path = str(tmp_path / "source.db")
        backup_path = str(tmp_path / "backup.db")

        source = Store(db_path)
        source.init()
        event_id = source.add_event("correction", "backup lesson")
        cp = _minimal_checkpoint(
            frontier="frontier before backup",
            next_move="resume after restore",
            source_event_ids=[event_id],
        )
        save_checkpoint(source, cp)

        backup_db = sqlite3.connect(backup_path)
        source.db.backup(backup_db)
        backup_db.close()
        source.db.close()

        restored_path = str(tmp_path / "restored.db")
        restore_target = Store(restored_path)
        restore_target.init()
        src_db = sqlite3.connect(backup_path)
        try:
            src_db.backup(restore_target.db)
        finally:
            src_db.close()

        loaded = load_latest_checkpoint(restore_target)
        assert loaded is not None
        assert loaded.frontier == "frontier before backup"
        assert loaded.next_move == "resume after restore"

        event_count = restore_target.db.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]
        assert event_count == 1

    def test_add_event_returns_id(self, tmp_path):
        store = _make_store(tmp_path)
        id1 = store.add_event("obs", "first")
        id2 = store.add_event("obs", "second")
        assert id1 == 1
        assert id2 == 2

