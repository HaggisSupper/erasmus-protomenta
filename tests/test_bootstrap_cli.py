"""CLI tests for bootstrap contract utilities."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from erasmus.cli.main import main


def _fixture_paths(root: Path) -> tuple[Path, Path]:
    fixtures = root / "contracts" / "bootstrap" / "fixtures"
    return (
        fixtures / "valid-minimal-windows.json",
        fixtures / "invalid-duplicate-component-id.json",
    )


def test_bootstrap_validate_command_outputs_json(monkeypatch, tmp_path, capsys):
    repo_root = Path.cwd()
    fixture, _ = _fixture_paths(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(tmp_path / "erasmus.db"),
            "bootstrap-validate",
            str(fixture),
            "--json",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["errors"] == []
    assert output["derived_startup_order"] == [
        "sqlite-store",
        "erasmus-mcp",
        "mistral-rs",
        "llama-cpp",
        "headless-router",
    ]
    assert output["derived_shutdown_order"] == [
        "headless-router",
        "llama-cpp",
        "mistral-rs",
        "erasmus-mcp",
        "sqlite-store",
    ]


def test_bootstrap_resolve_command_writes_orders(monkeypatch, tmp_path, capsys):
    repo_root = Path.cwd()
    fixture, _ = _fixture_paths(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(tmp_path / "erasmus.db"),
            "bootstrap-resolve",
            str(fixture),
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["startup_order"] == [
        "sqlite-store",
        "erasmus-mcp",
        "mistral-rs",
        "llama-cpp",
        "headless-router",
    ]
    assert output["shutdown_order"] == [
        "headless-router",
        "llama-cpp",
        "mistral-rs",
        "erasmus-mcp",
        "sqlite-store",
    ]


def test_bootstrap_resolve_command_human_output(monkeypatch, tmp_path, capsys):
    repo_root = Path.cwd()
    fixture, _ = _fixture_paths(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(tmp_path / "erasmus.db"),
            "bootstrap-resolve",
            str(fixture),
            "--human",
        ],
    )
    main()

    output = capsys.readouterr().out
    assert "Bootstrap component order:" in output
    assert "startup:" in output
    assert "shutdown:" in output


def test_bootstrap_resolve_command_fails_on_invalid_fixture(monkeypatch, tmp_path):
    repo_root = Path.cwd()
    _, invalid = _fixture_paths(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "erasmus",
            "--db",
            str(tmp_path / "erasmus.db"),
            "bootstrap-resolve",
            str(invalid),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
