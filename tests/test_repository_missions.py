from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from erasmus.migrations import apply_migrations, rollback_repository_mission_migration
from erasmus.cli.main import main
from erasmus.repository_missions import (
    LocalGitRunner,
    PatchGate,
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

    mission_id = RepositoryMissionService(
        store, authority_rules=authority_rules(repository)
    ).create(
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


def test_repository_mission_migration_rollback_removes_only_additive_schema(
    tmp_path: Path,
) -> None:
    db = sqlite3.connect(tmp_path / "rollback.db")
    apply_migrations(db)

    rollback_repository_mission_migration(db)

    names = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "events" in names
    assert "repository_missions" not in names
    assert db.execute("SELECT 1 FROM schema_version WHERE version = 17").fetchone() is None
    assert apply_migrations(db) == [17]


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")
    assert executable is not None
    return subprocess.run(
        [executable, *args],
        cwd=repo,
        shell=False,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def git_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "--initial-branch=main")
    git(repository, "config", "user.name", "Repository Mission Test")
    git(repository, "config", "user.email", "repository-mission@example.invalid")
    (repository / "fixture.txt").write_text("before\n", encoding="utf-8")
    (repository / "other.txt").write_text("untouched\n", encoding="utf-8")
    git(repository, "add", "fixture.txt", "other.txt")
    git(repository, "commit", "-m", "fixture base")
    return repository, git(repository, "rev-parse", "HEAD").stdout.strip()


def text_patch(path: str = "fixture.txt") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
    )


def test_patch_gate_applies_valid_text_patch_and_returns_bounded_evidence(
    tmp_path: Path,
) -> None:
    repository, head = git_repository(tmp_path)

    evidence = PatchGate(LocalGitRunner()).validate_and_apply(
        repository, text_patch(), ("fixture.txt",), head
    )

    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "after\n"
    assert evidence.patch_digest == hashlib.sha256(text_patch().encode("utf-8")).hexdigest()
    assert evidence.changed_paths == ("fixture.txt",)
    assert evidence.expected_head == head
    assert evidence.commands
    assert all(len(command.stdout_excerpt) <= 4096 for command in evidence.commands)
    assert all("PATH=" not in command.stdout_excerpt for command in evidence.commands)


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ("", "empty"),
        ("this is prose, not a patch", "malformed"),
        ("diff --git a/fixture.txt b/fixture.txt\nGIT binary patch\nliteral 1\nAcmZQz\n", "binary"),
        (
            "diff --git /absolute.txt /absolute.txt\n"
            "--- /absolute.txt\n+++ /absolute.txt\n@@ -1 +1 @@\n-x\n+y\n",
            "absolute",
        ),
        (
            "diff --git a/../escape.txt b/../escape.txt\n"
            "--- a/../escape.txt\n+++ b/../escape.txt\n@@ -1 +1 @@\n-x\n+y\n",
            "traversal",
        ),
        (
            "diff --git a/fixture.txt b/outside.txt\n"
            "similarity index 100%\nrename from fixture.txt\nrename to outside.txt\n",
            "outside",
        ),
    ],
)
def test_patch_gate_rejects_unsafe_or_malformed_patch(
    tmp_path: Path, patch: str, message: str
) -> None:
    repository, head = git_repository(tmp_path)

    with pytest.raises(RepositoryMissionError, match=message):
        PatchGate(LocalGitRunner()).validate_and_apply(
            repository, patch, ("fixture.txt",), head
        )

    assert git(repository, "status", "--porcelain").stdout == ""


