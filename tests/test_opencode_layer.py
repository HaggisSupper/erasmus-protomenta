from __future__ import annotations

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
    return destination


def test_repository_opencode_layer_is_valid() -> None:
    assert validate_opencode_layer(ROOT) == ()


def test_frontmatter_parser_supports_one_nested_mapping() -> None:
    data, body = parse_frontmatter(
        "---\nname: example\npermission:\n  skill: allow\n  edit: ask\n---\n\nBody\n"
    )
    assert data == {
        "name": "example",
        "permission": {"skill": "allow", "edit": "ask"},
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


def test_agent_model_pin_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    agent = root / ".opencode" / "agents" / "erasmus.md"
    text = agent.read_text(encoding="utf-8").replace("mode: primary", "mode: primary\nmodel: provider/model")
    agent.write_text(text, encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("unsupported agent frontmatter fields: model" in error for error in errors)


def test_project_model_pin_fails(tmp_path: Path) -> None:
    root = _copy_layer(tmp_path)
    config_path = root / "opencode.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["model"] = "provider/model"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_opencode_layer(root)
    assert any("must not pin provider/model" in error for error in errors)


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _run_installer(
    executable: str,
    target: Path,
    action: str,
    *,
    what_if: bool = False,
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
        str(ROOT),
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
