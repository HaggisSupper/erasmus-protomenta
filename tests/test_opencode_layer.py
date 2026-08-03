from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from erasmus.opencode_layer import FrontmatterError, parse_frontmatter, validate_opencode_layer


ROOT = Path(__file__).resolve().parents[1]


def _copy_layer(destination: Path) -> Path:
    shutil.copytree(ROOT / ".opencode", destination / ".opencode")
    shutil.copy2(ROOT / "opencode.json", destination / "opencode.json")
    shutil.copy2(ROOT / "CONTEXT.md", destination / "CONTEXT.md")
    (destination / "constitution").mkdir()
    shutil.copy2(
        ROOT / "constitution" / "immutable-contract.md",
        destination / "constitution" / "immutable-contract.md",
    )
    (destination / "docs").mkdir()
    shutil.copy2(ROOT / "docs" / "architecture.md", destination / "docs" / "architecture.md")
    return destination


def test_repository_opencode_layer_is_valid() -> None:
    assert validate_opencode_layer(ROOT) == ()


def test_frontmatter_parser_supports_one_nested_mapping_and_quoted_wildcard() -> None:
    data, body = parse_frontmatter(
        '---\nname: example\npermission:\n  "*": ask\n  skill: allow\n---\n\nBody\n'
    )
    assert data == {
        "name": "example",
        "permission": {"*": "ask", "skill": "allow"},
    }
    assert body == "Body"


def test_frontmatter_parser_rejects_missing_delimiter() -> None:
    with pytest.raises(FrontmatterError, match="must start"):
        parse_frontmatter("name: example")


def test_missing_frontmatter_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    skill.write_text("# no frontmatter\n", encoding="utf-8")
    assert any("frontmatter must start" in error for error in validate_opencode_layer(root))


def test_skill_directory_name_mismatch_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    text = skill.read_text(encoding="utf-8").replace("name: erasmus-tdd", "name: erasmus-tdx")
    skill.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("must match directory" in error for error in errors)


def test_duplicate_skill_name_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    source = root / ".opencode" / "skills" / "erasmus-tdd"
    duplicate = root / ".opencode" / "skills" / "erasmus-tdd-copy"
    shutil.copytree(source, duplicate)
    errors = validate_opencode_layer(root)
    assert any("duplicate skill name 'erasmus-tdd'" in error for error in errors)


