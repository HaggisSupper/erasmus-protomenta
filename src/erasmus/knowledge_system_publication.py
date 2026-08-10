from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .knowledge_runtime import _digest, _json, _urn


class PublicationFacadeMixin:
    """Deterministic immutable OKF v0.2-style publication facade."""

    @staticmethod
    def _yaml_scalar(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _okf_document(self, revision_id: str) -> bytes:
        revision = self._revision_payload(revision_id)
        if revision["concept_lifecycle"] not in {"validated", "canonical"}:
            raise ValueError("only validated/canonical revisions can publish")
        source_refs: set[str] = set()
        claims: list[dict[str, Any]] = []
        for claim_id in revision["claim_ids"]:
            inspected = self.ledger.inspect(int(claim_id))
            for evidence in inspected["evidence"]:
                provenance = evidence.get("provenance")
                if provenance is None:
                    provenance = evidence.get("provenance_json")
                    if isinstance(provenance, str):
                        try:
                            provenance = json.loads(provenance)
                        except json.JSONDecodeError:
                            provenance = {}
                if isinstance(provenance, dict):
                    for span_id in provenance.get("source_span_ids", []):
                        span = self.db.execute(
                            "SELECT source_id FROM knowledge_source_spans WHERE span_id=?",
                            (span_id,),
                        ).fetchone()
                        if span:
                            source_refs.add(span["source_id"])
            claims.append({
                "id": str(claim_id),
                "statement": inspected["statement"],
                "status": inspected["status"],
            })
        lines = [
            "---",
            f"title: {self._yaml_scalar(revision['title'])}",
            f"description: {self._yaml_scalar(revision['description'])}",
            "status: canonical",
            "tags: []",
            "sources:",
        ]
        if source_refs:
            lines.extend(
                f"  - {self._yaml_scalar(source)}" for source in sorted(source_refs)
            )
        else:
            lines.append("  []")
        lines.extend([
            "erasmus:",
            f"  concept_id: {self._yaml_scalar(revision['concept_id'])}",
            f"  revision_id: {self._yaml_scalar(revision_id)}",
            "---",
            "",
            f"# {revision['title']}",
            "",
            revision["description"],
            "",
            "## Claims",
            "",
        ])
        for claim in claims:
            lines.append(
                f"- {claim['statement']} (`{claim['status']}`, claim `{claim['id']}`)"
            )
        lines.append("")
        return "\n".join(lines).encode("utf-8")

    def _verify_publication_receipt(self, snapshot: dict[str, Any]) -> None:
        receipt = self.db.execute(
            "SELECT * FROM knowledge_publication_receipts WHERE snapshot_id=?",
            (snapshot["snapshot_id"],),
        ).fetchone()
        if receipt is None:
            raise ValueError("published OKF snapshot is missing its receipt")
        root = Path(snapshot["root_path"])
        expected = json.loads(receipt["file_digests_json"])
        for relative, digest in expected.items():
            path = root / relative
            if not path.is_file():
                raise ValueError(f"published snapshot file missing: {relative}")
            if _digest(path.read_bytes()) != digest:
                raise ValueError(f"published snapshot was modified: {relative}")

    def publish_okf_snapshot(
        self,
        channel_id: str,
        revision_ids: list[str],
        actor: str,
        authority: str,
    ) -> dict[str, Any]:
        self._gate("knowledge:publish", actor)
        if authority != "knowledge:publish" or not actor.startswith("human:"):
            raise PermissionError("human knowledge:publish required")
        channel = self.db.execute(
            "SELECT * FROM knowledge_publication_channels WHERE channel_id=? AND state='active'",
            (channel_id,),
        ).fetchone()
        if channel is None:
            raise ValueError("active publication channel not found")
        files: dict[str, bytes] = {}
        for revision_id in sorted(revision_ids):
            revision = self._revision_payload(revision_id)
            relative = f"{revision['okf_path'].rstrip('/')}.md"
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise ValueError("publication path escaped snapshot root")
            if relative in files:
                raise ValueError("duplicate OKF path")
            files[relative] = self._okf_document(revision_id)
        file_digests = {
            path: _digest(content) for path, content in sorted(files.items())
        }
        manifest_digest = _digest({
            "contract": "erasmus.okf-publication/v1",
            "files": file_digests,
        })
        existing = self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE channel_id=? AND manifest_digest=? AND snapshot_state='published'",
            (channel_id, manifest_digest),
        ).fetchone()
        if existing:
            result = dict(existing)
            self._verify_publication_receipt(result)
            return result
        sequence = self.db.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM knowledge_snapshots WHERE channel_id=?",
            (channel_id,),
        ).fetchone()[0]
        snapshot_id = _urn("snapshot", f"{channel_id}:{sequence}:{manifest_digest}")
        target = (
            self.okf_root / channel_id / f"{sequence:08d}-{manifest_digest[:12]}"
        ).resolve()
        if not target.is_relative_to(self.okf_root):
            raise ValueError("snapshot path escaped OKF root")
        staging = target.with_name(target.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for relative, content in sorted(files.items()):
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            manifest = {
                "contract": "erasmus.okf-publication/v1",
                "snapshot_id": snapshot_id,
                "channel_id": channel_id,
                "sequence": sequence,
                "revision_ids": sorted(revision_ids),
                "file_digests": file_digests,
                "manifest_digest": manifest_digest,
            }
            (staging / "manifest.json").write_text(
                _json(manifest) + "\n", encoding="utf-8"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(target)
            receipt_id = _urn("publication-receipt", _digest(manifest))
            with self.db:
                self.db.execute(
                    "INSERT INTO knowledge_snapshots(snapshot_id,channel_id,sequence,revision_ids_json,root_path,manifest_digest,snapshot_state,actor) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        snapshot_id, channel_id, sequence,
                        _json(sorted(revision_ids)), str(target), manifest_digest,
                        "published", actor,
                    ),
                )
                self.db.execute(
                    "INSERT INTO knowledge_publication_receipts(receipt_id,snapshot_id,channel_id,manifest_digest,file_digests_json,actor,authority) VALUES(?,?,?,?,?,?,?)",
                    (
                        receipt_id, snapshot_id, channel_id, manifest_digest,
                        _json(file_digests), actor, authority,
                    ),
                )
                self.db.execute(
                    "UPDATE knowledge_publication_channels SET current_snapshot_id=? WHERE channel_id=?",
                    (snapshot_id, channel_id),
                )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if target.exists() and self.db.execute(
                "SELECT 1 FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone() is None:
                shutil.rmtree(target, ignore_errors=True)
            raise
        return dict(self.db.execute(
            "SELECT * FROM knowledge_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone())
