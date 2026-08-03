# Erasmus Engineering Platform Requirements Addendum

- **Version:** 1.0.0
- **Status:** Accepted additional requirements; deferred and mission-gated
- **Scope:** Erasmus runtime, memory, skills, verification, reconnaissance, local inference, multi-agent governance, and engineering-platform evolution
- **Authority:** Subordinate to repository constitutional rules, bounded missions, existing phase gates, and accepted ADRs
- **Preferred implementation posture:** Windows-first; Rust-first for new performance-critical components; Tauri 2 for desktop surfaces; mistral.rs primary; llama.cpp fallback; CUDA preferred with Vulkan/WebGPU fallback; no Docker

## 1. Purpose and integration boundary

This addendum records additional requirements derived from the broader Erasmus project. It does not authorize immediate implementation, replace the current kernel, or alter the locked development sequence.

Each requirement shall be promoted only through a bounded mission with explicit acceptance criteria, architecture review, deterministic and negative tests, rollback, evidence capture, and 10th-Man review. Existing contracts and runtime authority remain in force until a versioned migration is independently validated.

## 2. Bootstrap control plane

Erasmus shall provide a robust bootstrap control plane capable of starting, verifying, supervising, recovering, and stopping its required local services.

The bootstrap control plane shall:

1. Discover the active Erasmus installation, project context, configuration, models, tools, skills, databases, and runtime dependencies.
2. Start required databases, stores, local model runtimes, embedding services, graph services, tool servers, and orchestration services in dependency order.
3. Prefer headless and silent operation while preserving structured status, logs, and failure evidence.
4. Verify GPU availability, CUDA compatibility, fallback backends, model files, ports, schemas, migrations, and service health before declaring readiness.
5. Detect already-running compatible services and reuse them safely rather than spawning duplicates.
6. Recover stale locks, interrupted missions, orphaned processes, incomplete migrations, and partially written state through explicit recovery rules.
7. Restore authorized project and mission state after restart without treating conversation transcripts as authoritative runtime state.
8. Expose deterministic health, readiness, degraded-mode, and shutdown contracts.
9. Support mistral.rs as the primary local inference runtime and llama.cpp as a contract-compatible fallback.
10. Operate without Docker or an assumed Linux container environment.

## 3. Runtime kernel

Erasmus shall evolve toward a persistent runtime kernel that coordinates the platform while preserving current authority boundaries during migration.

The runtime kernel shall own or govern:

- agent lifecycle and role activation;
- service startup, dependency ordering, health supervision, and shutdown;
- mission and project state transitions;
- event routing and durable queues;
- scheduling and retry budgets;
- capability and skill discovery;
- deterministic-tool and inference-resource routing;
- memory reads, writes, promotion, invalidation, and provenance;
- crash recovery and resumable work;
- observability, audit, and evidence emission;
- policy enforcement and protected control-plane state.

The kernel shall not be implemented as an unbounded monolith. Components shall communicate through versioned typed contracts and explicit authority boundaries.

## 4. Long-lived architectural and engineering memory

Erasmus shall maintain durable engineering memory distinct from conversational memory.

The minimum governed record types shall include:

- architecture decision records;
- requirements and constraints;
- hypotheses and experiments;
- accepted, rejected, deferred, superseded, and invalidated proposals;
- implementation and migration status;
- validation evidence and regressions;
- technical debt and risk records;
- failure modes and recovery procedures;
- project-specific and cross-project lessons;
- reusable optimization motifs.

Every promoted memory item shall include provenance, scope, applicability, confidence, evidence, version, supersession state, and review status. Memory shall never silently grant capability authority or modify immutable contracts.

## 5. Graph-grounded world model

Erasmus shall support a graph-grounded world model for engineering knowledge and operational state.

The system shall transform source material and validated observations into governed entities, relationships, constraints, claims, evidence, states, and temporal changes.

Vector search and embeddings may support discovery and candidate retrieval, but shall not be treated as the authoritative knowledge representation. Authoritative conclusions shall remain traceable to typed graph structures, source evidence, deterministic validation, or explicitly qualified inference.

The world model shall support:

