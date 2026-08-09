from __future__ import annotations

import argparse
import json
from pathlib import Path

from erasmus.knowledge_foundry import build_candidate_bundle, validate_okf_bundle
from erasmus.runtime import LocalRuntimeConfig, OpenAICompatibleRuntime


def _runtime_config(path: str | Path) -> LocalRuntimeConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return LocalRuntimeConfig.from_mapping(raw)


def main() -> None:
    parser = argparse.ArgumentParser(prog="erasmus-foundry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Build a draft OKF v0.2 candidate bundle from PDFs.")
    build.add_argument("source_dir")
    build.add_argument("output_dir")
    build.add_argument("runtime_config")
    build.add_argument("--chunk-chars", type=int, default=6000)
    build.add_argument("--overlap-chars", type=int, default=500)
    build.add_argument("--max-concepts-per-chunk", type=int, default=4)
    build.add_argument("--overwrite", action="store_true")

    validate = sub.add_parser("validate", help="Validate a generated OKF candidate bundle.")
    validate.add_argument("bundle_dir")
    validate.add_argument("--write-report", action="store_true")

    args = parser.parse_args()

    if args.cmd == "build":
        config = _runtime_config(args.runtime_config)
        runtime = OpenAICompatibleRuntime(config)
        result = build_candidate_bundle(
            args.source_dir,
            args.output_dir,
            runtime,
            chunk_chars=args.chunk_chars,
            overlap_chars=args.overlap_chars,
            max_concepts_per_chunk=args.max_concepts_per_chunk,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    result = validate_okf_bundle(args.bundle_dir)
    if args.write_report:
        report = Path(args.bundle_dir) / "_foundry" / "validation-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
