"""Deterministic guarded missions for bounded local Git repositories."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .store import Store


class RepositoryMissionError(ValueError):
    """Raised when a repository mission violates a deterministic boundary."""


def _schema() -> Mapping[str, Any]:
    candidates = (
        Path(__file__).resolve().parents[2] / "contracts" / "repository-mission.schema.json",
        Path(__file__).resolve().parent / "contracts" / "repository-mission.schema.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise RepositoryMissionError("repository mission schema is unavailable")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class RepositoryMissionContract:
    identifier: str
    objective: str
    workspace_root: Path
    repository_root: Path
    expected_base_sha: str
    branch: str
    allowed_paths: tuple[str, ...]
    patch_source: str
    declared_patch: str | None
    worker_request: Mapping[str, Any] | None
    test_command: tuple[str, ...]
    test_timeout: int
    retry_limit: int
    stopping_condition: str
    rollback_command_description: str
    implementer: str
    reviewer: str
    reviewer_authority: str
    countercase: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "RepositoryMissionContract":
        if not isinstance(raw, Mapping):
            raise RepositoryMissionError("repository mission contract must be an object")
        errors = sorted(Draft202012Validator(_schema()).iter_errors(dict(raw)), key=lambda e: list(e.path))
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.absolute_path)
            label = location or "contract"
            if error.validator == "required":
                missing = re.search(r"'([^']+)'", error.message)
                if missing:
                    label = missing.group(1)
            raise RepositoryMissionError(f"{label}: {error.message}")

        workspace_root = Path(str(raw["workspace_root"])).resolve(strict=True)
        repository_root = Path(str(raw["repository_root"])).resolve(strict=True)
        if not workspace_root.is_dir() or not repository_root.is_dir():
            raise RepositoryMissionError("workspace_root and repository_root must be directories")
        if not repository_root.is_relative_to(workspace_root):
            raise RepositoryMissionError("repository_root resolves outside workspace_root")

        allowed_paths: list[str] = []
        for value in raw["allowed_paths"]:  # type: ignore[union-attr]
            path = str(value)
            posix = PurePosixPath(path)
            drive_absolute = bool(re.match(r"^[A-Za-z]:[/\\]", path))
            if (
                not path
                or "\\" in path
                or posix.is_absolute()
                or drive_absolute
                or any(part in {"", ".", ".."} for part in posix.parts)
            ):
                raise RepositoryMissionError(f"allowed_paths contains unsafe path: {path!r}")
            candidate = (repository_root / Path(*posix.parts)).resolve()
            if not candidate.is_relative_to(repository_root):
                raise RepositoryMissionError(f"allowed_paths escapes repository_root: {path!r}")
            allowed_paths.append(posix.as_posix())

        implementer = str(raw["implementer"]).strip()
        reviewer = str(raw["reviewer"]).strip()
        if implementer.casefold() == reviewer.casefold():
            raise RepositoryMissionError("reviewer must be independent from implementer")
        countercase = str(raw["countercase"]).strip()
        if not countercase:
            raise RepositoryMissionError("countercase is required")
        branch = str(raw["branch"])
        if branch.startswith("-") or branch.endswith(("/", ".")) or ".." in branch or re.search(r"[\s~^:?*\\\[]", branch):
            raise RepositoryMissionError("branch is not a safe Git branch name")

        worker_request_raw = raw.get("worker_request")
        worker_request = (
            _freeze_json(worker_request_raw)
            if isinstance(worker_request_raw, Mapping)
            else None
        )
        return cls(
            identifier=str(raw["identifier"]).strip(),
            objective=str(raw["objective"]).strip(),
            workspace_root=workspace_root,
            repository_root=repository_root,
            expected_base_sha=str(raw["expected_base_sha"]).lower(),
            branch=branch,
            allowed_paths=tuple(allowed_paths),
            patch_source=str(raw["patch_source"]),
            declared_patch=str(raw["declared_patch"]) if "declared_patch" in raw else None,
            worker_request=worker_request,
            test_command=tuple(str(part) for part in raw["test_command"]),  # type: ignore[union-attr]
            test_timeout=int(raw["test_timeout"]),
            retry_limit=int(raw["retry_limit"]),
            stopping_condition=str(raw["stopping_condition"]),
            rollback_command_description=str(raw["rollback_command_description"]).strip(),
            implementer=implementer,
            reviewer=reviewer,
            reviewer_authority=str(raw["reviewer_authority"]),
            countercase=countercase,
        )

    def to_dict(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "identifier": self.identifier,
            "objective": self.objective,
            "workspace_root": str(self.workspace_root),
            "repository_root": str(self.repository_root),
            "expected_base_sha": self.expected_base_sha,
            "branch": self.branch,
            "allowed_paths": list(self.allowed_paths),
            "patch_source": self.patch_source,
            "test_command": list(self.test_command),
            "test_timeout": self.test_timeout,
            "retry_limit": self.retry_limit,
            "stopping_condition": self.stopping_condition,
            "rollback_command_description": self.rollback_command_description,
            "implementer": self.implementer,
            "reviewer": self.reviewer,
            "reviewer_authority": self.reviewer_authority,
            "countercase": self.countercase,
        }
        if self.declared_patch is not None:
            raw["declared_patch"] = self.declared_patch
        if self.worker_request is not None:
            raw["worker_request"] = _thaw_json(self.worker_request)
        return raw


class RepositoryMissionService:
    """Persist guarded repository mission contracts and their state history."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def create(
        self,
        contract: RepositoryMissionContract,
        actor: str,
        authority: str,
    ) -> int:
        if not actor.strip():
            raise RepositoryMissionError("actor is required")
        if authority != "repository:execute":
            raise RepositoryMissionError("repository:execute authority is required")
        contract_json = json.dumps(contract.to_dict(), sort_keys=True, separators=(",", ":"))
        with self.store.db:
            cursor = self.store.db.execute(
                """
                INSERT INTO repository_missions(
                    identifier, objective, workspace_root, repository_root,
                    expected_base_sha, branch, allowed_paths_json, patch_source,
                    contract_json, status, actor, authority, current_head
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'created', ?, ?, ?)
                """,
                (
                    contract.identifier,
                    contract.objective,
                    str(contract.workspace_root),
                    str(contract.repository_root),
                    contract.expected_base_sha,
                    contract.branch,
                    json.dumps(contract.allowed_paths),
                    contract.patch_source,
                    contract_json,
                    actor,
                    authority,
                    contract.expected_base_sha,
                ),
            )
            mission_id = int(cursor.lastrowid)
            self.store.db.execute(
                """
                INSERT INTO repository_mission_transitions(
                    mission_id, from_state, to_state, actor, authority,
                    repository_head, reason, evidence_ids_json
                ) VALUES (?, NULL, 'created', ?, ?, ?, 'contract accepted', '[]')
                """,
                (mission_id, actor, authority, contract.expected_base_sha),
            )
        return mission_id
