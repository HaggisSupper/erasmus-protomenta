import json
import sys

import pytest

from erasmus import foundry_cli
from erasmus.knowledge_foundry import CandidateConcept, SourceSpan, write_candidate_bundle


def _valid_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    source = SourceSpan("paper.pdf", "urn:sha256:" + "d" * 64, 1, 1)
    write_candidate_bundle(
        bundle,
        [CandidateConcept("Candidate", "Concept", "Draft candidate", "Body", (), (), (source,))],
        [{"path": "paper.pdf", "sha256": "d" * 64, "pages": 1, "textless_pages": []}],
        "local-model",
        "mistral_rs",
    )
    return bundle


def test_validate_command_writes_machine_readable_report(tmp_path, monkeypatch, capsys):
    bundle = _valid_bundle(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["erasmus-foundry", "validate", str(bundle), "--write-report"],
    )

    foundry_cli.main()

    output = json.loads(capsys.readouterr().out)
    report = json.loads((bundle / "_foundry" / "validation-report.json").read_text(encoding="utf-8"))
    assert output["valid"] is True
    assert report == output


def test_validate_command_exits_nonzero_for_invalid_bundle(tmp_path, monkeypatch):
    bundle = tmp_path / "invalid"
    bundle.mkdir()
    monkeypatch.setattr(sys, "argv", ["erasmus-foundry", "validate", str(bundle)])

    with pytest.raises(SystemExit) as exc:
        foundry_cli.main()

    assert exc.value.code == 1
