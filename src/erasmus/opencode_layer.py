"""Deterministic validation for the OpenCode Erasmus interaction layer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence


class FrontmatterError(ValueError):
    """Raised when bounded YAML frontmatter cannot be parsed safely."""


SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COMMAND_SKILL_RE = re.compile(
    r"Load the OpenCode skill named `([a-z0-9]+(?:-[a-z0-9]+)*)` and follow it\."
)

SKILL_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata"})
COMMAND_FIELDS = frozenset({"description", "agent", "subtask"})
AGENT_FIELDS = frozenset(
    {
        "description",
        "mode",
        "temperature",
        "top_p",
        "max_steps",
        "hidden",
        "color",
        "permission",
    }
)
AGENT_PERMISSION_FIELDS = frozenset(
    {
        "*",
        "read",
        "edit",
        "glob",
        "grep",
        "list",
        "bash",
        "task",
        "skill",
        "lsp",
        "question",
        "todowrite",
        "webfetch",
        "websearch",
        "external_directory",
        "doom_loop",
    }
)
PERMISSION_ACTIONS = frozenset({"allow", "ask", "deny"})
REQUIRED_SKILL_SECTIONS = (
    "## Trigger",
    "## Authority boundary",
    "## Deterministic evidence",
    "## Workflow",
    "## Output artifact",
    "## Stop condition",
)
AUTHORITY_SENTENCE = "The Erasmus runtime remains authoritative."
REQUIRED_SKILLS = frozenset(
    {
        "erasmus-router",
        "erasmus-setup",
        "erasmus-domain-model",
        "erasmus-spec",
        "erasmus-implement",
        "erasmus-tdd",
        "erasmus-diagnose",
        "erasmus-research",
        "erasmus-code-review",
        "erasmus-handoff",
        "erasmus-doctor",
    }
)
REQUIRED_COMMANDS = frozenset(
    {
        "erasmus",
        "erasmus-setup",
        "erasmus-spec",
        "erasmus-implement",
        "erasmus-review",
        "erasmus-research",
        "erasmus-handoff",
        "erasmus-doctor",
    }
)
REQUIRED_INSTRUCTIONS = frozenset(
    {"CONTEXT.md", "constitution/immutable-contract.md", "docs/architecture.md"}
)


def _parse_scalar(value: str) -> object:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if re.fullmatch(r"-?(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)", value):
        return float(value)
    return value


def _parse_key(value: str) -> str:
    parsed = _parse_scalar(value)
    if not isinstance(parsed, str) or not parsed:
        raise FrontmatterError("frontmatter keys must be non-empty strings")
    return parsed


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse the small YAML subset used by OpenCode files.

    The parser intentionally supports only top-level scalar fields and one nested
    scalar mapping. Unsupported YAML constructs fail closed rather than being
    interpreted differently from OpenCode.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("frontmatter must start with '---'")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        raise FrontmatterError("frontmatter closing '---' is missing") from error

    data: dict[str, object] = {}
    current_mapping: str | None = None
    for number, raw_line in enumerate(lines[1:end], start=2):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if "\t" in raw_line[:indent]:
            raise FrontmatterError(f"line {number}: tabs are not permitted")
        stripped = raw_line.strip()
        if ":" not in stripped:
            raise FrontmatterError(f"line {number}: expected key: value")
        raw_key, value = (part.strip() for part in stripped.split(":", 1))
        try:
            key = _parse_key(raw_key)
        except FrontmatterError as error:
            raise FrontmatterError(f"line {number}: {error}") from error

        if indent == 0:
            if key in data:
                raise FrontmatterError(f"line {number}: duplicate key '{key}'")
            if value:
                data[key] = _parse_scalar(value)
                current_mapping = None
            else:
                data[key] = {}
                current_mapping = key
            continue

        if indent != 2 or current_mapping is None:
            raise FrontmatterError(
                f"line {number}: only one two-space nested mapping is supported"
            )
        if not value:
            raise FrontmatterError(f"line {number}: nested mappings are not supported")
        mapping = data[current_mapping]
        if not isinstance(mapping, dict):
            raise FrontmatterError(f"line {number}: invalid nested mapping")
        if key in mapping:
            raise FrontmatterError(f"line {number}: duplicate nested key '{key}'")
        mapping[key] = _parse_scalar(value)

    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return data, body


def _unknown_fields(data: Mapping[str, object], allowed: frozenset[str]) -> list[str]:
    return sorted(set(data) - allowed)


def _is_erasmus_namespace(name: str) -> bool:
    return name == "erasmus" or name.startswith("erasmus-")


def _validate_skill(path: Path) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    try:
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, FrontmatterError) as error:
        return None, [f"{path}: {error}"]

    unknown = _unknown_fields(data, SKILL_FIELDS)
    if unknown:
        errors.append(f"{path}: unsupported skill frontmatter fields: {', '.join(unknown)}")

    name = data.get("name")
    if (
        not isinstance(name, str)
        or len(name) > 64
        or not SKILL_NAME_RE.fullmatch(name)
    ):
        errors.append(f"{path}: invalid or missing skill name")
        normalized_name: str | None = None
    else:
        normalized_name = name
        if not _is_erasmus_namespace(name):
            errors.append(f"{path}: globally installable skill must use the erasmus- namespace")
        if path.parent.name != name:
            errors.append(
                f"{path}: skill name '{name}' must match directory '{path.parent.name}'"
            )

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{path}: description must be a non-empty string")
    elif len(description) > 1024:
        errors.append(f"{path}: description exceeds 1024 characters")

    for optional_string in ("license", "compatibility"):
        if optional_string in data and (
            not isinstance(data[optional_string], str)
            or not str(data[optional_string]).strip()
        ):
            errors.append(f"{path}: {optional_string} must be a non-empty string")

    metadata = data.get("metadata")
    if metadata is not None and (
        not isinstance(metadata, dict)
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items())
    ):
        errors.append(f"{path}: metadata must be a string-to-string mapping")

    for section in REQUIRED_SKILL_SECTIONS:
        if section not in body:
            errors.append(f"{path}: missing required section '{section}'")
    if AUTHORITY_SENTENCE not in body:
        errors.append(f"{path}: missing authoritative runtime boundary sentence")

    return normalized_name, errors


def _validate_command(path: Path, skill_names: frozenset[str]) -> list[str]:
    errors: list[str] = []
    try:
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, FrontmatterError) as error:
        return [f"{path}: {error}"]

    if len(path.stem) > 64 or not SKILL_NAME_RE.fullmatch(path.stem):
        errors.append(f"{path}: command filename must be lowercase kebab-case")
    elif not _is_erasmus_namespace(path.stem):
        errors.append(f"{path}: globally installable command must use the erasmus namespace")

    unknown = _unknown_fields(data, COMMAND_FIELDS)
    if unknown:
        errors.append(f"{path}: unsupported command frontmatter fields: {', '.join(unknown)}")
    if not isinstance(data.get("description"), str) or not str(data["description"]).strip():
        errors.append(f"{path}: command description must be non-empty")
    if data.get("agent") != "erasmus":
        errors.append(f"{path}: command must use agent 'erasmus'")
    if "subtask" in data and not isinstance(data["subtask"], bool):
        errors.append(f"{path}: subtask must be boolean")

    references = COMMAND_SKILL_RE.findall(body)
    if len(references) != 1:
        errors.append(f"{path}: command must reference exactly one OpenCode skill")
    for reference in references:
        if reference not in skill_names:
            errors.append(f"{path}: referenced skill '{reference}' does not exist")
    return errors


def _contains_key(value: object, forbidden: frozenset[str]) -> bool:
    if isinstance(value, dict):
        return any(key in forbidden or _contains_key(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


def _validate_agent(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, FrontmatterError) as error:
        return [f"{path}: {error}"]

    unknown = _unknown_fields(data, AGENT_FIELDS)
    if unknown:
        errors.append(f"{path}: unsupported agent frontmatter fields: {', '.join(unknown)}")
    if data.get("mode") != "primary":
        errors.append(f"{path}: Erasmus agent mode must be 'primary'")

    permission = data.get("permission")
    if not isinstance(permission, dict):
        errors.append(f"{path}: Erasmus agent permission must be a mapping")
    else:
        unknown_permissions = _unknown_fields(permission, AGENT_PERMISSION_FIELDS)
        if unknown_permissions:
            errors.append(
                f"{path}: unsupported permission fields: {', '.join(unknown_permissions)}"
            )
        for key, action in sorted(permission.items()):
            if not isinstance(action, str) or action not in PERMISSION_ACTIONS:
                errors.append(
                    f"{path}: permission '{key}' must be allow, ask, or deny"
                )
        if permission.get("*") != "ask":
            errors.append(f"{path}: unknown OpenCode actions must default to ask")
        if permission.get("skill") != "allow":
            errors.append(f"{path}: Erasmus agent must allow the native skill tool")

    if AUTHORITY_SENTENCE not in body:
        errors.append(f"{path}: agent must preserve the authoritative runtime boundary")
    return errors


def validate_opencode_layer(root: Path) -> tuple[str, ...]:
    """Return sorted deterministic validation errors for an OpenCode layer."""

    root = root.resolve()
    errors: list[str] = []
    skills_root = root / ".opencode" / "skills"
    commands_root = root / ".opencode" / "commands"
    agent_path = root / ".opencode" / "agents" / "erasmus.md"

    skill_files = sorted(skills_root.glob("*/SKILL.md")) if skills_root.is_dir() else []
    if not skill_files:
        errors.append(f"{skills_root}: no skills found")

    seen: dict[str, Path] = {}
    for skill_file in skill_files:
        name, skill_errors = _validate_skill(skill_file)
        errors.extend(skill_errors)
        if name is not None:
            if name in seen:
                errors.append(f"{skill_file}: duplicate skill name '{name}' also used by {seen[name]}")
            else:
                seen[name] = skill_file

    skill_names = frozenset(seen)
    missing_skills = sorted(REQUIRED_SKILLS - skill_names)
    if missing_skills:
        errors.append(f"{skills_root}: missing required skills: {', '.join(missing_skills)}")

    command_files = sorted(commands_root.glob("*.md")) if commands_root.is_dir() else []
    command_names = frozenset(path.stem for path in command_files)
    missing_commands = sorted(REQUIRED_COMMANDS - command_names)
    if missing_commands:
        errors.append(f"{commands_root}: missing required commands: {', '.join(missing_commands)}")
    for command_file in command_files:
        errors.extend(_validate_command(command_file, skill_names))

    if not agent_path.is_file():
        errors.append(f"{agent_path}: missing Erasmus agent")
    else:
        errors.extend(_validate_agent(agent_path))

    config_path = root / "opencode.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(f"{config_path}: {error}")
    else:
        if not isinstance(config, dict):
            errors.append(f"{config_path}: project configuration must be a JSON object")
        else:
            if _contains_key(config, frozenset({"model", "provider"})):
                errors.append(f"{config_path}: project configuration must not pin provider/model")
            instructions = config.get("instructions")
            if not isinstance(instructions, list) or not REQUIRED_INSTRUCTIONS.issubset(set(instructions)):
                errors.append(f"{config_path}: required instruction files are missing")
            else:
                for instruction in sorted(REQUIRED_INSTRUCTIONS):
                    if not (root / instruction).is_file():
                        errors.append(f"{config_path}: instruction path does not exist: {instruction}")

            permission = config.get("permission")
            skill_permission = permission.get("skill") if isinstance(permission, dict) else None
            if not isinstance(skill_permission, dict) or skill_permission.get("*") != "allow":
                errors.append(f"{config_path}: native skill discovery must be explicitly allowed")

    context_path = root / "CONTEXT.md"
    try:
        context = context_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"{context_path}: {error}")
    else:
        for term in ("**Authoritative state:**", "**Interaction layer:**"):
            if term not in context:
                errors.append(f"{context_path}: missing shared-language term {term}")

    return tuple(sorted(errors))


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a repository root and return a process exit code."""

    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    errors = validate_opencode_layer(args.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("OpenCode layer: READY")
    return 0
