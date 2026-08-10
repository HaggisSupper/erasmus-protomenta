# OKF Knowledge Foundry

## Status

Bounded candidate-ingestion capability. This is **not** the Phase 3 canonical knowledge system.

## Purpose

The foundry converts a folder tree of PDFs into an inspectable Google Open Knowledge Format (OKF) v0.2 candidate bundle while preserving source identity and page provenance. It exists to turn external research and engineering documents into reviewable semantic artifacts without granting those artifacts epistemic authority.

## Data flow

```text
PDF folder
  -> recursive discovery
  -> SHA-256 source identity
  -> page text extraction
  -> source digest re-verification
  -> bounded overlapping chunks with page-content spans
  -> versioned local-model semantic proposal
  -> strict JSON contract validation
  -> deterministic title normalization/deduplication
  -> OKF v0.2 draft concept documents
  -> manifest, source-span, internal-link, and metadata validation
```

All source text is treated as untrusted evidence. The model prompt explicitly instructs the runtime that embedded source instructions have no authority. The extraction prompt is a versioned repository artifact; generated concepts record both its version and SHA-256 digest.

## Runtime

The foundry reuses `LocalRuntimeConfig` and `OpenAICompatibleRuntime`. This keeps mistral.rs as the normal local runtime and preserves llama.cpp/OpenAI-compatible fallback behavior already supported by Erasmus.

The foundry does not start a model server, choose a model, or write credentials.

## Commands

```powershell
erasmus-foundry build `
  D:\Knowledge\PDFs `
  D:\Knowledge\erasmus-okf-candidates `
  configs\local-runtime.example.json
```

Optional controls:

```powershell
--chunk-chars 6000
--overlap-chars 500
--max-concepts-per-chunk 4
--overwrite
```

Validate an existing candidate bundle:

```powershell
erasmus-foundry validate D:\Knowledge\erasmus-okf-candidates --write-report
```

## Output contract

```text
erasmus-okf-candidates/
├── index.md
├── concepts/
│   └── <concept>.md
└── _foundry/
    ├── source-manifest.json
    ├── candidates.jsonl
    └── validation-report.json   # only when requested
```

Every generated concept:

- has non-empty `type` metadata;
- has `status: draft`;
- records `generated.by`, generation time, model, runtime kind, prompt version, and prompt digest;
- records immutable `urn:sha256:<digest>` source resources;
- records source path and page ranges in Erasmus-specific source metadata;
- has each source resource/path/page span cross-checked against `_foundry/source-manifest.json` during validation;
- omits `verified` because synthesis is not independent verification.

## Provenance and publication hardening

- The source PDF is hashed before extraction and hashed again immediately after extraction. A changed source aborts the build before semantic synthesis is accepted.
- Inter-page separator bytes are not attributed to a page. Chunk provenance is calculated only from actual page-text overlap.
- Source and output directories must be disjoint: output cannot equal, contain, or be nested within the source tree.
- Overwrite publication uses staging plus a backup of the previous valid bundle. The backup is deleted only after successful publication; if restoration is blocked, the backup is retained for operator recovery.
- Bundle validation requires the source manifest and rejects unknown resources, mismatched paths, and page spans beyond the manifest page count.

## Failure behavior

The build fails closed when:

- the source path is not a directory;
- source and output trees overlap in either direction;
- no PDFs are found;
- a source changes between hashing and extraction;
- a PDF is encrypted and cannot be opened without credentials;
- the local model violates the strict candidate JSON contract;
- the model exceeds the declared per-chunk candidate bound;
- no concepts are produced;
- output already exists without `--overwrite`;
- source-manifest or source-span validation fails;
- prompt provenance is missing or mismatched;
- generated OKF validation fails.

Textless pages are listed in the source manifest instead of being silently represented as extracted evidence. OCR is deliberately not implicit in this increment because OCR adds another executable/tool contract and should be introduced separately if a concrete mission requires it.

## Phase boundary

The foundry does **not**:

- write ledger evidence or propositions;
- promote or verify concepts;
- reconcile contradictions with existing knowledge;
- update the capability graph;
- create or promote skills;
- build vector or graph indexes;
- mutate an existing canonical OKF bundle.

Those operations remain governed by the locked development track. A later Phase 3 mission can consume these candidate bundles through explicit review, evidence, contradiction, supersession, and promotion contracts.

## Rollback

This increment adds no database migrations. Rollback consists of removing the foundry module, CLI entry point, versioned prompt artifact, `pypdf` dependency, tests, and documentation. Candidate output directories are external artifacts and can be deleted independently. If an interrupted overwrite retains a `.foundry-backup-*` directory, preserve it until the previous valid bundle is restored or explicitly retired.