- entity and relationship identity;
- temporal and versioned state;
- claims, evidence, contradiction, and uncertainty;
- project, domain, environment, tool, model, runtime, and hardware context;
- constraint propagation and dependency traversal;
- problem-resolution traces and alternate diagnostic forks;
- selective retrieval of bounded context packets;
- invalidation, supersession, and rollback.

A generic remote graph database shall not be required on the hot path. The implementation may use an embedded operational graph, durable append-only records, and generated projections where appropriate.

## 6. Executable self-growing skill library

Erasmus shall maintain a governed skill library in which reusable procedures are executable, testable, versioned, and promotable.

Each skill package shall include, where applicable:

- standards-compliant skill metadata and instructions;
- declared capabilities and required authority;
- typed input and output contracts;
- deterministic tools and exact implementation references;
- tests, negative tests, fixtures, and validators;
- platform and runtime requirements;
- setup and execution automation;
- evidence and observability requirements;
- rollback and failure handling;
- documentation and examples;
- provenance, version, digest, and compatibility metadata.

Agents may propose or construct new tools and skills, but generated capabilities shall remain quarantined until validated, reviewed, versioned, and promoted. Tools shall be retained in a governed tool repository rather than discarded after one use.

Self-improvement shall mean evidence-backed refinement under policy, not unrestricted self-modification.

## 7. Deterministic computation and tool layer

Erasmus shall treat deterministic tools as first-class execution resources and generative models as planners, interpreters, synthesizers, or fallback reasoning resources.

The deterministic layer shall cover, as relevant:

- compilation, formatting, static analysis, tests, benchmarks, and packaging;
- schema, configuration, and contract validation;
- mathematics, units, symbolic and numerical computation;
- statistics, optimization, constraints, and uncertainty propagation;
- signal, image, geometry, point-cloud, mesh, CAD, and engineering processing;
- database queries and data transformations;
- file, repository, operating-system, and process operations;
- security, provenance, digest, and dependency inspection.

A model assertion shall not substitute for obtainable deterministic evidence. Tool outputs shall be captured with exact tool identity, version, arguments, environment, result, and artifact references.

## 8. Agent quality gates and definition of done

No agent may declare consequential work complete solely through self-report.

Every bounded implementation mission shall pass an applicable verification pipeline containing:

1. scope and contract validation;
2. implementation completeness checks;
3. build or compile validation;
4. unit tests;
5. integration tests;
6. automation or end-to-end tests;
7. configuration and schema validators;
8. static analysis and linting;
9. security and dependency review;
10. performance and resource checks where material;
11. architecture and contract-boundary review;
12. documentation synchronization;
13. rollback verification;
14. independent reviewer or model-council assessment where required;
15. 10th-Man countercase;
16. acceptance-criteria evidence.

A failed gate shall produce a repair mission, explicit deferral, or rollback. It shall not be converted into a successful completion by narrative qualification.

## 9. Continuous technical reconnaissance

Erasmus shall support governed reconnaissance of relevant technical developments, including:

- local inference runtimes and model architectures;
- mistral.rs and llama.cpp;
- Rust crates and language/toolchain changes;
- Tauri and Windows-native application tooling;
- CUDA, Vulkan, and WebGPU capabilities;
- agent frameworks, skills, deterministic tools, and orchestration patterns;
- security advisories and dependency risks;
- relevant research papers and engineering methods.

Reconnaissance findings shall be deduplicated, source-backed, ranked by applicability and evidence, and compared against current architecture. A finding may create a candidate issue or proposal, but shall not automatically alter requirements, dependencies, runtime behavior, or canonical architecture.

## 10. Local-first inference and graceful fallback

Erasmus shall prefer local execution where capability, validation strength, latency, privacy, and resource constraints permit.

The routing order shall be policy-driven but default to:

1. deterministic local tool;
2. validated local model or multimodal runtime;
3. local alternative runtime or backend;
4. authorized hosted capability;
5. explicit degraded or blocked result.

The system shall remain useful offline for supported missions. Cloud use shall be explicit, auditable, budgeted, provider-neutral, and subject to data-governance policy.

Runtime and hardware selection shall support:

