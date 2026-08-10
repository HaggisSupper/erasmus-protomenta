# OKF Knowledge Foundry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded local-first PDF-to-OKF v0.2 candidate-concept pipeline that reuses Erasmus's existing OpenAI-compatible runtime and cannot automatically promote generated knowledge.

**Architecture:** Deterministic code owns PDF discovery, hashing, extraction, chunking, normalization, provenance, serialization, and validation. The local model owns only semantic candidate extraction from bounded source chunks. Output is a standalone draft OKF bundle plus source/candidate manifests.

**Tech Stack:** Python 3.12, `pypdf`, existing `erasmus.runtime.OpenAICompatibleRuntime`, stdlib JSON/hash/path tooling, pytest, GitHub Actions Windows + Ubuntu matrix.

## Global Constraints

- Preserve the locked Phase 1–3 development sequence.
- Generated concepts remain draft candidates and never write to ledger/capability/skill state.
- Local-first; reuse mistral.rs/llama.cpp-compatible runtime configuration.
- Deterministic-first; model inference is limited to semantic synthesis.
- No Docker.
- Windows-first operator commands.
- Additive and rollback-safe; no database migration.

---

### Task 1: Foundry deterministic core and tests

**Files:**
- Create: `tests/test_knowledge_foundry.py`
- Create: `src/erasmus/knowledge_foundry.py`

**Interfaces:**
- Produces: `discover_pdfs`, `extract_pdf_pages`, `chunk_pages`, `parse_candidate_response`, `build_candidate_bundle`, `validate_okf_bundle`.

- [ ] Write failing tests for PDF discovery, extraction, hashing/provenance, chunking, strict JSON parsing, deduplication, draft metadata, overwrite protection, and validation.
- [ ] Run `python -m pytest tests/test_knowledge_foundry.py -v` and confirm failures are caused by the absent implementation.
- [ ] Implement the minimum deterministic pipeline and fake-runtime integration needed to pass.
- [ ] Re-run the focused tests and then the full repository suite.

### Task 2: Operator CLI

**Files:**
- Create: `src/erasmus/foundry_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `erasmus-foundry build` and `erasmus-foundry validate`.

- [ ] Add CLI tests through the foundry test module.
- [ ] Add the `pypdf` runtime dependency and `erasmus-foundry` console script.
- [ ] Validate runtime config via existing `LocalRuntimeConfig` and use `OpenAICompatibleRuntime` unchanged.
- [ ] Run focused and complete tests.

### Task 3: Documentation and governance boundary

**Files:**
- Create: `docs/architecture/okf-knowledge-foundry.md`
- Modify: `README.md`

- [ ] Document data flow, commands, output layout, trust semantics, Phase-3 boundary, failure behavior, and rollback.
- [ ] Document that PDFs are untrusted evidence and generated concepts are not verified knowledge.
- [ ] Run documentation/link-adjacent existing validation plus full CI-equivalent tests.

### Task 4: GitHub acceptance

- [ ] Open a draft PR from `feat/okf-knowledge-foundry` to `main` with exact acceptance criteria and 10th-Man countercase.
- [ ] Inspect GitHub Actions results on the PR head.
- [ ] Repair any failures without weakening tests or phase gates.
- [ ] Confirm review/10th-Man evidence before merge; otherwise leave the PR blocked with the exact remaining action.
