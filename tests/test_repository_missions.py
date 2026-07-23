from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from erasmus.migrations import apply_migrations
from erasmus.repository_missions import (
    RepositoryMissionContract,
    RepositoryMissionError,
    RepositoryMissionService,
)
from erasmus.store import Store


def contract_data(repository: Path, **overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "identifier": "bounded-change",
        "objective": "Change the declared fixture file",
        "workspace_root": str(repository.parent),
        "repository_root": str(repository),
        "expected_base_sha": "a" * 40,
        "branch": "mission/bounded-change",
        "allowed_paths": ["fixture.txt"],
        "patch_source": "declared",
        "declared_patch": (
            "diff --git a/fixture.txt b/fixture.txt\n"
            "--- a/fixture.txt\n"
            "+++ b/fixture.txt\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        ),
        "test_command": ["python", "-c", "print('ok')"],
        "test_timeout": 30,
        "retry_limit": 0,
        "stopping_condition": "awaiting_human",
        "rollback_command_description": "Reset the mission branch to its recorded base SHA",
        "implementer": "worker-alpha",
        "reviewer": "reviewer-beta",
        "reviewer_authority": "repository:review",
        "countercase": "The local fixture may not expose hosted branch-protection failures.",
    }
    raw.update(overrides)
    return raw


def test_contract_requires_every_declared_field(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    raw = contract_data(repository)
    del raw["objective"]

    with pytest.raises(RepositoryMissionError, match="objective"):
        RepositoryMissionContract.from_dict(raw)


def test_contract_resolves_root_inside_declared_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repository = workspace / "repo"
    repository.mkdir(parents=True)

    contract = RepositoryMissionContract.from_dict(contract_data(repository))

    assert contract.repository_root == repository.resolve()
    assert contract.workspace_root == workspace.resolve()


def test_contract_rejects_resolved_root_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repository = tmp_path / "outside"
    workspace.mkdir()
    repository.mkdir()

    with pytest.raises(RepositoryMissionError, match="outside workspace_root"):
        RepositoryMissionContract.from_dict(
            contract_data(repository, workspace_root=str(workspace))
        )


@pytest.mark.parametrize("path", ["/absolute.txt", "C:/absolute.txt", "../escape.txt", "a/../../escape.txt"])
def test_contract_rejects_non_relative_or_traversing_allowed_paths(
    tmp_path: Path, path: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(RepositoryMissionError, match="allowed_paths"):
        RepositoryMissionContract.from_dict(
            contract_data(repository, allowed_paths=[path])
        )


def test_contract_requires_independent_reviewer(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(RepositoryMissionError, match="reviewer"):
        RepositoryMissionContract.from_dict(
            contract_data(repository, reviewer="worker-alpha")
        )


def test_contract_requires_a_tenth_man_countercase(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(RepositoryMissionError, match="countercase"):
        RepositoryMissionContract.from_dict(contract_data(repository, countercase=" "))


def test_contract_is_immutable(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    contract = RepositoryMissionContract.from_dict(contract_data(repository))

    with pytest.raises(FrozenInstanceError):
        contract.objective = "changed"  # type: ignore[misc]


def test_create_persists_mission_and_append_only_created_transition(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = Store(str(tmp_path / "state.db"))
    store.init()
    contract = RepositoryMissionContract.from_dict(contract_data(repository))

    mission_id = RepositoryMissionService(store).create(
        contract, actor="Protomentat", authority="repository:execute"
    )

    row = store.db.execute(
        "SELECT identifier, status, contract_json FROM repository_missions WHERE id = ?",
        (mission_id,),
    ).fetchone()
    assert (row["identifier"], row["status"]) == ("bounded-change", "created")
    assert json.loads(row["contract_json"])["objective"] == contract.objective
    transition = store.db.execute(
        "SELECT from_state, to_state, actor, authority FROM repository_mission_transitions "
        "WHERE mission_id = ?",
        (mission_id,),
    ).fetchone()
    assert tuple(transition) == (None, "created", "Protomentat", "repository:execute")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with store.db:
            store.db.execute(
                "UPDATE repository_mission_transitions SET reason = 'rewritten' WHERE mission_id = ?",
                (mission_id,),
            )


def test_repository_mission_migration_is_idempotent(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "migration.db")
    first = apply_migrations(db)
    second = apply_migrations(db)

    assert 17 in first
    assert second == []
    assert {
        "repository_missions",
        "repository_mission_transitions",
        "repository_mission_evidence",
        "draft_pull_requests",
    } <= {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
