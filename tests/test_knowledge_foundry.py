import json
from pathlib import Path

import pytest

from erasmus import knowledge_foundry as foundry


class FakeRuntime:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.config = type("Config", (), {"model": "local-test-model", "runtime_kind": "mistral_rs"})()

    def complete_nonstream(self, messages):
        self.calls.append(messages)
        return next(self.responses)


def test_discover_pdfs_is_recursive_sorted_and_case_insensitive(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "a.pdf").write_bytes(b"%PDF-test")
    (tmp_path / "b" / "Z.PDF").write_bytes(b"%PDF-test")
    (tmp_path / "ignore.txt").write_text("no", encoding="utf-8")

    assert [p.relative_to(tmp_path).as_posix() for p in foundry.discover_pdfs(tmp_path)] == [
        "a.pdf", "b/Z.PDF"
    ]


def test_chunk_pages_preserves_page_spans_and_overlap():
    pages = ["A" * 60, "B" * 60]
    chunks = foundry.chunk_pages(Path("sample.pdf"), pages, chunk_chars=80, overlap_chars=20)

    assert len(chunks) >= 2
    assert chunks[0].start_page == 1
    assert chunks[-1].end_page == 2
    assert chunks[0].text[-20:] == chunks[1].text[:20]


def test_parse_candidate_response_accepts_json_fence_and_rejects_wrong_shape():
    raw = "```json\n[{\"title\":\"Cache\",\"type\":\"Concept\",\"description\":\"d\",\"body\":\"b\",\"tags\":[\"x\"],\"related_titles\":[]}]\n```"
    parsed = foundry.parse_candidate_response(raw)
    assert parsed[0]["title"] == "Cache"

    with pytest.raises(foundry.FoundryProtocolError):
        foundry.parse_candidate_response('{"title":"not-an-array"}')

    with pytest.raises(foundry.FoundryProtocolError):
        foundry.parse_candidate_response('[{"title":"missing fields"}]')


def test_merge_candidates_deduplicates_titles_and_preserves_all_source_spans():
    source_a = foundry.SourceSpan("a.pdf", "urn:sha256:" + "a" * 64, 1, 2)
    source_b = foundry.SourceSpan("b.pdf", "urn:sha256:" + "b" * 64, 3, 4)
    first = foundry.CandidateConcept("KV Cache", "Concept", "one", "body one", ("cache",), (), (source_a,))
    second = foundry.CandidateConcept("kv cache", "Concept", "two", "body two", ("inference",), (), (source_b,))

    merged = foundry.merge_candidates([first, second])
    assert len(merged) == 1
    assert {span.path for span in merged[0].sources} == {"a.pdf", "b.pdf"}
    assert set(merged[0].tags) == {"cache", "inference"}
    assert "body one" in merged[0].body and "body two" in merged[0].body


def test_write_and_validate_bundle_keeps_generated_concepts_draft(tmp_path):
    out = tmp_path / "bundle"
    source = foundry.SourceSpan("paper.pdf", "urn:sha256:" + "c" * 64, 2, 3)
    concepts = [
        foundry.CandidateConcept(
            "Agent Memory", "Memory", "Durable memory", "Evidence-backed body", ("memory",), (), (source,)
        )
    ]
    manifest = [{"path": "paper.pdf", "sha256": "c" * 64, "pages": 3, "textless_pages": []}]

    foundry.write_candidate_bundle(out, concepts, manifest, "model-x", "mistral_rs")
    report = foundry.validate_okf_bundle(out)

    assert report["valid"] is True
    concept_text = next((out / "concepts").glob("*.md")).read_text(encoding="utf-8")
    frontmatter = json.loads(concept_text.split("---", 2)[1])
    assert frontmatter["status"] == "draft"
    assert "verified" not in frontmatter
    assert frontmatter["generated"]["by"] == "model:model-x"
    assert frontmatter["sources"][0]["resource"].startswith("urn:sha256:")


def test_validate_bundle_fails_broken_internal_link(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "index.md").write_text("---\n{\"okf_version\":\"0.2\"}\n---\n\n[bad](missing.md)\n", encoding="utf-8")
    report = foundry.validate_okf_bundle(bundle)
    assert report["valid"] is False
    assert any("missing.md" in error for error in report["errors"])


def test_build_candidate_bundle_is_end_to_end_and_fail_closed_on_existing_output(tmp_path, monkeypatch):
    source_dir = tmp_path / "pdfs"
    source_dir.mkdir()
    pdf = source_dir / "paper.pdf"
    pdf.write_bytes(b"%PDF-placeholder")
    monkeypatch.setattr(foundry, "extract_pdf_pages", lambda path: (["A useful concept about bounded agent tools."], []))
    runtime = FakeRuntime([
        '[{"title":"Bounded Tools","type":"Agent Pattern","description":"Typed tools","body":"Use narrow deterministic tools.","tags":["tools"],"related_titles":[]}]'
    ])

    out = tmp_path / "okf"
    result = foundry.build_candidate_bundle(source_dir, out, runtime, chunk_chars=200, overlap_chars=20)
    assert result["valid"] is True
    assert result["concept_count"] == 1
    assert (out / "_foundry" / "source-manifest.json").exists()
    assert (out / "_foundry" / "candidates.jsonl").exists()
    assert runtime.calls and "untrusted source evidence" in runtime.calls[0][0]["content"].lower()

    with pytest.raises(FileExistsError):
        foundry.build_candidate_bundle(source_dir, out, runtime)
