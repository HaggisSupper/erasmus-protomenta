"""Deterministic guarded missions for bounded local Git repositories."""
from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

try:
    from jsonschema import Draft202012Validator
except ImportError:  # The disposable verifier remains standard-library runnable.
    Draft202012Validator = None  # type: ignore[assignment,misc]

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


def _validate_contract_shape(raw: Mapping[str, object]) -> None:
    schema = _schema()
    if Draft202012Validator is not None:
        errors = sorted(
            Draft202012Validator(schema).iter_errors(dict(raw)),
            key=lambda error: list(error.path),
        )
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.absolute_path)
            label = location or "contract"
            if error.validator == "required":
                missing = re.search(r"'([^']+)'", error.message)
                if missing:
                    label = missing.group(1)
            raise RepositoryMissionError(f"{label}: {error.message}")
        return

    required = set(schema["required"])
    missing = sorted(required - set(raw))
    if missing:
        raise RepositoryMissionError(f"{missing[0]}: required property is missing")
    allowed = set(schema["properties"])
    extras = sorted(set(raw) - allowed)
    if extras:
        raise RepositoryMissionError(f"contract: additional property is not allowed: {extras[0]}")
    string_fields = required - {
        "allowed_paths", "test_command", "test_timeout", "retry_limit"
    }
    for field in string_fields:
        if not isinstance(raw[field], str) or not str(raw[field]).strip():
            raise RepositoryMissionError(f"{field}: non-empty string is required")
    if not isinstance(raw["allowed_paths"], list) or not raw["allowed_paths"] or not all(
        isinstance(path, str) and path for path in raw["allowed_paths"]
    ):
        raise RepositoryMissionError("allowed_paths: non-empty string array is required")
    if len(set(raw["allowed_paths"])) != len(raw["allowed_paths"]):
        raise RepositoryMissionError("allowed_paths: entries must be unique")
    if not isinstance(raw["test_command"], list) or not raw["test_command"] or not all(
        isinstance(argument, str) and argument for argument in raw["test_command"]
    ):
        raise RepositoryMissionError("test_command: non-empty argument array is required")
    for field, minimum, maximum in (("test_timeout", 1, 3600), ("retry_limit", 0, 10)):
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise RepositoryMissionError(f"{field}: integer must be between {minimum} and {maximum}")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(raw["expected_base_sha"])):
        raise RepositoryMissionError("expected_base_sha: 40 hexadecimal characters are required")
    if raw["patch_source"] not in {"declared", "worker"}:
        raise RepositoryMissionError("patch_source: must be declared or worker")
    if raw["stopping_condition"] != "awaiting_human":
        raise RepositoryMissionError("stopping_condition: must be awaiting_human")
    if raw["reviewer_authority"] != "repository:review":
        raise RepositoryMissionError("reviewer_authority: repository:review is required")
    if raw["patch_source"] == "declared":
        if not isinstance(raw.get("declared_patch"), str) or not raw["declared_patch"]:
            raise RepositoryMissionError("declared_patch: non-empty patch is required")
        if "worker_request" in raw:
            raise RepositoryMissionError("worker_request: not allowed for declared patch source")
    else:
        if not isinstance(raw.get("worker_request"), Mapping):
            raise RepositoryMissionError("worker_request: object is required")
        if "declared_patch" in raw:
            raise RepositoryMissionError("declared_patch: not allowed for worker patch source")


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
        _validate_contract_shape(raw)

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

    _TERMINAL_STATES = frozenset({"awaiting_human", "blocked", "quarantined", "failed", "rolled_back"})
    _NEXT_STATES = {
        "created": "authorized",
        "authorized": "inspecting",
        "inspecting": "branched",
        "branched": "patch_validated",
        "patch_validated": "changed",
        "changed": "tested",
        "tested": "reviewed",
        "reviewed": "draft_pr_recorded",
        "draft_pr_recorded": "awaiting_human",
    }

    def __init__(self, store: Store, runner: LocalGitRunner | None = None) -> None:
        self.store = store
        self.runner = runner or LocalGitRunner()

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

    def run(
        self,
        mission_id: int,
        worker_patch_provider: Any | None = None,
    ) -> dict[str, object]:
        row = self._mission_row(mission_id)
        state = str(row["status"])
        if state == "awaiting_human":
            return self.inspect(mission_id)
        if state in self._TERMINAL_STATES:
            raise RepositoryMissionError(f"mission {mission_id} is terminal in state {state}")
        if row["authority"] != "repository:execute":
            self._transition_terminal(
                mission_id,
                "blocked",
                "persisted execution authority is denied",
                str(row["current_head"] or row["expected_base_sha"]),
            )
            raise RepositoryMissionError("repository execution authority is denied")
        try:
            contract = RepositoryMissionContract.from_dict(json.loads(row["contract_json"]))
        except (json.JSONDecodeError, RepositoryMissionError) as exc:
            self._transition_terminal(
                mission_id,
                "blocked",
                f"persisted contract failed validation: {exc}",
                str(row["current_head"] or row["expected_base_sha"]),
            )
            raise RepositoryMissionError(str(exc)) from exc
        if str(contract.repository_root) != row["repository_root"]:
            self._transition_terminal(mission_id, "blocked", "repository root identity changed", contract.expected_base_sha)
            raise RepositoryMissionError("repository root identity changed")

        while True:
            state = str(self._mission_row(mission_id)["status"])
            if state == "awaiting_human":
                return self.inspect(mission_id)
            if state in self._TERMINAL_STATES:
                raise RepositoryMissionError(f"mission {mission_id} stopped in state {state}")
            if state == "created":
                authority_id = self._store_evidence(
                    mission_id,
                    "authority",
                    {"actor": row["actor"], "authority": row["authority"], "decision": "allowed"},
                )
                self._transition(
                    mission_id,
                    "authorized",
                    "declared repository execution authority accepted",
                    contract.expected_base_sha,
                    (authority_id,),
                )
                continue
            if state == "authorized":
                self._transition(
                    mission_id,
                    "inspecting",
                    "repository inspection started",
                    contract.expected_base_sha,
                )
                continue
            if state == "inspecting":
                try:
                    inspection_id = self._inspect_base(mission_id, contract)
                    self._ensure_mission_branch(contract)
                except RepositoryMissionError as exc:
                    self._transition_terminal(mission_id, "blocked", str(exc), contract.expected_base_sha)
                    raise
                self._transition(
                    mission_id,
                    "branched",
                    "bounded mission branch selected",
                    contract.expected_base_sha,
                    (inspection_id,),
                )
                continue
            if state == "branched":
                try:
                    self._validate_branched_state(contract)
                except RepositoryMissionError as exc:
                    self._transition_terminal(
                        mission_id, "blocked", str(exc), contract.expected_base_sha
                    )
                    raise
                try:
                    patch_text = self._obtain_patch(contract, worker_patch_provider)
                    patch = PatchGate(self.runner).validate_and_apply(
                        contract.repository_root,
                        patch_text,
                        contract.allowed_paths,
                        contract.expected_base_sha,
                    )
                except RepositoryMissionError as exc:
                    target = "blocked" if "provider is required" in str(exc) else "quarantined"
                    self._transition_terminal(mission_id, target, str(exc), contract.expected_base_sha)
                    raise
                patch_id = self._store_patch_evidence(mission_id, patch)
                self._transition(
                    mission_id,
                    "patch_validated",
                    "patch passed the shared deterministic gate",
                    contract.expected_base_sha,
                    (patch_id,),
                )
                continue
            if state == "patch_validated":
                patch_data = self._evidence_data(mission_id, "patch")
                self._validate_changed_paths(contract, patch_data["changed_paths"])
                self._transition(
                    mission_id,
                    "changed",
                    "validated patch changed only declared paths",
                    contract.expected_base_sha,
                )
                continue
            if state == "changed":
                patch_data = self._evidence_data(mission_id, "patch")
                self._validate_changed_paths(contract, patch_data["changed_paths"])
                completed, output = self._run_test_command(contract)
                test_id = self._store_evidence(
                    mission_id,
                    "test",
                    {
                        "command": list(contract.test_command),
                        "exit_status": completed.returncode,
                        "output_digest": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                        "output_excerpt": output[:8192],
                    },
                )
                if completed.returncode != 0:
                    rollback_id = self._rollback_owned_changes(mission_id, contract, test_id)
                    self._transition(
                        mission_id,
                        "rolled_back",
                        f"declared tests failed with exit status {completed.returncode}",
                        contract.expected_base_sha,
                        (test_id, rollback_id),
                    )
                    raise RepositoryMissionError(
                        f"declared tests failed with exit status {completed.returncode}"
                    )
                self._transition(
                    mission_id,
                    "tested",
                    "declared tests passed",
                    contract.expected_base_sha,
                    (test_id,),
                )
                continue
            if state == "tested":
                try:
                    head = self._commit_and_push(mission_id, contract)
                except RepositoryMissionError as exc:
                    current_head = self._git_output(contract.repository_root, ("rev-parse", "HEAD"), "inspect local commit").strip()
                    self._transition_terminal(mission_id, "blocked", str(exc), current_head)
                    raise
                if contract.reviewer.casefold() == contract.implementer.casefold():
                    self._transition_terminal(mission_id, "blocked", "reviewer is not independent", head)
                    raise RepositoryMissionError("reviewer must be independent")
                if contract.reviewer_authority != "repository:review":
                    self._transition_terminal(mission_id, "blocked", "review authority is denied", head)
                    raise RepositoryMissionError("review authority is denied")
                if not contract.countercase.strip():
                    self._transition_terminal(mission_id, "blocked", "countercase is required", head)
                    raise RepositoryMissionError("countercase is required")
                review_id = self._store_evidence(
                    mission_id,
                    "review",
                    {
                        "reviewer": contract.reviewer,
                        "authority": contract.reviewer_authority,
                        "countercase": contract.countercase,
                        "decision": "await_human",
                    },
                )
                self._transition(
                    mission_id,
                    "reviewed",
                    "independent deterministic review recorded",
                    head,
                    (review_id,),
                )
                continue
            if state == "reviewed":
                self._record_draft(mission_id, contract)
                continue
            if state == "draft_pr_recorded":
                head = self._git_output(contract.repository_root, ("rev-parse", "HEAD"), "inspect final HEAD").strip()
                self._transition(
                    mission_id,
                    "awaiting_human",
                    "draft comparison is ready for final human authority",
                    head,
                )
                continue
            raise RepositoryMissionError(f"unsupported repository mission state: {state}")

    def inspect(self, mission_id: int) -> dict[str, object]:
        row = self._mission_row(mission_id)
        transitions = []
        for transition in self.store.db.execute(
            "SELECT * FROM repository_mission_transitions WHERE mission_id = ? ORDER BY id",
            (mission_id,),
        ).fetchall():
            transitions.append(
                {
                    "id": transition["id"],
                    "from_state": transition["from_state"],
                    "to_state": transition["to_state"],
                    "actor": transition["actor"],
                    "authority": transition["authority"],
                    "repository_head": transition["repository_head"],
                    "reason": transition["reason"],
                    "evidence_ids": json.loads(transition["evidence_ids_json"]),
                    "created_at": transition["created_at"],
                }
            )
        evidence = []
        for item in self.store.db.execute(
            "SELECT * FROM repository_mission_evidence WHERE mission_id = ? ORDER BY id",
            (mission_id,),
        ).fetchall():
            evidence.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "digest": item["digest"],
                    "data": json.loads(item["data_json"]),
                    "created_at": item["created_at"],
                }
            )
        draft_row = self.store.db.execute(
            "SELECT * FROM draft_pull_requests WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        draft = None
        if draft_row is not None:
            draft = {
                "id": draft_row["id"],
                "status": draft_row["status"],
                "base_sha": draft_row["base_sha"],
                "head_sha": draft_row["head_sha"],
                "branch": draft_row["branch"],
                "changed_paths": json.loads(draft_row["changed_paths_json"]),
                "patch_digest": draft_row["patch_digest"],
                "test_command": json.loads(draft_row["test_command_json"]),
                "test_exit_status": draft_row["test_exit_status"],
                "test_output_digest": draft_row["test_output_digest"],
                "reviewer": draft_row["reviewer"],
                "countercase": draft_row["countercase"],
                "rollback_sha": draft_row["rollback_sha"],
                "created_at": draft_row["created_at"],
            }
        return {
            "id": row["id"],
            "identifier": row["identifier"],
            "state": row["status"],
            "contract": json.loads(row["contract_json"]),
            "current_head": row["current_head"],
            "transitions": transitions,
            "evidence": evidence,
            "draft_pr": draft,
            "rollback_command": f"git reset --hard {row['expected_base_sha']}",
            "rollback_args": ["reset", "--hard", row["expected_base_sha"]],
        }

    def _mission_row(self, mission_id: int) -> Any:
        row = self.store.db.execute(
            "SELECT * FROM repository_missions WHERE id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise RepositoryMissionError(f"repository mission {mission_id} not found")
        return row

    def _transition(
        self,
        mission_id: int,
        to_state: str,
        reason: str,
        repository_head: str,
        evidence_ids: tuple[int, ...] = (),
    ) -> None:
        with self.store.db:
            self._transition_in_transaction(
                mission_id, to_state, reason, repository_head, evidence_ids
            )

    def _transition_in_transaction(
        self,
        mission_id: int,
        to_state: str,
        reason: str,
        repository_head: str,
        evidence_ids: tuple[int, ...] = (),
    ) -> None:
        row = self._mission_row(mission_id)
        from_state = str(row["status"])
        expected = self._NEXT_STATES.get(from_state)
        if to_state not in {expected, "blocked", "quarantined", "failed", "rolled_back"}:
            raise RepositoryMissionError(f"illegal transition {from_state} -> {to_state}")
        self.store.db.execute(
            """
            UPDATE repository_missions
            SET status = ?, current_head = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = ?
            """,
            (to_state, repository_head, mission_id, from_state),
        )
        self.store.db.execute(
            """
            INSERT INTO repository_mission_transitions(
                mission_id, from_state, to_state, actor, authority,
                repository_head, reason, evidence_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mission_id,
                from_state,
                to_state,
                row["actor"],
                row["authority"],
                repository_head,
                reason[:2000],
                json.dumps(evidence_ids),
            ),
        )

    def _transition_terminal(
        self, mission_id: int, state: str, reason: str, repository_head: str
    ) -> None:
        current = str(self._mission_row(mission_id)["status"])
        if current not in self._TERMINAL_STATES:
            self._transition(mission_id, state, reason, repository_head)

    def _store_evidence(
        self, mission_id: int, kind: str, data: Mapping[str, object]
    ) -> int:
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 32_768:
            raise RepositoryMissionError("repository mission evidence exceeds bound")
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        with self.store.db:
            cursor = self.store.db.execute(
                "INSERT INTO repository_mission_evidence(mission_id, kind, digest, data_json) VALUES (?, ?, ?, ?)",
                (mission_id, kind, digest, serialized),
            )
        return int(cursor.lastrowid)

    def _store_patch_evidence(self, mission_id: int, patch: PatchEvidence) -> int:
        commands = []
        for command in patch.commands:
            raw = asdict(command)
            raw["args"] = [
                "<temporary-patch>" if str(argument).endswith(".patch") else argument
                for argument in command.args
            ]
            raw["stdout_excerpt"] = command.stdout_excerpt[:1024]
            raw["stderr_excerpt"] = command.stderr_excerpt[:1024]
            commands.append(raw)
        return self._store_evidence(
            mission_id,
            "patch",
            {
                "patch_digest": patch.patch_digest,
                "changed_paths": list(patch.changed_paths),
                "expected_head": patch.expected_head,
                "commands": commands,
            },
        )

    def _evidence_data(self, mission_id: int, kind: str) -> dict[str, object]:
        row = self.store.db.execute(
            "SELECT data_json FROM repository_mission_evidence WHERE mission_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (mission_id, kind),
        ).fetchone()
        if row is None:
            raise RepositoryMissionError(f"missing {kind} evidence")
        return json.loads(row["data_json"])

    def _git_output(self, repo: Path, args: tuple[str, ...], operation: str) -> str:
        completed = self.runner.run(repo, args)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[:500]
            raise RepositoryMissionError(f"unable to {operation}: {detail}")
        return completed.stdout

    def _inspect_base(self, mission_id: int, contract: RepositoryMissionContract) -> int:
        top = self._git_output(
            contract.repository_root, ("rev-parse", "--show-toplevel"), "resolve repository root"
        ).strip()
        if Path(top).resolve(strict=True) != contract.repository_root:
            raise RepositoryMissionError("resolved Git root does not match repository_root")
        head = self._git_output(
            contract.repository_root, ("rev-parse", "HEAD"), "inspect repository HEAD"
        ).strip().lower()
        if head != contract.expected_base_sha:
            raise RepositoryMissionError("repository HEAD is stale")
        status = self._git_output(
            contract.repository_root,
            ("status", "--porcelain", "--untracked-files=normal"),
            "inspect repository cleanliness",
        )
        if status:
            raise RepositoryMissionError("repository must have a clean worktree")
        return self._store_evidence(
            mission_id,
            "inspection",
            {"repository_root": str(contract.repository_root), "head": head, "clean": True},
        )

    def _ensure_mission_branch(self, contract: RepositoryMissionContract) -> None:
        current = self._git_output(
            contract.repository_root,
            ("branch", "--show-current"),
            "inspect current branch",
        ).strip()
        if current == contract.branch:
            return
        exists = self.runner.run(
            contract.repository_root,
            ("show-ref", "--verify", "--quiet", f"refs/heads/{contract.branch}"),
        )
        if exists.returncode == 0:
            raise RepositoryMissionError("declared mission branch already exists")
        created = self.runner.run(
            contract.repository_root, ("switch", "-c", contract.branch)
        )
        if created.returncode != 0:
            raise RepositoryMissionError(f"unable to create mission branch: {created.stderr[:500]}")

    def _validate_branched_state(self, contract: RepositoryMissionContract) -> None:
        current = self._git_output(
            contract.repository_root, ("branch", "--show-current"), "inspect mission branch"
        ).strip()
        head = self._git_output(
            contract.repository_root, ("rev-parse", "HEAD"), "inspect mission branch HEAD"
        ).strip()
        status = self._git_output(
            contract.repository_root,
            ("status", "--porcelain", "--untracked-files=normal"),
            "inspect mission worktree",
        )
        if current != contract.branch or head != contract.expected_base_sha or status:
            raise RepositoryMissionError("mission branch no longer matches durable branched state")

    def _obtain_patch(self, contract: RepositoryMissionContract, provider: Any | None) -> str:
        if contract.patch_source == "declared":
            assert contract.declared_patch is not None
            return contract.declared_patch
        if provider is None:
            raise RepositoryMissionError("worker patch provider is required")
        last_error: Exception | None = None
        for _ in range(contract.retry_limit + 1):
            try:
                response = provider(contract.worker_request)
            except Exception as exc:
                last_error = exc
                continue
            if not isinstance(response, str):
                raise RepositoryMissionError("worker response must be unified diff text")
            return response
        raise RepositoryMissionError(f"worker patch provider failed: {last_error}")

    def _validate_changed_paths(
        self, contract: RepositoryMissionContract, expected_paths: object
    ) -> None:
        if not isinstance(expected_paths, list) or not expected_paths:
            raise RepositoryMissionError("patch evidence has no changed paths")
        actual = set(
            self._git_output(
                contract.repository_root,
                ("diff", "--name-only", "--no-renames", "HEAD"),
                "inspect changed paths",
            ).splitlines()
        )
        actual.update(
            self._git_output(
                contract.repository_root,
                ("ls-files", "--others", "--exclude-standard"),
                "inspect new paths",
            ).splitlines()
        )
        if actual != set(expected_paths) or not actual.issubset(set(contract.allowed_paths)):
            raise RepositoryMissionError("worktree changes do not match durable patch evidence")

    def _run_test_command(
        self, contract: RepositoryMissionContract
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        try:
            completed = subprocess.run(
                list(contract.test_command),
                cwd=contract.repository_root,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=contract.test_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            completed = subprocess.CompletedProcess(
                list(contract.test_command), -1, stdout=stdout, stderr=stderr + "\ntest command timed out"
            )
        output = (completed.stdout or "") + (completed.stderr or "")
        return completed, output

    def _rollback_owned_changes(
        self, mission_id: int, contract: RepositoryMissionContract, test_id: int
    ) -> int:
        reset = self.runner.run(
            contract.repository_root, ("reset", "--hard", contract.expected_base_sha)
        )
        clean = self.runner.run(contract.repository_root, ("clean", "-fd"))
        if reset.returncode != 0 or clean.returncode != 0:
            raise RepositoryMissionError("test failure rollback did not complete")
        return self._store_evidence(
            mission_id,
            "rollback",
            {
                "rollback_sha": contract.expected_base_sha,
                "test_evidence_id": test_id,
                "reset_returncode": reset.returncode,
                "clean_returncode": clean.returncode,
                "resulting_head": self._git_output(
                    contract.repository_root, ("rev-parse", "HEAD"), "verify rollback HEAD"
                ).strip(),
            },
        )

    def _commit_and_push(self, mission_id: int, contract: RepositoryMissionContract) -> str:
        status = self._git_output(
            contract.repository_root,
            ("status", "--porcelain", "--untracked-files=normal"),
            "inspect pre-commit worktree",
        )
        message = f"Repository mission {contract.identifier}"
        if status:
            patch_data = self._evidence_data(mission_id, "patch")
            changed_paths = tuple(str(path) for path in patch_data["changed_paths"])
            added = self.runner.run(contract.repository_root, ("add", "--", *changed_paths))
            if added.returncode != 0:
                raise RepositoryMissionError(f"unable to stage mission paths: {added.stderr[:500]}")
            committed = self.runner.run(contract.repository_root, ("commit", "-m", message))
            if committed.returncode != 0:
                raise RepositoryMissionError(f"unable to commit mission changes: {committed.stderr[:500]}")
        head = self._git_output(
            contract.repository_root, ("rev-parse", "HEAD"), "inspect mission commit"
        ).strip()
        if head == contract.expected_base_sha:
            raise RepositoryMissionError("mission commit was not created")
        parent = self._git_output(
            contract.repository_root, ("rev-parse", "HEAD^"), "inspect mission commit parent"
        ).strip()
        subject = self._git_output(
            contract.repository_root, ("log", "-1", "--pretty=%s"), "inspect mission commit message"
        ).strip()
        if parent != contract.expected_base_sha or subject != message:
            raise RepositoryMissionError("local commit does not match the durable mission")

        origin_text = self._git_output(
            contract.repository_root, ("remote", "get-url", "origin"), "resolve local origin"
        ).strip()
        if "://" in origin_text or re.match(r"^[^/\\]+@[^:]+:", origin_text):
            raise RepositoryMissionError("origin must be a local bare repository")
        origin = Path(origin_text)
        if not origin.is_absolute():
            origin = contract.repository_root / origin
        try:
            origin = origin.resolve(strict=True)
        except OSError as exc:
            raise RepositoryMissionError("origin local bare repository is unavailable") from exc
        if not origin.is_relative_to(contract.workspace_root):
            raise RepositoryMissionError("origin resolves outside workspace_root")
        bare = self.runner.run(
            contract.repository_root,
            ("--git-dir", str(origin), "rev-parse", "--is-bare-repository"),
        )
        if bare.returncode != 0 or bare.stdout.strip() != "true":
            raise RepositoryMissionError("origin must be a local bare repository")
        pushed = self.runner.run(
            contract.repository_root,
            ("push", "origin", f"refs/heads/{contract.branch}:refs/heads/{contract.branch}"),
        )
        push_id = self._store_evidence(
            mission_id,
            "push",
            {
                "branch": contract.branch,
                "head": head,
                "returncode": pushed.returncode,
                "stdout_digest": hashlib.sha256((pushed.stdout or "").encode("utf-8")).hexdigest(),
                "stderr_digest": hashlib.sha256((pushed.stderr or "").encode("utf-8")).hexdigest(),
            },
        )
        if pushed.returncode != 0:
            raise RepositoryMissionError(
                f"unable to push mission branch to local origin; evidence {push_id}"
            )
        return head

    def _record_draft(self, mission_id: int, contract: RepositoryMissionContract) -> None:
        patch = self._evidence_data(mission_id, "patch")
        test = self._evidence_data(mission_id, "test")
        head = self._git_output(
            contract.repository_root, ("rev-parse", "HEAD"), "inspect draft head"
        ).strip()
        draft_data = {
            "base_sha": contract.expected_base_sha,
            "head_sha": head,
            "branch": contract.branch,
            "changed_paths": patch["changed_paths"],
            "patch_digest": patch["patch_digest"],
            "test_output_digest": test["output_digest"],
            "reviewer": contract.reviewer,
            "countercase": contract.countercase,
            "rollback_sha": contract.expected_base_sha,
        }
        draft_evidence_id = self._store_evidence(mission_id, "draft_pr", draft_data)
        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO draft_pull_requests(
                    mission_id, status, base_sha, head_sha, branch,
                    changed_paths_json, patch_digest, test_command_json,
                    test_exit_status, test_output_digest, reviewer, countercase,
                    rollback_sha
                ) VALUES (?, 'awaiting_human', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    contract.expected_base_sha,
                    head,
                    contract.branch,
                    json.dumps(patch["changed_paths"]),
                    patch["patch_digest"],
                    json.dumps(contract.test_command),
                    test["exit_status"],
                    test["output_digest"],
                    contract.reviewer,
                    contract.countercase,
                    contract.expected_base_sha,
                ),
            )
            self._transition_in_transaction(
                mission_id,
                "draft_pr_recorded",
                "durable local draft comparison recorded",
                head,
                (draft_evidence_id,),
            )
