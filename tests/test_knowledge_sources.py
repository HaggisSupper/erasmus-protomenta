import json
import sqlite3
import sys
from pathlib import Path

import pytest

from erasmus.cli.main import main
from erasmus.migrations import apply_migrations
from erasmus.knowledge_sources import KnowledgeSourceError, KnowledgeSourceRegistry


def _init_store(tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
    db_path = tmp_path / "knowledge.db"
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    apply_migrations(db)
    return db, tmp_path / "source_store"


def _write_source(path: Path) -> Path:
    path.write_bytes(b"source bytes")
    return path


def test_register_source_span_roundtrip(tmp_path):
    db, source_store = _init_store(tmp_path)
    registry = KnowledgeSourceRegistry(db, source_store)
    source_path = _write_source(tmp_path / "source.txt")

    source = registry.register_source(
        source_path,
        source_kind="document",
        media_type="text/plain",
        scope={"tenant": "unit"},
        actor="process:test",
        acquired_by="process:test",
    )
    assert source["storage_state"] == "available"
    assert source["source_kind"] == "document"

    span = registry.register_span(
        source["source_id"],
        start_page=1,
        end_page=1,
        coordinate={"page": 1},
        extracted_text="a span",
        scope={"tenant": "unit"},
        actor="process:test",
    )
    assert span["source_id"] == source["source_id"]
    assert span["start_page"] == 1
    assert span["end_page"] == 1
    assert span["extracted_text"] == "a span"

    listed = registry.list_spans(source["source_id"])
    assert len(listed) == 1


def test_register_source_filters_tombstoned_source(tmp_path):
    db, source_store = _init_store(tmp_path)
    registry = KnowledgeSourceRegistry(db, source_store)
    source_path = _write_source(tmp_path / "source.txt")

    source = registry.register_source(source_path)
    registry.tombstone_source(source["source_id"], reason="deprecation", actor="process:test")

    with pytest.raises(KnowledgeSourceError, match="source is not available"):
        registry.register_span(
            source["source_id"],
            start_page=1,
            end_page=1,
            coordinate={"page": 1},
            extracted_text="not allowed",
            actor="process:test",
        )


def test_register_source_rejects_unknown_kind(tmp_path):
    db, source_store = _init_store(tmp_path)
    registry = KnowledgeSourceRegistry(db, source_store)
    source_path = _write_source(tmp_path / "source.txt")

    with pytest.raises(KnowledgeSourceError, match="source_kind must be one of"):
        registry.register_source(source_path, source_kind="unknown-kind")


def test_verify_source_and_list_scope(tmp_path):
    db, source_store = _init_store(tmp_path)
    registry = KnowledgeSourceRegistry(db, source_store)
    source_path = _write_source(tmp_path / "alpha.txt")

    alpha = registry.register_source(source_path, scope={"tenant": "alpha"})
    _write_source(tmp_path / "beta.txt")
    beta = registry.register_source(tmp_path / "beta.txt", scope={"tenant": "beta"})

    filtered = registry.list_sources(scope={"tenant": "alpha"})
    assert [row["source_id"] for row in filtered] == [alpha["source_id"]]

    verified = registry.verify_source(beta["source_id"])
    assert verified["ok"] is True

    Path(beta["local_path"]).write_bytes(b"tampered bytes")
    tampered = registry.verify_source(beta["source_id"])
    assert tampered["ok"] is False
    assert tampered["recorded_sha256"] != tampered["actual_sha256"]


def test_cli_knowledge_source_lifecycle(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "cli.db"
    source_store = tmp_path / "cli-source-store"
    source = _write_source(tmp_path / "cli_source.txt")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(db_path),
            "--source-store",
            str(source_store),
            "knowledge-source-add",
            str(source),
            "--source-kind",
            "document",
            "--scope-json",
            "{\"tenant\":\"cli\"}",
        ],
    )
    main()
    added = json.loads(capsys.readouterr().out)
    assert added["source_kind"] == "document"
    assert added["storage_state"] == "available"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(db_path),
            "--source-store",
            str(source_store),
            "knowledge-source-list",
            "--scope-json",
            "{\"tenant\":\"cli\"}",
        ],
    )
    main()
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert listed[0]["source_id"] == added["source_id"]