def test_patch_gate_rejects_dirty_tree(tmp_path: Path) -> None:
    repository, head = git_repository(tmp_path)
    (repository / "fixture.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(RepositoryMissionError, match="clean"):
        PatchGate(LocalGitRunner()).validate_and_apply(
            repository, text_patch(), ("fixture.txt",), head
        )


def test_patch_gate_rejects_stale_head(tmp_path: Path) -> None:
    repository, _ = git_repository(tmp_path)

    with pytest.raises(RepositoryMissionError, match="HEAD"):
        PatchGate(LocalGitRunner()).validate_and_apply(
            repository, text_patch(), ("fixture.txt",), "f" * 40
        )


def test_patch_gate_rejects_disallowed_path(tmp_path: Path) -> None:
    repository, head = git_repository(tmp_path)

    with pytest.raises(RepositoryMissionError, match="allowed"):
        PatchGate(LocalGitRunner()).validate_and_apply(
            repository, text_patch(), ("other.txt",), head
        )

    assert git(repository, "status", "--porcelain").stdout == ""


def repository_with_bare_origin(tmp_path: Path) -> tuple[Path, Path, str]:
    repository, head = git_repository(tmp_path)
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    git(repository, "remote", "add", "origin", str(origin))
    git(repository, "push", "origin", "main:main")
    return repository, origin, head


def mission_contract(
    repository: Path,
    head: str,
    *,
    source: str = "declared",
    branch: str = "mission/bounded-change",
    test_command: list[str] | None = None,
) -> RepositoryMissionContract:
    changes: dict[str, object] = {
        "workspace_root": str(repository.parent),
        "expected_base_sha": head,
        "branch": branch,
        "test_command": test_command
        or [sys.executable, "-c", "from pathlib import Path; assert Path('fixture.txt').read_text() == 'after\\n'"],
    }
    if source == "worker":
        changes.update(
            patch_source="worker",
            declared_patch=None,
            worker_request={"instruction": "Change only fixture.txt from before to after."},
        )
    raw = contract_data(repository, **changes)
    if source == "worker":
        raw.pop("declared_patch")
    return RepositoryMissionContract.from_dict(raw)


def authority_rules(
    repository: Path, *, process: bool = True, review: bool = True
) -> list[dict[str, str]]:
    rules = [{
        "actor": "Protomentat",
        "operation": "repository_execute",
        "scope": str(repository.resolve()),
        "effect": "allow",
    }]
    if process:
        rules.append({
            "actor": "Protomentat",
            "operation": "process_execute",
            "scope": str(repository.resolve()),
            "effect": "allow",
        })
    if review:
        rules.append({
            "actor": "reviewer-beta",
            "operation": "independent_review",
            "scope": "*",
            "effect": "allow",
        })
    return rules


def mission_service(
    tmp_path: Path, repository: Path, *, process: bool = True, review: bool = True
) -> RepositoryMissionService:
    store = Store(str(tmp_path / "state.db"))
    store.init()
    return RepositoryMissionService(
        store,
        authority_rules=authority_rules(repository, process=process, review=review),
    )


def test_declared_repository_mission_reaches_awaiting_human_and_pushes_branch(
    tmp_path: Path,
) -> None:
    repository, origin, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(repository, head)
    mission_id = service.create(contract, "Protomentat", "repository:execute")

    result = service.run(mission_id)

    assert result["state"] == "awaiting_human"
    assert git(origin, "rev-parse", f"refs/heads/{contract.branch}").stdout.strip() == result["draft_pr"]["head_sha"]
    assert [transition["to_state"] for transition in result["transitions"]] == [
        "created",
        "authorized",
        "inspecting",
        "branched",
        "patch_validated",
        "changed",
        "tested",
        "reviewed",
        "draft_pr_recorded",
        "awaiting_human",
    ]
    assert result["draft_pr"]["changed_paths"] == ["fixture.txt"]
    assert result["draft_pr"]["rollback_sha"] == head
    patch_evidence = next(item for item in result["evidence"] if item["kind"] == "patch")
    review_evidence = next(item for item in result["evidence"] if item["kind"] == "review")
    test_evidence = next(item for item in result["evidence"] if item["kind"] == "test")
    assert review_evidence["data"]["head_sha"] == result["draft_pr"]["head_sha"]
    assert review_evidence["data"]["diff_digest"] == patch_evidence["data"]["repository_snapshot"]["diff_digest"]
    assert review_evidence["data"]["capability"] == "invoke_tenth_man_review@1.0.0"
    assert test_evidence["data"]["capability"] == "run_tests@1.0.0"


def test_governed_worker_uses_same_gate_without_repository_authority(
    tmp_path: Path,
) -> None:
    repository, origin, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(repository, head, source="worker", branch="mission/worker-change")
    mission_id = service.create(contract, "Protomentat", "repository:execute")
    requests: list[dict[str, object]] = []

    def provider(request):
        requests.append(dict(request))
        return text_patch()

    result = service.run(mission_id, provider)

    assert result["state"] == "awaiting_human"
    assert requests == [{"instruction": "Change only fixture.txt from before to after."}]
    assert "repository_root" not in requests[0]
    assert "authority" not in requests[0]
    assert git(origin, "rev-parse", "refs/heads/mission/worker-change").returncode == 0


def test_failed_tests_restore_recorded_base_and_enter_rolled_back(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(
        repository,
        head,
        test_command=[sys.executable, "-c", "raise SystemExit(7)"],
    )
    mission_id = service.create(contract, "Protomentat", "repository:execute")

    with pytest.raises(RepositoryMissionError, match="tests failed"):
        service.run(mission_id)

    inspected = service.inspect(mission_id)
    assert inspected["state"] == "rolled_back"
    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "before\n"
    assert git(repository, "rev-parse", "HEAD").stdout.strip() == head
    assert git(repository, "status", "--porcelain").stdout == ""
    assert any(evidence["kind"] == "rollback" for evidence in inspected["evidence"])


def test_malformed_worker_response_is_quarantined_without_changes(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(repository, head, source="worker", branch="mission/malformed")
    mission_id = service.create(contract, "Protomentat", "repository:execute")

    with pytest.raises(RepositoryMissionError, match="malformed"):
        service.run(mission_id, lambda _: "I changed the file for you.")

    assert service.inspect(mission_id)["state"] == "quarantined"
    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "before\n"


def test_run_blocks_when_persisted_execution_authority_is_denied(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )
    with service.store.db:
        service.store.db.execute(
            "UPDATE repository_missions SET authority = 'repository:inspect' WHERE id = ?",
            (mission_id,),
        )

    with pytest.raises(RepositoryMissionError, match="authority"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "blocked"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("reviewer", "worker-alpha", "reviewer"), ("countercase", "", "countercase")],
)
def test_run_blocks_corrupted_review_boundaries_before_draft_creation(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )
    row = service.store.db.execute(
        "SELECT contract_json FROM repository_missions WHERE id = ?", (mission_id,)
    ).fetchone()
    raw = json.loads(row["contract_json"])
    raw[field] = value
    with service.store.db:
        service.store.db.execute(
            "UPDATE repository_missions SET contract_json = ? WHERE id = ?",
            (json.dumps(raw), mission_id),
        )

    with pytest.raises(RepositoryMissionError, match=message):
        service.run(mission_id)

    inspected = service.inspect(mission_id)
    assert inspected["state"] == "blocked"
    assert inspected["draft_pr"] is None


def test_push_failure_retains_local_commit_and_blocks_with_rollback_command(
    tmp_path: Path,
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    git(repository, "remote", "remove", "origin")
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )

    with pytest.raises(RepositoryMissionError, match="origin"):
        service.run(mission_id)

    inspected = service.inspect(mission_id)
    assert inspected["state"] == "blocked"
    assert git(repository, "rev-parse", "HEAD").stdout.strip() != head
    assert head in inspected["rollback_command"]


def test_interrupted_worker_mission_resumes_without_duplicate_commit_or_draft(
    tmp_path: Path,
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(repository, head, source="worker", branch="mission/resumed")
    mission_id = service.create(contract, "Protomentat", "repository:execute")

    def interrupted(_):
        raise KeyboardInterrupt("simulated interruption")

    with pytest.raises(KeyboardInterrupt, match="simulated"):
        service.run(mission_id, interrupted)
    assert service.inspect(mission_id)["state"] == "branched"

    result = service.run(mission_id, lambda _: text_patch())

    assert result["state"] == "awaiting_human"
    assert git(repository, "rev-list", "--count", f"{head}..HEAD").stdout.strip() == "1"
    assert len([draft for draft in [result["draft_pr"]] if draft]) == 1
    assert service.run(mission_id, lambda _: pytest.fail("provider called after completion"))["state"] == "awaiting_human"


def test_interrupted_worker_mission_blocks_on_worktree_mismatch(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    contract = mission_contract(repository, head, source="worker", branch="mission/mismatch")
    mission_id = service.create(contract, "Protomentat", "repository:execute")

    with pytest.raises(KeyboardInterrupt):
        service.run(mission_id, lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    (repository / "fixture.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(RepositoryMissionError, match="durable branched state"):
        service.run(mission_id, lambda _: text_patch())

    assert service.inspect(mission_id)["state"] == "blocked"


def test_repository_execution_requires_policy_decision(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    store = Store(str(tmp_path / "denied.db"))
    store.init()

    with pytest.raises(RepositoryMissionError, match="authority policy denied"):
        RepositoryMissionService(store, authority_rules=[]).create(
            mission_contract(repository, head), "Protomentat", "repository:execute"
        )


def test_process_execution_denial_restores_mission_paths(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository, process=False)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )

    with pytest.raises(RepositoryMissionError, match="process_execute"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "blocked"
    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "before\n"
    assert git(repository, "status", "--porcelain").stdout == ""


def test_independent_review_requires_policy_decision(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository, review=False)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )

    with pytest.raises(RepositoryMissionError, match="independent_review"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "blocked"


@pytest.mark.parametrize(
    "test_command",
    [
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('fixture.txt').write_text('evil\\n')",
        ],
        [str(Path(shutil.which("git") or "git").resolve()), "commit", "-am", "evil test commit"],
    ],
)
def test_test_command_repository_mutation_is_rejected_and_rolled_back(
    tmp_path: Path, test_command: list[str]
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head, test_command=test_command),
        "Protomentat",
        "repository:execute",
    )

    with pytest.raises(RepositoryMissionError, match="mutated repository state"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "rolled_back"
    assert git(repository, "rev-parse", "HEAD").stdout.strip() == head
    assert git(repository, "status", "--porcelain").stdout == ""


def test_test_command_merge_commit_is_functionally_rejected(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    git(repository, "switch", "-c", "side")
    (repository / "other.txt").write_text("side\n", encoding="utf-8")
    git(repository, "commit", "-am", "side change")
    git(repository, "switch", "main")
    service = mission_service(tmp_path, repository)
    test_command = [
        str(Path(shutil.which("git") or "git").resolve()),
        "merge",
        "side",
        "--no-ff",
        "-m",
        "evil merge",
    ]
    mission_id = service.create(
        mission_contract(repository, head, test_command=test_command),
        "Protomentat",
        "repository:execute",
    )

    with pytest.raises(RepositoryMissionError, match="merge commit"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "rolled_back"
    assert git(repository, "rev-list", "--merges", "mission/bounded-change").stdout == ""


def test_post_apply_quarantine_restores_mission_owned_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )
    original = PatchGate.validate_and_apply

    def fail_after_apply(gate, *args, **kwargs):
        original(gate, *args, **kwargs)
        raise RepositoryMissionError("post-apply provenance failure")

    monkeypatch.setattr(PatchGate, "validate_and_apply", fail_after_apply)
    with pytest.raises(RepositoryMissionError, match="post-apply"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "quarantined"
    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "before\n"
    assert git(repository, "status", "--porcelain").stdout == ""


def test_recovery_rejects_same_path_with_different_diff_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )
    with monkeypatch.context() as context:
        context.setattr(
            service,
            "_run_test_command",
            lambda _: (_ for _ in ()).throw(KeyboardInterrupt("after patch")),
        )
        with pytest.raises(KeyboardInterrupt):
            service.run(mission_id)
    assert service.inspect(mission_id)["state"] == "changed"
    (repository / "fixture.txt").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RepositoryMissionError, match="snapshot"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "blocked"
    assert (repository / "fixture.txt").read_text(encoding="utf-8") == "before\n"


def test_recovery_rejects_existing_commit_with_wrong_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )
    with monkeypatch.context() as context:
        context.setattr(
            service,
            "_commit_and_push",
            lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("before commit")),
        )
        with pytest.raises(KeyboardInterrupt):
            service.run(mission_id)
    assert service.inspect(mission_id)["state"] == "tested"
    (repository / "fixture.txt").write_text("wrong tree\n", encoding="utf-8")
    git(repository, "add", "fixture.txt")
    git(repository, "commit", "-m", "Repository mission bounded-change")

    with pytest.raises(RepositoryMissionError, match="commit tree"):
        service.run(mission_id)

    assert service.inspect(mission_id)["state"] == "blocked"
    assert git(repository, "rev-parse", "HEAD").stdout.strip() == head


def test_evidence_is_deduplicated_across_recovery_boundaries(tmp_path: Path) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    service = mission_service(tmp_path, repository)
    mission_id = service.create(
        mission_contract(repository, head), "Protomentat", "repository:execute"
    )

    first = service._store_evidence(mission_id, "test-boundary", {"value": 1})
    second = service._store_evidence(mission_id, "test-boundary", {"value": 1})

    assert first == second
    assert service.store.db.execute(
        "SELECT COUNT(*) FROM repository_mission_evidence WHERE mission_id = ? AND kind = 'test-boundary'",
        (mission_id,),
    ).fetchone()[0] == 1
    service._transition(mission_id, "authorized", "deduplicated boundary", head)
    service._transition(mission_id, "authorized", "deduplicated boundary", head)
    assert service.store.db.execute(
        "SELECT COUNT(*) FROM repository_mission_transitions WHERE mission_id = ? AND to_state = 'authorized'",
        (mission_id,),
    ).fetchone()[0] == 1


def test_repository_mission_cli_create_run_and_inspect_emit_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _, head = repository_with_bare_origin(tmp_path)
    contract = mission_contract(repository, head)
    contract_path = tmp_path / "repository-mission.json"
    contract_path.write_text(json.dumps(contract.to_dict()), encoding="utf-8")
    rules_path = tmp_path / "authority-rules.json"
    rules_path.write_text(json.dumps({"rules": authority_rules(repository)}), encoding="utf-8")
    database = tmp_path / "cli.db"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(database),
            "repository-mission-create",
            "--contract",
            str(contract_path),
            "--actor",
            "Protomentat",
            "--authority-rules",
            str(rules_path),
        ],
    )
    main()
    created = json.loads(capsys.readouterr().out)
    assert created["state"] == "created"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus", "--db", str(database), "repository-mission-run",
            str(created["mission_id"]), "--authority-rules", str(rules_path),
        ],
    )
    main()
    run = json.loads(capsys.readouterr().out)
    assert run["state"] == "awaiting_human"

    monkeypatch.setattr(
        sys,
        "argv",
        ["erasmus", "--db", str(database), "repository-mission-inspect", str(created["mission_id"])],
    )
    main()
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["draft_pr"]["head_sha"] == run["draft_pr"]["head_sha"]


def test_repository_mission_cli_registers_no_merge_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["erasmus", "repository-mission-merge", "1"])

    with pytest.raises(SystemExit, match="2"):
        main()

    error = capsys.readouterr().err
    assert "invalid choice: 'repository-mission-merge'" in error
    assert "repository-mission-create" in error
    assert "repository-mission-run" in error
    assert "repository-mission-inspect" in error


def test_repository_mission_cli_cannot_self_grant_execution_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["erasmus", "repository-mission-create", "--contract", str(contract_path)],
    )

    with pytest.raises(SystemExit, match="2"):
        main()
