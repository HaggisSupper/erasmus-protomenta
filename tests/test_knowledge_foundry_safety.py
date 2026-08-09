from pathlib import Path

import pytest

from erasmus import knowledge_foundry as foundry


class FakeRuntime:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.config = type("Config", (), {"model": "local-test-model", "runtime_kind": "mistral_rs"})()

    def complete_nonstream(self, messages):
        return next(self.responses)


def test_build_rejects_output_equal_to_or_ancestor_of_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "paper.pdf").write_bytes(b"%PDF-placeholder")
    monkeypatch.setattr(foundry, "extract_pdf_pages", lambda path: (["text"], []))
    runtime = FakeRuntime([])

    with pytest.raises(ValueError, match="must not contain the source directory"):
        foundry.build_candidate_bundle(source, source, runtime, overwrite=True)
    assert (source / "paper.pdf").exists()

    with pytest.raises(ValueError, match="must not contain the source directory"):
        foundry.build_candidate_bundle(source, tmp_path, runtime, overwrite=True)
    assert (source / "paper.pdf").exists()


def test_distinct_titles_with_same_slug_get_distinct_files(tmp_path):
    source = foundry.SourceSpan("paper.pdf", "urn:sha256:" + "e" * 64, 1, 1)
    concepts = [
        foundry.CandidateConcept("A+B", "Concept", "plus", "one", (), (), (source,)),
        foundry.CandidateConcept("A B", "Concept", "space", "two", (), (), (source,)),
    ]
    out = tmp_path / "bundle"

    foundry.write_candidate_bundle(out, concepts, [], "model", "mistral_rs")

    files = sorted(path.name for path in (out / "concepts").glob("*.md"))
    assert len(files) == 2
    assert len(set(files)) == 2
    assert foundry.validate_okf_bundle(out)["valid"] is True


def test_failed_overwrite_preserves_previous_valid_bundle(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "paper.pdf").write_bytes(b"%PDF-placeholder")
    monkeypatch.setattr(foundry, "extract_pdf_pages", lambda path: (["text"], []))
    out = tmp_path / "bundle"
    out.mkdir()
    marker = out / "keep.txt"
    marker.write_text("previous-valid-bundle", encoding="utf-8")
    runtime = FakeRuntime(["not-json"])

    with pytest.raises(foundry.FoundryProtocolError):
        foundry.build_candidate_bundle(source, out, runtime, overwrite=True)

    assert marker.read_text(encoding="utf-8") == "previous-valid-bundle"
