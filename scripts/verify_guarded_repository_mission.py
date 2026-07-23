#!/usr/bin/env python3
"""Verify both guarded repository patch modes against disposable local Git state."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from erasmus.repository_missions import (  # noqa: E402
    RepositoryMissionContract,
    RepositoryMissionService,
)
from erasmus.store import Store  # noqa: E402


PATCH = (
    "diff --git a/fixture.txt b/fixture.txt\n"
    "--- a/fixture.txt\n"
    "+++ b/fixture.txt\n"
    "@@ -1 +1 @@\n"
    "-before\n"
    "+after\n"
)


def run_git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    discovered = shutil.which("git")
    if discovered is None:
        raise RuntimeError("Git executable was not found")
    return subprocess.run(
        [str(Path(discovered).resolve(strict=True)), *args],
        cwd=repository,
        shell=False,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def contract(
    repository: Path,
    base_sha: str,
    identifier: str,
    branch: str,
    patch_source: str,
) -> RepositoryMissionContract:
    raw: dict[str, object] = {
        "identifier": identifier,
        "objective": "Verify the guarded local repository mission loop",
        "workspace_root": str(repository.parent),
        "repository_root": str(repository),
        "expected_base_sha": base_sha,
        "branch": branch,
        "allowed_paths": ["fixture.txt"],
        "patch_source": patch_source,
        "test_command": [
            sys.executable,
            "-c",
            "from pathlib import Path; assert Path('fixture.txt').read_text() == 'after\\n'",
        ],
        "test_timeout": 30,
        "retry_limit": 0,
        "stopping_condition": "awaiting_human",
        "rollback_command_description": "Reset the mission branch to its recorded base SHA",
        "implementer": f"{identifier}-worker",
        "reviewer": f"{identifier}-reviewer",
        "reviewer_authority": "repository:review",
        "countercase": "A local bare remote does not exercise hosted branch protection.",
    }
    if patch_source == "declared":
        raw["declared_patch"] = PATCH
    else:
        raw["worker_request"] = {"instruction": "Return the bounded fixture diff only."}
    return RepositoryMissionContract.from_dict(raw)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="erasmus-repository-mission-") as temporary:
        root = Path(temporary).resolve(strict=True)
        repository = root / "working"
        origin = root / "origin.git"
        repository.mkdir()
        run_git(repository, "init", "--initial-branch=main")
        run_git(repository, "config", "user.name", "Erasmus Mission Verifier")
        run_git(repository, "config", "user.email", "erasmus-verifier@example.invalid")
        (repository / "fixture.txt").write_text("before\n", encoding="utf-8")
        run_git(repository, "add", "fixture.txt")
        run_git(repository, "commit", "-m", "verification base")
        base_sha = run_git(repository, "rev-parse", "HEAD").stdout.strip()
        run_git(root, "init", "--bare", str(origin))
        run_git(repository, "remote", "add", "origin", str(origin))
        run_git(repository, "push", "origin", "main:main")

        store = Store(str(root / "state.db"))
        store.init()
        service = RepositoryMissionService(store)

        declared_id = service.create(
            contract(repository, base_sha, "manual-declared", "mission/manual-declared", "declared"),
            actor="Protomentat",
            authority="repository:execute",
        )
        declared = service.run(declared_id)

        run_git(repository, "switch", "main")
        worker_id = service.create(
            contract(repository, base_sha, "manual-worker", "mission/manual-worker", "worker"),
            actor="Protomentat",
            authority="repository:execute",
        )
        requests: list[dict[str, object]] = []

        def worker(request):
            requests.append(dict(request))
            return PATCH

        governed_worker = service.run(worker_id, worker)

        assert declared["state"] == "awaiting_human"
        assert governed_worker["state"] == "awaiting_human"
        assert requests == [{"instruction": "Return the bounded fixture diff only."}]
        run_git(origin, "show-ref", "--verify", "refs/heads/mission/manual-declared")
        run_git(origin, "show-ref", "--verify", "refs/heads/mission/manual-worker")
        print(
            json.dumps(
                {
                    "declared": declared["draft_pr"],
                    "worker": governed_worker["draft_pr"],
                    "verified_states": [declared["state"], governed_worker["state"]],
                    "remote_branches_verified": [
                        "mission/manual-declared",
                        "mission/manual-worker",
                    ],
                },
                indent=2,
            )
        )
        store.db.close()


if __name__ == "__main__":
    main()