def test_additional_valid_skill_is_allowed(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-extra" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        """---
name: erasmus-extra
description: Prevent one explicitly documented repeated failure
---

# Extra bounded skill

## Trigger

Use only for the documented repeated failure.

## Authority boundary

The Erasmus runtime remains authoritative.

## Deterministic evidence

Inspect the exact failing artifact.

## Workflow

1. Reproduce the failure.
2. Apply the bounded correction.

## Output artifact

A reviewable correction record.

## Stop condition

Stop when the failure is deterministically resolved.
""",
        encoding="utf-8",
    )
    assert validate_opencode_layer(root) == ()


def test_non_erasmus_skill_namespace_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    source = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    skill = root / ".opencode" / "skills" / "other-skill" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        source.read_text(encoding="utf-8").replace("name: erasmus-tdd", "name: other-skill"),
        encoding="utf-8",
    )
    errors = validate_opencode_layer(root)
    assert any("must use the erasmus- namespace" in error for error in errors)


def test_skill_name_over_64_characters_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    long_name = "a" * 65
    skill = root / ".opencode" / "skills" / long_name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    source = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    skill.write_text(
        source.read_text(encoding="utf-8").replace("name: erasmus-tdd", f"name: {long_name}"),
        encoding="utf-8",
    )
    errors = validate_opencode_layer(root)
    assert any("invalid or missing skill name" in error for error in errors)


def test_unsupported_skill_frontmatter_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    text = skill.read_text(encoding="utf-8").replace(
        "description:", "disable-model-invocation: true\ndescription:", 1
    )
    skill.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("unsupported skill frontmatter fields" in error for error in errors)


def test_missing_required_skill_section_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    text = skill.read_text(encoding="utf-8").replace("## Stop condition", "## Finished")
    skill.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("missing required section '## Stop condition'" in error for error in errors)


def test_missing_authoritative_boundary_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    skill = root / ".opencode" / "skills" / "erasmus-tdd" / "SKILL.md"
    text = skill.read_text(encoding="utf-8").replace(
        "The Erasmus runtime remains authoritative.", "The prompt is authoritative."
    )
    skill.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("missing authoritative runtime boundary" in error for error in errors)


def test_command_reference_to_missing_skill_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    command = root / ".opencode" / "commands" / "erasmus.md"
    text = command.read_text(encoding="utf-8").replace("erasmus-router", "erasmus-missing")
    command.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("referenced skill 'erasmus-missing' does not exist" in error for error in errors)


def test_non_erasmus_command_namespace_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    source = root / ".opencode" / "commands" / "erasmus.md"
    shutil.copy2(source, root / ".opencode" / "commands" / "help.md")
    errors = validate_opencode_layer(root)
    assert any("must use the erasmus namespace" in error for error in errors)


def test_agent_model_pin_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    agent = root / ".opencode" / "agents" / "erasmus.md"
    text = agent.read_text(encoding="utf-8").replace(
        "mode: primary", "mode: primary\nmodel: provider/model"
    )
    agent.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("unsupported agent frontmatter fields: model" in error for error in errors)


def test_documented_list_and_todowrite_permissions_are_allowed(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    agent = root / ".opencode" / "agents" / "erasmus.md"
    data, _ = parse_frontmatter(agent.read_text(encoding="utf-8"))
    permission = data["permission"]
    assert isinstance(permission, dict)
    assert permission["list"] == "allow"
    assert permission["todowrite"] == "allow"
    assert validate_opencode_layer(root) == ()


def test_agent_unknown_permission_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    agent = root / ".opencode" / "agents" / "erasmus.md"
    text = agent.read_text(encoding="utf-8").replace(
        "  doom_loop: ask", "  doom_loop: ask\n  made_up_tool: allow"
    )
    agent.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("unsupported permission fields: made_up_tool" in error for error in errors)


def test_agent_wildcard_permission_must_default_to_ask(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    agent = root / ".opencode" / "agents" / "erasmus.md"
    text = agent.read_text(encoding="utf-8").replace('  "*": ask\n', "")
    agent.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("unknown OpenCode actions must default to ask" in error for error in errors)


def test_project_model_pin_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    config_path = root / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["model"] = "provider/model"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("must not pin provider/model" in error for error in errors)


def test_project_skill_discovery_permission_is_required(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    config_path = root / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    del config["permission"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("native skill discovery must be explicitly allowed" in error for error in errors)


def test_required_instruction_path_must_exist(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    config_path = root / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["instructions"].append("docs/missing.md")
    config_path.write_text(json.dumps(config), encoding="utf-8")
    # Only required paths are guaranteed by the layer; arbitrary operator paths are allowed.
    assert validate_opencode_layer(root) == ()

    config["instructions"].remove("constitution/immutable-contract.md")
    config_path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("required instruction files are missing" in error for error in errors)


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _run_installer(
    executable: str,
    target: Path,
    action: str,
    *,
    what_if: bool = False,
    source_root: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    command = [
        executable,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "install" / "Install-ErasmusOpenCode.ps1"),
        "-Action",
        action,
        "-SourceRoot",
        str(source_root),
        "-TargetRoot",
        str(target),
    ]
    if what_if:
        command.append("-WhatIf")
    return subprocess.run(command, text=True, capture_output=True, check=False)


def test_powershell_installer_dry_run_install_repair_and_rollback(tmp_path: Path) -> None:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    target = tmp_path / "opencode"
    dry_run = _run_installer(executable, target, "Install", what_if=True)
    assert dry_run.returncode == 0, dry_run.stderr
    assert not target.exists()

    installed = _run_installer(executable, target, "Install")
    assert installed.returncode == 0, installed.stderr
    manifest = target / "erasmus-install-manifest.json"
    agent = target / "agents" / "erasmus.md"
    assert manifest.is_file()
    assert agent.is_file()
    original = agent.read_text(encoding="utf-8")

    repeated = _run_installer(executable, target, "Install")
    assert repeated.returncode == 0, repeated.stderr
    assert agent.read_text(encoding="utf-8") == original

    agent.write_text("operator-local-agent\n", encoding="utf-8")
    repaired = _run_installer(executable, target, "Repair")
    assert repaired.returncode == 0, repaired.stderr
    assert agent.read_text(encoding="utf-8") == original

    rolled_back = _run_installer(executable, target, "Rollback")
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert agent.read_text(encoding="utf-8") == "operator-local-agent\n"


def test_powershell_installer_refuses_to_rollback_post_install_edits(tmp_path: Path) -> None:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    target = tmp_path / "opencode"
    installed = _run_installer(executable, target, "Install")
    assert installed.returncode == 0, installed.stderr
    agent = target / "agents" / "erasmus.md"
    agent.write_text("post-install-operator-edit\n", encoding="utf-8")

    rolled_back = _run_installer(executable, target, "Rollback")
    assert rolled_back.returncode != 0
    assert agent.read_text(encoding="utf-8") == "post-install-operator-edit\n"
    assert (target / "erasmus-install-manifest.json").is_file()


def test_powershell_installer_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    target = tmp_path / "opencode"
    installed = _run_installer(executable, target, "Install")
    assert installed.returncode == 0, installed.stderr

    outside = tmp_path / "outside.md"
    outside.write_text("do-not-touch\n", encoding="utf-8")
    manifest_path = target / "erasmus-install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["relative_path"] = "../../outside.md"
    manifest["entries"][0]["installed_sha256"] = hashlib.sha256(
        outside.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rolled_back = _run_installer(executable, target, "Rollback")
    assert rolled_back.returncode != 0
    assert outside.read_text(encoding="utf-8") == "do-not-touch\n"
    assert manifest_path.is_file()


def test_powershell_installer_invalid_source_does_not_mutate_target(tmp_path: Path) -> None:
    executable = _powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    invalid_source = tmp_path / "invalid-source"
    invalid_source.mkdir()
    target = tmp_path / "opencode"
    result = _run_installer(
        executable,
        target,
        "Install",
        source_root=invalid_source,
    )
    assert result.returncode != 0
    assert not target.exists()
