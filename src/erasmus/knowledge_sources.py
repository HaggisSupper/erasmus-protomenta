"""Phase 3.1 source registry primitives.

Implements deterministic source artifact registration, immutable span registration,
and minimal verification for source integrity.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

DEFAULT_SOURCE_KIND = "document"
DEFAULT_MEDIA_TYPE = "application/octet-stream"
DEFAULT_STORAGE_STATE = "available"
ALLOWED_SOURCE_KINDS = {
    "document",
    "web",
    "repository",
    "database",
    "observation",
    "tool_receipt",
    "human",
    "model",
    "other",
}


class KnowledgeSourceError(ValueError):
    """Raised for immutable source registry rule violations."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _coerce_storage_state(value: Any, *, field_name: str) -> str:
    value = _coerce_str(value, field_name=field_name)
    if value not in {"available", "external", "tombstoned", "removed"}:
        raise KnowledgeSourceError(
            f"{field_name} must be one of: available, external, tombstoned, removed"
        )
    return value


def _coerce_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise KnowledgeSourceError(f"{field_name} must be a JSON object")
    return dict(value)


def _coerce_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise KnowledgeSourceError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise KnowledgeSourceError(f"{field_name} cannot be empty")
    return value


def _coerce_positive_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise KnowledgeSourceError(f"{field_name} must be a positive integer")
    return value


def _coerce_scope(scope: Any) -> dict[str, Any]:
    if scope is None:
        return {}
    return _coerce_mapping(scope, field_name="scope")


def _coerce_root(root: str | Path) -> Path:
    return Path(root).resolve()


def _is_reparse_or_symlink(path: Path) -> bool:
    if os.name != "nt":
        return path.is_symlink()
    try:
        return path.is_symlink() or path.is_junction()
    except AttributeError:
        return path.is_symlink()


def _source_blob_path(root: Path, digest: str, *, suffix: str) -> Path:
    base = root / "blobs" / digest[:2] / digest[2:4]
    return base / f"{digest}{suffix.lower() or '.bin'}"


def _source_id(digest: str) -> str:
    return f"urn:erasmus:source:{digest}"


def _span_id(source_id: str, start_page: int, end_page: int, coordinate: Mapping[str, Any]) -> str:
    payload = _canonical_json(
        {"source_id": source_id, "start_page": start_page, "end_page": end_page, "coordinate": coordinate}
    )
    return f"urn:erasmus:source-span:{_sha256_bytes(payload.encode('utf-8'))[:40]}"


def _receipt_id(source_id: str, extractor: str) -> str:
    return f"urn:erasmus:extractor-receipt:{source_id}:{extractor}"


def _text_digest(text: str | None) -> str:
    if text is None:
        return _canonical_json({"algorithm": "sha256", "value": "none"})
    return _canonical_json(
        {"algorithm": "sha256", "value": _sha256_bytes(text.encode("utf-8")), "canonicalization": "utf-8"}
    )


@dataclass(frozen=True)
class SourceArtifact:
    source_id: str
    locator: str
    local_path: str
    sha256: str
    byte_size: int