- mistral.rs primary local serving;
- llama.cpp fallback;
- CUDA acceleration where compatible;
- Vulkan/WebGPU fallback where available;
- optimized CPU fallback;
- model, quantization, adapter, context, and inference-state compatibility checks.

## 11. Multi-agent council and independent adjudication

Erasmus shall support multiple governed agents with explicit roles rather than treating all agents as interchangeable workers.

The role catalogue may include:

- mission governor;
- architect;
- systems engineer;
- implementation engineer;
- performance engineer;
- security reviewer;
- quality and test engineer;
- domain expert;
- evidence auditor;
- 10th-Man adversarial reviewer;
- synthesizer or adjudicator.

Each role shall have declared authority, permitted capabilities, required evidence, conflict rules, retry and cost budgets, and stop conditions. Disagreement shall be preserved as structured evidence and resolved through deterministic results, explicit policy, or an authorized adjudicator rather than averaged away.

## 12. Erasmus as an engineering operating platform

Erasmus shall be designed as a persistent engineering operating platform rather than only a conversational coding assistant.

The platform shall eventually coordinate:

- repositories, branches, issues, pull requests, CI, review, merge, and rollback;
- missions, plans, contracts, tasks, agents, and evidence;
- local models, runtimes, adapters, tools, and hardware resources;
- engineering documents, decisions, requirements, and knowledge;
- data stores, vector indexes, graphs, and telemetry;
- skills, capability packages, and toolchains;
- scheduling, monitoring, alerts, and recovery;
- user-facing status, control, and audit surfaces.

The LLM is one subsystem within this platform. It shall not be the sole state store, scheduler, verifier, authority system, or execution engine.

## 13. De-emphasized approaches

The following approaches shall not become default architectural assumptions:

- embedding-centric RAG as the authoritative memory model;
- large monolithic prompts as the primary governance mechanism;
- unrestricted autonomous agents without contracts and verification;
- model self-evaluation as sufficient completion evidence;
- cloud-first execution;
- hidden or transcript-only operational state;
- whole-kernel rewrites without reversible staged migration;
- direct ports of analogous projects where only the abstract mechanism is relevant.

## 14. Required cross-cutting qualities

All promoted components shall satisfy applicable requirements for:

- typed and versioned contracts;
- deterministic fallback;
- explicit authority and least privilege;
- idempotent setup and recovery;
- structured JSONL-compatible logging and evidence;
- observability and health reporting;
- offline and degraded operation;
- reversible migration and rollback;
- bounded retries, budgets, and stop conditions;
- secure secret handling;
- provenance, checksums, and reproducibility;
- Windows 11 native operation unless a mission explicitly requires another environment;
- PowerShell automation for Windows setup and control;
- WSL instructions separated and explicitly labelled only where Linux is genuinely required;
- no Docker.

## 15. Promotion order

These requirements shall be promoted in dependency order rather than as one broad implementation:

1. Strengthen current mission, capability, evidence, and verification contracts.
2. Define bootstrap, service-health, process-supervision, and recovery contracts.
3. Implement a minimal Windows-native bootstrap supervisor for existing services.
4. Establish durable engineering-memory record types and provenance.
5. Establish skill-package validation, quarantine, and promotion.
6. Expand deterministic tool registration and evidence capture.
7. Add independent quality gates and model-council adjudication.
8. Introduce graph-grounded operational memory in observation-only mode.
9. Add governed reconnaissance and candidate issue creation.
10. Migrate selected orchestration responsibilities into a persistent runtime kernel.
11. Add the Tauri 2 engineering command surface after backend contracts stabilize.
12. Expand toward the full engineering operating platform only after repeated missions demonstrate need and reliability.

## 16. Acceptance criteria for this documentation increment

This addendum is successfully integrated when:

- it exists as a versioned repository document;
- the development track references it as a deferred, mission-gated requirement set;
- it does not silently authorize implementation or contradict existing constitutional rules;
- it preserves Windows-first, Rust-first, mistral.rs, llama.cpp fallback, CUDA/Vulkan/WebGPU, Tauri 2, deterministic-first, and no-Docker constraints;
- future missions can trace implementation proposals back to individual requirement sections;
- 10th-Man review can challenge each promoted increment independently.
