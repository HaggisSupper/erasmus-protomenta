from pathlib import Path

import pytest

from erasmus import knowledge_foundry as foundry


class FakeRuntime:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.config = type("Config", (), {"model": "local-test-model", "runtime_kind": "mistral_rs"})()

    def complete_nonstream(self, messages):
        return next(self.responses)


def test_build_rejects_output_equal_to_ancestor_or_descendant_of_source(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "paper.pdf").write_bytes(b"%PDF-placeholder")
    monkeypatch.setattr(foundry, "extract_pdf_pages", lambda path: (["text"], []))
    runtime = FakeRuntime([])

    with pytest.raises(ValueError, match="must be disjoint from the source directory"):
        foundry.build_candidate_bundle(source, source, runtime, overwrite=True)
    assert (source / "paper.pdf").exists()

    with pytest.raises(ValueError, match="must be disjoint from the source directory"):
        foundry.build_candidate_bundle(source, tmp_path, runtime, overwrite=True)
    assert (source / "paper.pdf").exists()

    nested_output = source / "generated"
    with pytest.raises(ValueError, match="must be disjoint from the source directory"):
        foundry.build_candidate_bundle(source, nested_output, runtime, overwrite=True)
    assert (source / "paper.pdf").exists()


def test_chunk_page_span_does_not_attribute_separator_to_later_page():
    chunks = foundry.chunk_pages(
        Path("paper.pdf"),
        ["abc", "def"],
        chunk_chars=4,
        overlap_chars=0,
    )

    assert chunks[0].text == "abc\n"
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 1
    assert chunks[1].start_page == 2
    assert chunks[1].end_page == 2


def test_distinct_titles_with_same_slug_get_distinct_files(tmp_path):
    source = foundry.SourceSpan("paper.pdf", "urn:sha256:" + "e" * 64, 1, 1)
    concepts = [
        foundry.CandidateConcept("A+B", "Concept", "plus", "one", (), (), (source,)),
        foundry.CandidateConcept("A B", "Concept", "space", "two", (), (), (source,)),
    ]
    out = tmp_path / "bundle"
    manifest = [
        {
            "path": "paper.pdf",
            "sha256": "e" * 64,
            "resource": "urn:sha256:" + "e" * 64,
            "pages": 1,
            "textless_pages": [],
        }
    ]

    foundry.write_candidate_bundle(out, concepts, manifest, "model", "mistral_rs")

    files = sorted(path.name for path in (out / "concepts").glob("*.md"))
    assert len(files) == 2
    assert len(set(files)) == 2
    assert foundry.validate_okf_bundle(out)["valid"] is True


def test_validation_requires_manifest_and_cross_checks_span(tmp_path):
    source = foundry.SourceSpan("paper.pdf", "urn:sha256:" + "e" * 64, 1, 2)
    concept = foundry.CandidateConcept(
        "Concept", "Concept", "desc", "body", (), (), (source,)
    )
    out = tmp_path / "bundle"
    manifest = [
        {
            "path": "paper.pdf",
            "sha256": "e" * 64,
            "resource": "urn:sha256:" + "e" * 64,
            "pages": 1,
            "textless_pages": [],
        }
    ]

    foundry.write_candidate_bundle(out, [concept], manifest, "model", "mistral_rs")
    report = foundry.validate_okf_bundle(out)
    assert report["valid"] is False
    assert any("source span exceeds manifest page count" in error for error in report["errors"])

    (out / "_foundry" / "source-manifest.json").unlink()
    report = foundry.validate_okf_bundle(out)
    assert report["valid"] is False
    assert any("missing source manifest" in error for error in report["errors"])


def test_generated_provenance_records_versioned_prompt(tmp_path):
    source = foundry.SourceSpan("paper.pdf", "urn:sha256:" + "e" * 64, 1, 1)
    concept = foundry.CandidateConcept(
        "Concept", "Concept", "desc", "body", (), (), (source,)
    )
    out = tmp_path / "bundle"
    manifest = [
        {
            "path": "paper.pdf",
            "sha256": "e" * 64,
            "resource": "urn:sha256:" + "e" * 64,
            "pages": 1,
            "textless_pages": [],
        }
    ]

    foundry.write_candidate_bundle(out, [concept], manifest, "model", "mistral_rs")
    concept_path = next((out / "concepts").glob("*.md"))
    meta = foundry._frontmatter(concept_path.read_text(encoding="utf-8"), concept_path)

    assert meta["generated"]["prompt_version"] == foundry.FOUNDRY_PROMPT_VERSION
    assert foundry.FOUNDRY_PROMPT_PATH.is_file()


def test_build_detects_source_change_between_hash_and_extraction(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    pdf = source / "paper.pdf"
    pdf.write_bytes(b"%PDF-original")
    out = tmp_path / "bundle"

    def extract_then_mutate(path):
        Path(path).write_bytes(b"%PDF-replaced")
        return ["text"], []

    monkeypatch.setattr(foundry, "extract_pdf_pages", extract_then_mutate)
    runtime = FakeRuntime([])

    with pytest.raises(ValueError, match="source changed during extraction"):
        foundry.build_candidate_bundle(source, out, runtime)


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


def test_publish_retains_backup_when_restoration_is_blocked(tmp_path, monkeypatch):
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "keep.txt").write_text("previous-valid-bundle", encoding="utf-8")
    staging = tmp_path / ".bundle.foundry-staging-test"
    staging.mkdir()
    (staging / "new.txt").write_text("new", encoding="utf-8")

    original_replace = Path.replace

    def replace_with_race(self, target):
        target = Path(target)
        if self == staging and target == output:
            output.mkdir(exist_ok=True)
            raise OSError("simulated publication race")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace_with_race)

    with pytest.raises(OSError, match="simulated publication race"):
        foundry._publish_staging(staging, output, overwrite=True)

    backups = list(tmp_path.glob(".bundle.foundry-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "keep.txt").read_text(encoding="utf-8") == "previous-valid-bundle"
