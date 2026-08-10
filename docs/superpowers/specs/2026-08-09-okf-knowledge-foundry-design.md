# OKF Knowledge Foundry Design

## Purpose

Add a bounded, local-first ingestion capability that converts PDF source material into provenance-bearing **candidate** Google Open Knowledge Format (OKF) v0.2 concepts. This increment must not bypass the locked Erasmus Phase 1–3 sequence: generated concepts remain draft artifacts and are never promoted into the epistemic ledger, capability graph, skills, or canonical knowledge automatically.

## Architectural fit

The existing Erasmus capability graph already establishes OKF as a semantic representation and the runtime already provides a provider-neutral OpenAI-compatible local model client. The foundry reuses those seams instead of introducing a second runtime or knowledge authority.

Pipeline:

`PDF source -> deterministic discovery/hash/extraction/chunking -> local semantic concept proposal -> deterministic normalization/deduplication -> OKF candidate bundle -> deterministic validation`

Vector indexes, GraphRAG, contradiction reconciliation, canonical promotion, autonomous memory mutation, and graph-backed world-model behavior remain deferred Phase 3 work.

## Components

### `erasmus.knowledge_foundry`

Owns deterministic PDF discovery, SHA-256 source identity, page-aware extraction, bounded chunking, strict model-response decoding, duplicate consolidation, OKF v0.2 document generation, manifest generation, and validation.

The module accepts the existing `OpenAICompatibleRuntime` contract. It does not start or configure a model server itself.

### `erasmus-foundry` CLI

A separate narrow entry point avoids inflating the main Erasmus command router. Commands:

- `erasmus-foundry build <source_dir> <output_dir> <runtime_config>`
- `erasmus-foundry validate <bundle_dir> [--write-report]`

Build is fail-closed by default if the output exists. `--overwrite` explicitly authorizes replacement.

## Trust and provenance

Every generated concept is `status: draft`, includes model-generation provenance, and links to source evidence by immutable SHA-256 URN plus source path/page ranges. The tool must never populate OKF `verified` metadata because generation is not independent verification.

A `_foundry/source-manifest.json` records every source file, digest, page count, and textless pages. `_foundry/candidates.jsonl` records normalized candidate metadata and source spans.

## Model boundary

The model receives one bounded source chunk and must return a JSON array only. Candidate schema fields are title, type, description, body, tags, and related_titles. Invalid output fails that chunk rather than being silently accepted.

The model is used only for semantic extraction and synthesis. Discovery, hashing, extraction, chunking, file paths, deduplication keys, provenance, OKF serialization, links, and validation are deterministic.

## Security and authority

Input PDFs are untrusted data. Their text is explicitly framed as source evidence, not instructions. The foundry has no execution tools and no authority to mutate ledger propositions, missions, capabilities, tool manifests, skills, or existing canonical OKF bundles.

## Testing

Tests cover PDF discovery, hashing, extraction, chunk overlap, fenced/invalid JSON handling, deterministic deduplication, draft provenance, internal-link validation, overwrite protection, and an end-to-end build with a fake runtime. CI remains the repository's Ubuntu/Windows Python 3.12 matrix.

## Rollback

The feature is additive. Rollback is deletion of the new module, entry point, dependency, tests, and documentation. It adds no migration and mutates no existing database schema.

## 10th-Man countercase

The strongest countercase is that this is premature Phase 3 knowledge infrastructure. The containment is deliberate: this increment produces only inspectable candidate bundles and cannot promote or reconcile knowledge. It solves the concrete observed need to ingest the user-created PDF/OKF corpus while preserving the existing phase gate for governed long-term knowledge evolution.
