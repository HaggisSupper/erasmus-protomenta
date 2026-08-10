from __future__ import annotations

from pathlib import Path


PATH = Path("src/erasmus/knowledge_foundry.py")


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one anchor, found {count}: {old[:100]!r}")
    return text.replace(old, new, 1)


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"missing start marker: {start_marker!r}")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"missing end marker: {end_marker!r}")
    return text[:start] + replacement + text[end:]


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "}\n\n\ndef discover_pdfs",
        """}

FOUNDRY_PROMPT_VERSION = "1.0.0"
FOUNDRY_PROMPT_PATH = Path(__file__).with_name("prompts") / "foundry-v1.json"
FOUNDRY_PROMPT_SHA256 = hashlib.sha256(FOUNDRY_PROMPT_PATH.read_bytes()).hexdigest()


def _load_foundry_prompt() -> dict[str, str]:
    try:
        data = json.loads(FOUNDRY_PROMPT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FoundryProtocolError(f"foundry prompt artifact is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise FoundryProtocolError("foundry prompt artifact must be an object")
    if data.get("version") != FOUNDRY_PROMPT_VERSION:
        raise FoundryProtocolError("foundry prompt artifact version mismatch")
    for field in ("system", "user_template"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise FoundryProtocolError(f"foundry prompt artifact lacks {field}")
    return data


def discover_pdfs""",
    )

    text = replace_between(
        text,
        "    def page_for(position: int) -> int:",
        "        if end == len(combined):",
        """    def pages_for_range(range_start: int, range_end: int) -> list[int]:
        return [
            number
            for page_start, page_end, number in offsets
            if page_end > page_start
            and max(range_start, page_start) < min(range_end, page_end)
        ]

    chunks: list[SourceChunk] = []
    start = 0
    while start < len(combined):
        end = min(start + chunk_chars, len(combined))
        text = combined[start:end]
        covered_pages = pages_for_range(start, end)
        if text.strip() and covered_pages:
            chunks.append(
                SourceChunk(
                    path=path,
                    start_page=covered_pages[0],
                    end_page=covered_pages[-1],
                    text=text,
                )
            )
""",
    )

    text = replace_once(
        text,
        '                "erasmus_runtime": runtime_kind,\n            },',
        '                "erasmus_runtime": runtime_kind,\n'
        '                "prompt_version": FOUNDRY_PROMPT_VERSION,\n'
        '                "prompt_sha256": FOUNDRY_PROMPT_SHA256,\n'
        '            },',
    )

    marker = '    concept_dir = root / "concepts"'
    manifest_block = """    manifest_by_resource: dict[str, dict[str, Any]] = {}
    manifest_path = root / "_foundry" / "source-manifest.json"
    if not manifest_path.is_file():
        errors.append("missing source manifest: _foundry/source-manifest.json")
    else:
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid source manifest: {exc}")
            manifest_data = []
        if not isinstance(manifest_data, list):
            errors.append("source manifest must be a JSON array")
            manifest_data = []
        for index, entry in enumerate(manifest_data):
            if not isinstance(entry, dict):
                errors.append(f"source manifest entry {index} must be an object")
                continue
            source_path = entry.get("path")
            digest = entry.get("sha256")
            pages = entry.get("pages")
            resource = entry.get("resource")
            if resource is None and isinstance(digest, str):
                resource = f"urn:sha256:{digest}"
            if (
                not isinstance(source_path, str)
                or not source_path
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or resource != f"urn:sha256:{digest}"
                or not isinstance(pages, int)
                or pages < 1
            ):
                errors.append(f"source manifest entry {index} is invalid")
                continue
            if resource in manifest_by_resource:
                errors.append(f"source manifest duplicates resource: {resource}")
                continue
            manifest_by_resource[resource] = {"path": source_path, "pages": pages}

"""
    if marker not in text:
        raise SystemExit("concept directory marker missing")
    text = text.replace(marker, manifest_block + marker, 1)

    needle = '                        errors.append(f"concept has invalid source span: {path.relative_to(root)}")'
    replacement = needle + """
                        continue
                    resource = str(source.get("resource"))
                    manifest_entry = manifest_by_resource.get(resource)
                    if manifest_entry is None:
                        errors.append(
                            f"concept source resource is absent from manifest: {path.relative_to(root)}"
                        )
                        continue
                    if erasmus["source_path"] != manifest_entry["path"]:
                        errors.append(
                            f"concept source path disagrees with manifest: {path.relative_to(root)}"
                        )
                    if end_page > manifest_entry["pages"]:
                        errors.append(
                            f"source span exceeds manifest page count: {path.relative_to(root)}"
                        )"""
    text = replace_once(text, needle, replacement)

    needle = '                errors.append(f"concept lacks generation provenance: {path.relative_to(root)}")'
    replacement = needle + """
            elif (
                generated.get("prompt_version") != FOUNDRY_PROMPT_VERSION
                or generated.get("prompt_sha256") != FOUNDRY_PROMPT_SHA256
            ):
                errors.append(f"concept has invalid prompt provenance: {path.relative_to(root)}")"""
    text = replace_once(text, needle, replacement)

    semantic_start = text.find("def _semantic_candidates(")
    if semantic_start < 0:
        raise SystemExit("semantic function missing")
    system_start = text.find("    system = (", semantic_start)
    raw_start = text.find("    raw = runtime.complete_nonstream(", system_start)
    if system_start < 0 or raw_start < 0:
        raise SystemExit("semantic prompt block markers missing")
    semantic_prompt = """    prompt = _load_foundry_prompt()
    system = prompt["system"]
    user = prompt["user_template"].format(
        max_concepts_per_chunk=max_concepts_per_chunk,
        source_path=span.path,
        start_page=span.start_page,
        end_page=span.end_page,
        source_text=chunk.text,
    )
"""
    text = text[:system_start] + semantic_prompt + text[raw_start:]

    text = replace_between(
        text,
        "def _publish_staging(staging: Path, output: Path, *, overwrite: bool) -> None:",
        "\n\ndef build_candidate_bundle(",
        """def _publish_staging(staging: Path, output: Path, *, overwrite: bool) -> None:
    backup: Path | None = None
    publication_succeeded = False
    try:
        if output.exists():
            if not overwrite:
                raise FileExistsError(output)
            backup = output.parent / f".{output.name}.foundry-backup-{uuid.uuid4().hex}"
            output.replace(backup)
        staging.replace(output)
        publication_succeeded = True
    except Exception:
        if backup is not None and backup.exists() and not output.exists():
            backup.replace(output)
        raise
    finally:
        if staging.exists():
            if staging.is_dir():
                shutil.rmtree(staging)
            else:
                staging.unlink()
        if publication_succeeded and backup is not None and backup.exists():
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink()
""",
    )

    text = replace_once(
        text,
        '    if source_root == output or output in source_root.parents:\n'
        '        raise ValueError("output directory must not contain the source directory")',
        """    if (
        source_root == output
        or output in source_root.parents
        or source_root in output.parents
    ):
        raise ValueError("output directory must be disjoint from the source directory")""",
    )

    text = replace_once(
        text,
        "        digest = sha256_file(pdf)\n"
        "        pages, textless_pages = extract_pdf_pages(pdf)\n"
        "        relative = pdf.relative_to(source_root).as_posix()",
        """        digest = sha256_file(pdf)
        pages, textless_pages = extract_pdf_pages(pdf)
        if sha256_file(pdf) != digest:
            raise ValueError(f"source changed during extraction: {pdf}")
        relative = pdf.relative_to(source_root).as_posix()""",
    )

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