class KnowledgeSourceRegistry:
    """Minimal bounded source registry implementation for P3.1."""

    def __init__(self, db: sqlite3.Connection, storage_root: str | Path):
        self.db = db
        if self.db.row_factory is None:
            self.db.row_factory = sqlite3.Row
        self.storage_root = _coerce_root(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def register_source(
        self,
        source_path: str | Path,
        *,
        source_kind: str = DEFAULT_SOURCE_KIND,
        media_type: str = DEFAULT_MEDIA_TYPE,
        scope: Mapping[str, Any] | None = None,
        actor: str = "process:erasmus",
        acquired_by: str = "process:erasmus",
    ) -> dict[str, Any]:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise KnowledgeSourceError(f"source path is not a file: {path}")
        if _is_reparse_or_symlink(path):
            raise KnowledgeSourceError(f"source path is a reparse or symlink point: {path}")
        if _is_reparse_or_symlink(path.parent):
            raise KnowledgeSourceError(f"source parent is a reparse or symlink point: {path.parent}")

        source_kind = _coerce_str(source_kind, field_name="source_kind")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise KnowledgeSourceError(
                f"source_kind must be one of: {', '.join(sorted(ALLOWED_SOURCE_KINDS))}"
            )
        media_type = _coerce_str(media_type, field_name="media_type")
        scope_data = _coerce_scope(scope)

        data = path.read_bytes()
        digest = _sha256_bytes(data)
        byte_size = len(data)
        source_id = _source_id(digest)
        blob = _source_blob_path(self.storage_root, digest, suffix=path.suffix)

        row = self._find_source(source_id)
        if row is not None:
            metadata = self._row_to_source_dict(row)
            if row["sha256"] != digest:
                raise KnowledgeSourceError("digest collision detected for source-id")
            return metadata

        if blob.exists() and not blob.is_file():
            raise KnowledgeSourceError(f"target source blob is not a regular file: {blob}")
        if blob.exists() and _sha256_bytes(blob.read_bytes()) != digest:
            raise KnowledgeSourceError("alias attack rejected: digest mismatch at target blob path")

        now = datetime.now(UTC).isoformat()
        with self.db:
            blob.parent.mkdir(parents=True, exist_ok=True)
            if not blob.exists():
                shutil.copy2(path, blob)

            event_seq = self._emit_event(
                "source.register",
                "KnowledgeSource",
                source_id,
                actor,
                {"source_path": str(path), "source_id": source_id},
            )
            locator = f"blob:{blob.relative_to(self.storage_root)}"
            metadata = json.dumps(
                {
                    "source_path": str(path),
                    "registered_from": "external-path",
                    "scope": scope_data,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.db.execute(
                """
                INSERT INTO knowledge_sources(
                    source_id, event_seq, sha256, media_type, byte_size,
                    source_kind, locator, local_path, scope_json, storage_state,
                    metadata_json, acquired_by, acquired_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    event_seq,
                    digest,
                    media_type,
                    byte_size,
                    source_kind,
                    locator,
                    str(blob),
                    json.dumps(scope_data, sort_keys=True, separators=(",", ":")),
                    _coerce_storage_state("available", field_name="storage_state"),
                    metadata,
                    acquired_by,
                    now,
                ),
            )

            receipt_payload = _coerce_mapping({"method": "copy", "source_path": str(path)}, field_name="extractor")
            self._ensure_receipt(
                source_id=source_id,
                actor=actor,
                started_at=now,
                extractor=receipt_payload,
                status="complete",
                output_digest=None,
                options={},
                detail={"storage_root": str(self.storage_root)},
            )

        return self.inspect_source(source_id)

    def register_span(
        self,
        source_id: str,
        *,
        start_page: int,
        end_page: int,
        coordinate: Mapping[str, Any] | None = None,
        extracted_text: str | None = None,
        protected_ref: str | None = None,
        scope: Mapping[str, Any] | None = None,
        actor: str = "process:erasmus",
    ) -> dict[str, Any]:
        source_id = _coerce_str(source_id, field_name="source_id")
        start_page = _coerce_positive_int(start_page, field_name="start_page")
        end_page = _coerce_positive_int(end_page, field_name="end_page")
        if end_page < start_page:
            raise KnowledgeSourceError("end_page must be greater than or equal to start_page")
        if extracted_text is None and protected_ref is None:
            raise KnowledgeSourceError("exactly one of extracted_text or protected_ref must be provided")
        if extracted_text is not None and protected_ref is not None:
            raise KnowledgeSourceError("extracted_text and protected_ref are mutually exclusive")
        scope_data = _coerce_scope(scope)
        coordinate_payload = _coerce_mapping(coordinate or {}, field_name="coordinate")

        source = self._find_source(source_id)
        if source is None:
            raise KnowledgeSourceError(f"source not found: {source_id}")
        if source["storage_state"] != "available":
            raise KnowledgeSourceError(f"source is not available: {source_id}")

        receipt = self._latest_receipt(source_id)
        if receipt is None:
            now = datetime.now(UTC).isoformat()
            receipt = self._ensure_receipt(
                source_id=source_id,
                actor=actor,
                started_at=now,
                extractor={"method": "copy"},
                status="complete",
                output_digest=None,
                options={},
                detail={"storage_root": str(self.storage_root)},
            )

        span_id = _span_id(source_id, start_page, end_page, coordinate_payload)
        row = self.db.execute(
            "SELECT * FROM knowledge_source_spans WHERE span_id = ?",
            (span_id,),
        ).fetchone()
        if row is not None:
            return dict(row)

        with self.db:
            event_seq = self._emit_event(
                "source.span_register",
                "KnowledgeSourceSpan",
                span_id,
                actor,
                {
                    "source_id": source_id,
                    "start_page": start_page,
                    "end_page": end_page,
                },
            )
            self.db.execute(
                """
                INSERT INTO knowledge_source_spans(
                    span_id, event_seq, source_id, coordinate_json, text_digest_json,
                    extracted_text, protected_ref, extraction_receipt_id, scope_json,
                    start_page, end_page
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span_id,
                    event_seq,
                    source_id,
                    _canonical_json(coordinate_payload),
                    _text_digest(extracted_text),
                    extracted_text,
                    protected_ref,
                    receipt["receipt_id"],
                    json.dumps(scope_data, sort_keys=True, separators=(",", ":")),
                    start_page,
                    end_page,
                ),
            )
        return self.inspect_span(span_id)

    def inspect_source(self, source_id: str) -> dict[str, Any]:
        row = self._find_source(source_id)
        if row is None:
            raise KnowledgeSourceError(f"source not found: {source_id}")
        return self._row_to_source_dict(row)

    def inspect_span(self, span_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM knowledge_source_spans WHERE span_id = ?",
            (_coerce_str(span_id, field_name="span_id"),),
        ).fetchone()
        if row is None:
            raise KnowledgeSourceError(f"span not found: {_coerce_str(span_id, field_name='span_id')}")
        return dict(row)

    def list_sources(self, *, scope: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        wanted = _coerce_scope(scope)
        rows = self.db.execute(
            """
            SELECT source_id, event_seq, sha256, media_type, byte_size, source_kind, locator,
                   local_path, scope_json, storage_state, metadata_json, acquired_by, acquired_at,
                   created_at, retired_at
            FROM knowledge_sources
            ORDER BY source_id
            """
        ).fetchall()
        if not wanted:
            return [self._row_to_source_dict(row) for row in rows]
        result: list[dict[str, Any]] = []
        for row in rows:
            source = self._row_to_source_dict(row)
            if all(source["scope"].get(key) == value for key, value in wanted.items()):
                result.append(source)
        return result

    def list_spans(self, source_id: str) -> list[dict[str, Any]]:
        source_id = _coerce_str(source_id, field_name="source_id")
        rows = self.db.execute(
            "SELECT * FROM knowledge_source_spans WHERE source_id = ? ORDER BY span_id",
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def tombstone_source(self, source_id: str, *, reason: str, actor: str = "process:erasmus") -> dict[str, Any]:
        source_id = _coerce_str(source_id, field_name="source_id")
        source = self._find_source(source_id)
        if source is None:
            raise KnowledgeSourceError(f"source not found: {source_id}")
        if source["storage_state"] == "tombstoned":
            raise KnowledgeSourceError(f"source already tombstoned: {source_id}")

        reason_text = _coerce_str(reason, field_name="reason")
        with self.db:
            event_seq = self._emit_event(
                "source.tombstone",
                "KnowledgeSource",
                source_id,
                actor,
                {"source_id": source_id, "reason": reason_text},
            )
            self.db.execute(
                "UPDATE knowledge_sources SET storage_state = 'tombstoned', retired_at = ? WHERE source_id = ?",
                (datetime.now(UTC).isoformat(), source_id),
            )
            self.db.execute(
                """
                INSERT INTO knowledge_source_tombstones(
                    source_id, event_seq, actor, reason_json
                ) VALUES (?, ?, ?, ?)
                """,
                (source_id, event_seq, actor, json.dumps({"reason": reason_text}, separators=(",", ":"), sort_keys=True)),
            )
        row = self._find_source(source_id)
        return self._row_to_source_dict(row) if row is not None else {}

    def verify_source(self, source_id: str) -> dict[str, Any]:
        source_id = _coerce_str(source_id, field_name="source_id")
        source = self._find_source(source_id)
        if source is None:
            raise KnowledgeSourceError(f"source not found: {source_id}")
        local = Path(source["local_path"])
        if not local.is_file():
            return {"source_id": source_id, "ok": False, "reason": "missing source file"}
        return {
            "source_id": source_id,
            "ok": _sha256_bytes(local.read_bytes()) == source["sha256"],
            "recorded_sha256": source["sha256"],
            "actual_sha256": _sha256_bytes(local.read_bytes()),
            "byte_size": local.stat().st_size,
            "expected_byte_size": source["byte_size"],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _find_source(self, source_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM knowledge_sources WHERE source_id = ?",
            (_coerce_str(source_id, field_name="source_id"),),
        ).fetchone()

    def _row_to_source_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "source_id": row["source_id"],
            "sha256": row["sha256"],
            "media_type": row["media_type"],
            "byte_size": row["byte_size"],
            "source_kind": row["source_kind"],
            "locator": row["locator"],
            "local_path": row["local_path"],
            "scope": json.loads(row["scope_json"]),
            "storage_state": row["storage_state"],
            "metadata": json.loads(row["metadata_json"]),
            "acquired_by": row["acquired_by"],
            "acquired_at": row["acquired_at"],
            "created_at": row["created_at"],
            "retired_at": row["retired_at"],
        }

    def _latest_receipt(self, source_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM knowledge_extraction_receipts WHERE source_id = ? ORDER BY completed_at DESC",
            (source_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _ensure_receipt(
        self,
        *,
        source_id: str,
        actor: str,
        started_at: str,
        extractor: Mapping[str, Any],
        status: str,
        output_digest: Mapping[str, Any] | None,
        options: Mapping[str, Any],
        detail: Mapping[str, Any],
    ) -> dict[str, Any]:
        existing = self.db.execute(
            "SELECT * FROM knowledge_extraction_receipts WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if existing is not None:
            return dict(existing)

        receipt = self._register_receipt(
            source_id,
            actor=actor,
            started_at=started_at,
            extractor=extractor,
            status=status,
            output_digest=output_digest,
            options=options,
            detail=detail,
        )
        return receipt

    def _register_receipt(
        self,
        source_id: str,
        *,
        actor: str,
        started_at: str,
        extractor: Mapping[str, Any],
        status: str,
        output_digest: Mapping[str, Any] | None,
        options: Mapping[str, Any],
        detail: Mapping[str, Any],
    ) -> dict[str, Any]:
        extractor = _coerce_mapping(extractor, field_name="extractor")
        options = _coerce_mapping(options, field_name="options")
        detail = _coerce_mapping(detail, field_name="detail")
        event_seq = self._emit_event(
            "source.extractor_receipt",
            "KnowledgeExtractionReceipt",
            source_id,
            actor,
            {
                "source_id": source_id,
                "extractor": extractor,
                "status": status,
            },
        )
        receipt_id = _receipt_id(source_id, extractor.get("method", "default"))
        completed_at = datetime.now(UTC).isoformat()
        output_json = json.dumps(output_digest, sort_keys=True, separators=(",", ":")) if output_digest is not None else None
        self.db.execute(
            """
            INSERT INTO knowledge_extraction_receipts(
                receipt_id, event_seq, source_id, extractor_json, options_json,
                status, output_digest_json, detail_json, started_at, completed_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                event_seq,
                source_id,
                _canonical_json(extractor),
                _canonical_json(options),
                status,
                output_json,
                _canonical_json(detail),
                started_at,
                completed_at,
            ),
        )
        return {
            "receipt_id": receipt_id,
            "source_id": source_id,
            "extractor": extractor,
            "status": status,
            "output_digest": output_digest,
            "detail": detail,
            "event_seq": event_seq,
        }

    def _emit_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor: str,
        payload: Mapping[str, Any],
    ) -> int:
        payload = _coerce_mapping(payload, field_name="payload")
        actor = _coerce_str(actor, field_name="actor")
        event_id_payload = _canonical_json(
            {
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "actor": actor,
                "payload": payload,
            }
        )
        event_id = f"urn:erasmus:knowledge-source-event:{_sha256_bytes(event_id_payload.encode('utf-8'))[:40]}"
        existing = self.db.execute(
            "SELECT event_seq FROM knowledge_source_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if existing is not None:
            return existing["event_seq"]
        cursor = self.db.execute(
            """
            INSERT INTO knowledge_source_events(
                event_id, event_type, aggregate_type, aggregate_id, actor, payload_digest_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                _coerce_str(event_type, field_name="event_type"),
                _coerce_str(aggregate_type, field_name="aggregate_type"),
                _coerce_str(aggregate_id, field_name="aggregate_id"),
                actor,
                _canonical_json(payload),
            ),
        )
        return cursor.lastrowid
