"""Deterministic guarded missions for bounded local Git repositories."""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .store import Store


class RepositoryMissionError(ValueError):
    """Raised when a repository mission violates a deterministic boundary."""


@dataclass(frozen=True)
class GitCommandEvidence:
    args: tuple[str, ...]
    returncode: int
    stdout_digest: str
    stderr_digest: str
    stdout_excerpt: str
    stderr_excerpt: str


@dataclass(frozen=True)
class PatchEvidence:
    patch_digest: str
    changed_paths: tuple[str, ...]
    expected_head: str
    commands: tuple[GitCommandEvidence, ...]


class LocalGitRunner:
    """Run a discovered local Git executable without a command shell."""

    def __init__(self) -> None:
        discovered = shutil.which("git")
        if discovered is None:
            raise RepositoryMissionError("Git executable was not found")
        self.executable = Path(discovered).resolve(strict=True)
        if not self.executable.is_file() or not self.executable.is_absolute():
            raise RepositoryMissionError("Git executable must resolve to an absolute file")

    def run(
        self,
        repo: Path,
        args: tuple[str, ...],
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        if not isinstance(args, tuple) or not all(isinstance(arg, str) for arg in args):
            raise RepositoryMissionError("Git arguments must be an exact tuple of strings")
        root = repo.resolve(strict=True)
        if not root.is_dir():
            raise RepositoryMissionError("Git repository root must be a directory")
        try:
            return subprocess.run(
                [str(self.executable), *args],
                cwd=root,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryMissionError(f"Git command timed out: {args[0] if args else 'git'}") from exc


def _command_evidence(
    args: tuple[str, ...], completed: subprocess.CompletedProcess[str]
) -> GitCommandEvidence:
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return GitCommandEvidence(
        args=args,
        returncode=completed.returncode,
        stdout_digest=hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        stderr_digest=hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        stdout_excerpt=stdout[:4096],
        stderr_excerpt=stderr[:4096],
    )


def _safe_relative_git_path(raw_path: str, *, label: str) -> str:
    if raw_path in {"", "/dev/null"}:
        if raw_path == "/dev/null":
            return raw_path
        raise RepositoryMissionError(f"{label} contains an empty path")
    if "\\" in raw_path:
        raise RepositoryMissionError(f"{label} contains a non-portable path")
    if re.match(r"^[A-Za-z]:/", raw_path) or raw_path.startswith("/"):
        raise RepositoryMissionError(f"{label} contains an absolute path")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RepositoryMissionError(f"{label} contains path traversal")
    return path.as_posix()


def _prefixed_patch_path(token: str, prefix: str, *, label: str) -> str:
    if token == "/dev/null":
        return token
    if not token.startswith(prefix):
        if token.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", token):
            raise RepositoryMissionError(f"{label} contains an absolute path")
        raise RepositoryMissionError(f"malformed {label} path")
    return _safe_relative_git_path(token[len(prefix):], label=label)


def _parse_patch_paths(patch_text: str) -> tuple[str, ...]:
    if not patch_text.strip():
        raise RepositoryMissionError("patch is empty")
    if len(patch_text.encode("utf-8", errors="strict")) > 1_048_576:
        raise RepositoryMissionError("patch exceeds the bounded size")
    if "\x00" in patch_text or "GIT binary patch" in patch_text or "Binary files " in patch_text:
        raise RepositoryMissionError("binary patches are not supported")
    if "160000" in patch_text or "Subproject commit " in patch_text:
        raise RepositoryMissionError("submodule patches are not supported")

    paths: set[str] = set()
    saw_diff = False
    section_has_file_headers = False
    section_has_rename_pair: set[str] = set()
    in_hunk = False

    def finish_section() -> None:
        if saw_diff and not section_has_file_headers and section_has_rename_pair != {"from", "to"}:
            raise RepositoryMissionError("malformed patch section lacks file headers")

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            finish_section()
            tokens = line.split(" ")
            if len(tokens) != 4 or tokens[:2] != ["diff", "--git"]:
                raise RepositoryMissionError("malformed diff --git header")
            old_path = _prefixed_patch_path(tokens[2], "a/", label="diff")
            new_path = _prefixed_patch_path(tokens[3], "b/", label="diff")
            paths.update((old_path, new_path))
            saw_diff = True
            section_has_file_headers = False
            section_has_rename_pair = set()
            in_hunk = False
            continue
        if not saw_diff:
            raise RepositoryMissionError("malformed patch: expected diff --git header")
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if in_hunk:
            continue
        if line.startswith("--- "):
            path = _prefixed_patch_path(line[4:], "a/", label="old file")
            if path != "/dev/null":
                paths.add(path)
            section_has_file_headers = True
            continue
        if line.startswith("+++ "):
            path = _prefixed_patch_path(line[4:], "b/", label="new file")
            if path != "/dev/null":
                paths.add(path)
            section_has_file_headers = True
            continue
        metadata = (
            "index ", "old mode ", "new mode ", "new file mode ",
            "deleted file mode ", "similarity index ", "dissimilarity index ",
        )
        if line.startswith(metadata):
            continue
        for prefix, marker in (
            ("rename from ", "from"),
            ("rename to ", "to"),
            ("copy from ", "from"),
            ("copy to ", "to"),
        ):
            if line.startswith(prefix):
                paths.add(_safe_relative_git_path(line[len(prefix):], label=prefix.strip()))
                section_has_rename_pair.add(marker)
                break
        else:
            if line:
                raise RepositoryMissionError(f"unsupported patch metadata: {line[:80]}")
    finish_section()
    if not saw_diff or not paths:
        raise RepositoryMissionError("malformed patch")
    paths.discard("/dev/null")
    return tuple(sorted(paths))


class PatchGate:
    """Validate and apply unified text patches through one deterministic gate."""

    def __init__(self, runner: LocalGitRunner) -> None:
        self.runner = runner

    def validate_and_apply(
        self,
        repo: Path,
        patch_text: str,
        allowed_paths: tuple[str, ...],
        expected_head: str,
    ) -> PatchEvidence:
        try:
            patch_text.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise RepositoryMissionError("patch is not valid UTF-8 text") from exc
        parsed_paths = _parse_patch_paths(patch_text)
        allowed = {
            _safe_relative_git_path(path, label="allowed paths")
            for path in allowed_paths
        }
        outside = sorted(set(parsed_paths) - allowed)
        if outside:
            raise RepositoryMissionError(f"patch path is outside allowed paths: {outside[0]}")

        root = repo.resolve(strict=True)
        commands: list[GitCommandEvidence] = []

        def run(args: tuple[str, ...], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            completed = self.runner.run(root, args, timeout)
            commands.append(_command_evidence(args, completed))
            return completed

        head_args = ("rev-parse", "HEAD")
        head = run(head_args)
        if head.returncode != 0:
            raise RepositoryMissionError("unable to inspect repository HEAD")
        actual_head = head.stdout.strip().lower()
        if actual_head != expected_head.lower():
            raise RepositoryMissionError(
                f"repository HEAD does not match expected HEAD {expected_head}"
            )
        status_args = ("status", "--porcelain", "--untracked-files=normal")
        status = run(status_args)
        if status.returncode != 0:
            raise RepositoryMissionError("unable to inspect repository cleanliness")
        if status.stdout:
            raise RepositoryMissionError("repository must have a clean worktree")

        patch_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix=".patch",
                prefix="erasmus-mission-",
                dir=root.parent,
                delete=False,
            ) as patch_file:
                patch_file.write(patch_text)
                patch_path = Path(patch_file.name)
            check_args = ("apply", "--check", "--whitespace=nowarn", str(patch_path))
            checked = run(check_args)
            if checked.returncode != 0:
                raise RepositoryMissionError(
                    f"malformed or inapplicable patch: {checked.stderr[:500]}"
                )
            apply_args = ("apply", "--whitespace=nowarn", str(patch_path))
            applied = run(apply_args)
            if applied.returncode != 0:
                raise RepositoryMissionError(f"patch application failed: {applied.stderr[:500]}")
        finally:
            if patch_path is not None:
                patch_path.unlink(missing_ok=True)

        diff_args = ("diff", "--name-only", "--no-renames", "HEAD")
        changed = run(diff_args)
        if changed.returncode != 0:
            raise RepositoryMissionError("unable to verify changed paths after patch application")
        untracked_args = ("ls-files", "--others", "--exclude-standard")
        untracked = run(untracked_args)
        if untracked.returncode != 0:
            raise RepositoryMissionError("unable to verify new paths after patch application")
        changed_paths = tuple(sorted({
            _safe_relative_git_path(line, label="changed paths")
            for line in (*changed.stdout.splitlines(), *untracked.stdout.splitlines())
            if line
        }))
        post_outside = sorted(set(changed_paths) - allowed)
        if post_outside:
            run(("reset", "--hard", expected_head))
            run(("clean", "-fd"))
            raise RepositoryMissionError(
                f"applied patch changed a path outside allowed paths: {post_outside[0]}"
            )
        if set(changed_paths) != set(parsed_paths):
            raise RepositoryMissionError("applied changes do not match declared patch paths")
        return PatchEvidence(
            patch_digest=hashlib.sha256(patch_text.encode("utf-8")).hexdigest(),
            changed_paths=changed_paths,
            expected_head=actual_head,
            commands=tuple(commands),
        )


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
