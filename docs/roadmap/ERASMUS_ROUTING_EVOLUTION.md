# Erasmus Routing Evolution Track

- **Status:** Deferred additive target track
- **Authority:** Subordinate to `docs/DEVELOPMENT_TRACK.md`, `AGENTS.md`, the immutable contract, and bounded missions
- **Implementation rule:** No current milestone may be delayed, re-scoped, or refactored solely to accommodate this track.

## 1. Objective

Introduce the adaptive, provider-agnostic routing and experienced problem-resolution architecture as an incremental evolution of the existing Erasmus control plane.

The current repository already contains a governed Python kernel, one SQLite operational store, bounded missions, deterministic capability/tool execution, epistemic and immune controls, sleep consolidation, skill promotion, local-runtime integration, MCP governance, and GitHub orchestration. This track may evolve those facilities only through additive, measured, reversible seams that do not disturb their current contracts or issue sequence.

## 2. Non-infringement rules

1. Existing bootstrap/control-plane issues retain priority and sequence.
2. Current public contracts are not mutated. New versions or extension contracts must be added.
3. No deep RL, graph database, model training, adapter framework, or Tauri observability UI enters the critical path.
4. No runtime is replaced. mistral.rs remains the preferred local runtime and llama.cpp remains fallback where already planned.
5. No provider-specific model taxonomy enters core contracts.
6. The initial router remains static and deterministic until sufficient validated telemetry exists.
7. Every new subsystem is feature-gated and may remain unimplemented without affecting the existing system.
8. Documentation landing does not constitute implementation authorization.

## 3. Compatibility sequence

### Track A — Current implementation trajectory

Continue unchanged:

- the one-process/one-SQLite kernel;
- bounded mission and capability execution;
- deterministic tool registry and evidence collection;
- epistemic, immune, sleep and skill-promotion boundaries;
- current local-runtime and headless execution contracts;
- MCP and OpenCode/GitHub integration already accepted on `main`;
- repository governance, CI, PR and issue sequencing.

### Track B0 — Documentation landing

May occur immediately because it changes no runtime behavior:

- add the accepted target architecture specification;
- add the contract catalogue;
- add starter schemas under a clearly namespaced path;
- record the architecture decision;
- add this deferred roadmap track.

**Exit criterion:** documentation validation passes and existing CI behavior is unchanged.

### Track B1 — Telemetry compatibility seam

Open only after the current control plane emits stable typed execution events.

Add optional fields or new event versions for:

- task signature reference;
- selected resource and tool path;
- validation outcome;
- latency and cost units;
- failure and recovery classification;
- route provenance.

No learning or adaptive routing is required.

**Exit criterion:** current execution behavior is identical with telemetry disabled or ignored.

### Track B2 — Static resource registry and policy router

Open only after runtime adapters and tool contracts are stable.

Deliver:

- provider-neutral resource profiles;
- hard-constraint filtering;
- static route scoring;
- explainable route decisions;
- compatibility with the existing runtime selection path.

The router must be deployable in observation-only mode before it is allowed to select resources.

### Track B3 — Deterministic tool-path recording

Record which deterministic tools were used and which outputs were authoritative. This phase uses existing compiler, test, lint, schema, search, and PowerShell tooling; it does not introduce learning.

### Track B4 — Compact routing graph cache

Introduce only after enough stable route observations exist. Start as an embedded cache and durable summary store. Prefer Rust for a separately authorized performance-critical component only after measurement; otherwise extend the current kernel through its existing contracts. Do not add a remote or heavyweight graph database to the hot path.

### Track B5 — Problem-resolution cases and lessons

Persist:

- hypotheses;
- tests;
- evidence;
- false forks marked `disproven_here` rather than globally invalid;
- rollback and alternate branches;
- successful resolution and validation;
- generalized lessons with applicability boundaries.

This remains advisory until promotion and drift controls are proven.

### Track B6 — Reinforced route map

Bootstrap with interpretable statistics, Bayesian estimates, contextual bandits, and route-segment credit assignment. Deep reinforcement learning is explicitly deferred.

### Track B7 — Per-call adapters and architecture-neutral optimization

Add LoRA, multi-LoRA, X-LoRA, Mamba/state-space, and backend-specific acceleration only as optional runtime capabilities. Vanilla model support remains the functional baseline.

### Track B8 — Optimization motifs and state-vector graph

Add cross-case optimization motifs and the abstract angle/magnitude-inspired state-vector representation only after scalar and probabilistic routing baselines are benchmarked. This is an adaptation of the underlying principle, not a direct port of TurboQuant or any other referenced system.

### Track B9 — Tauri observability surface

Add the UI after the control-plane APIs, telemetry, graph, lesson, and replay contracts are stable. The UI must not become the control plane.

## 4. Promotion gates

A deferred phase may enter implementation only when all prior conditions are met:

- current bootstrap milestone is complete or unaffected;
- named immutable contracts exist;
- feature flag and rollback path exist;
- deterministic tests exist before implementation;
- CI cost and runtime remain acceptable;
- no hidden provider or architecture coupling is introduced;
- authoritative current behavior remains available as fallback;
- definition of done is evidence-based.

## 5. Initial issue order

1. Land architecture documents, schema seeds and ADR under Mission #62.
2. Close Track B0 after documentation and diff verification.
3. Do not open B1 until a concrete routing failure or measurement justifies telemetry expansion.
4. Define any telemetry extension without changing existing producers or consumers by default.
5. Add fixtures and validation tests before registering a live contract.
6. Introduce any resource registry first in disabled, observation-only mode.
7. Benchmark correctness, latency, memory and operational burden.
8. Reassess through a fresh bounded mission before granting adaptive control authority.

## 6. Explicitly deferred

- deep RL;
- autonomous policy mutation;
- heavyweight graph infrastructure;
- mandatory LoRA/X-LoRA;
- training pipelines in the bootstrap path;
- replacement of existing runtime selection;
- broad refactors of working control-plane modules;
- a new Tauri application before backend contracts stabilize.
