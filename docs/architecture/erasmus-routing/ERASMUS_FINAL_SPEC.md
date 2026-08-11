# Erasmus Adaptive Problem Routing and Resolution System

- **Version:** 1.0.0
- **Status:** Accepted target architecture; deferred implementation
- **Repository authority:** Documentation-only until promoted by a bounded mission
- **Design posture:** Provider-neutral, runtime-neutral, domain-general; Rust-first for separately authorized native components
- **Preferred future reference stack:** Windows-first, Tauri 2, mistral.rs primary, llama.cpp fallback, CUDA acceleration with Vulkan/WebGPU fallback, no Docker


## 0. Repository integration boundary

This document defines the target architecture for a future Erasmus routing and problem-resolution control plane. Landing it in the repository does **not** activate, authorize, or imply implementation of the described subsystems.

Until a later bounded mission explicitly promotes a component:

- the existing one-process, one-SQLite Erasmus kernel remains authoritative;
- the current Python implementation and its public contracts remain in force;
- existing mission, capability, tool, evidence, governance, runtime, sleep, immune, and skill-promotion paths remain unchanged;
- the namespaced schemas accompanying this document are experimental design seeds and are not registered with the live runtime;
- no model, provider, adapter, graph, reinforcement, training, UI, or hardware change is authorized;
- every promoted increment requires its own acceptance criteria, deterministic tests, negative tests, rollback, observation-only mode where applicable, and 10th-Man review.

The implementation sequence is governed by [`ERASMUS_IMPLEMENTATION_ROADMAP.md`](../../roadmap/ERASMUS_IMPLEMENTATION_ROADMAP.md#track-c-adaptive-routing-evolution) and [`ADR-ROUTING-001`](../../adr/ADR-ROUTING-001-adaptive-routing-as-deferred-extension.md). Existing repository governance takes precedence wherever this target specification is less restrictive.

## 1. Executive definition

Erasmus is an adaptive inference control plane and experience-guided problem resolution system. It does not treat one model as the universal engine for an entire task. It decomposes work into bounded stages, classifies the problem, retrieves similar cases and optimization motifs, selects the best available combination of models, adapters, deterministic tools, runtimes and hardware, validates the result, records failed and successful forks, and updates a persistent reinforcement map.

The unit of orchestration is the **capability-bound execution stage**, not the model session.

The effective resource for a call is:

```text
Architecture
+ Base model
+ Quantization
+ Runtime
+ Hardware backend
+ Per-call adaptation profile
+ Tool access
+ Context strategy
+ Inference state
```

## 2. Goals

Erasmus shall:

1. Route each stage to the smallest sufficient, validated capability package.
2. Prefer deterministic computation and validation over unsupported inference.
3. Support local, hosted and hybrid execution without provider lock-in.
4. Support transformer, Mamba/state-space, hybrid and future architectures.
5. Support per-call LoRA, multi-LoRA, X-LoRA or equivalent adaptation where available.
6. Maintain a compact in-memory routing knowledge graph consulted on every call.
7. Learn conditional route value from validated outcomes, not model self-assertion.
8. Preserve failed diagnostic forks as conditionally useful knowledge.
9. Consolidate reusable lessons at case, domain and meta-optimization levels.
10. Expose a derived, evidence-backed answer to “what is Erasmus good at?”
11. Remain auditable, reversible, versioned and bounded by explicit policy.

## 3. Non-goals

Erasmus does not require:

- a specific provider or model family;
- a transformer-only architecture;
- a remote graph database on the hot path;
- hidden chain-of-thought storage;
- deep reinforcement learning for the first implementation;
- cloud-first deployment;
- Docker or containerized runtime assumptions;
- direct ports of analogous systems merely because they are referenced as “akin to” a desired capability.

Analogies shall be interpreted abstractly: extract the useful principle and adapt it to Erasmus.

## 4. Core architecture

```text
User intent
    -> Intent and constraint normalizer
    -> Compact routing cognition kernel
    -> Problem signature
    -> Lessons and resolution-case retrieval
    -> Routing knowledge graph
    -> Routing RL map / state-vector route field
    -> Policy and hard-constraint filter
    -> Candidate execution DAG
    -> Model/tool/runtime/adaptation selection
    -> Stage execution
    -> Deterministic validation
    -> Independent review where required
    -> Reward and credit assignment
    -> Problem-resolution trace update
    -> Lessons consolidation
    -> Durable telemetry and competency projection
```

## 5. Routing cognition kernel

A compact locally executable classifier shall convert raw requests into calibrated routing metadata. It shall not generate final answers and shall not bind directly to named models.

Minimum outputs:

- primary and secondary task classes;
- domain and subtype;
- complexity and risk;
- modality;
- context scale;
- required capabilities;
- deterministic-tool applicability;
- likely execution pattern;
- confidence and entropy;
- adaptation benefit prediction.

Deterministic request features outrank classifier output when explicit evidence exists.

## 6. Provider-neutral resource model

Every resource shall register through a normalized adapter and expose:

- identity and version;
- architecture family;
- capabilities with evidence-backed scores;
- context limits;
- supported modalities;
- structured-output and tool-use support;
- quantization options;
- adaptation support;
- runtime and hardware compatibility;
- latency, cost and reliability statistics;
- current health and rate-limit state.

Policies shall express capability requirements, not vendor names.

## 7. Per-call adaptation

Every inference call may request an adaptation profile. Supported mechanisms include:

- single LoRA;
- static weighted multi-LoRA;
- sequential adapters;
- materialized adapter merge;
- X-LoRA or equivalent dynamic mixture-of-adapters;
- prompt or prefix adapters;
- task vectors and future compatible methods.

Adapter selection shall occur after base-model, architecture, runtime and hardware eligibility are established. Adapter state shall not leak between calls unless explicitly permitted.

“Supported hardware” means hardware that can execute the vanilla model. Adapter features are additional optimizations and may be native, emulated, materialized or unavailable without invalidating base-model support.

## 8. Architecture-neutral inference

The control plane shall treat dense transformers, mixture-of-experts, Mamba/state-space, recurrent, hybrid attention/state-space, convolutional sequence and future architectures as peers.

Generic inference-state operations shall abstract over KV cache, recurrent state or other state forms:

```text
create_inference_state()
clone_inference_state()
reset_inference_state()
serialize_inference_state()
restore_inference_state()
estimate_state_memory()
```

## 9. Deterministic-first execution

Before invoking generative inference, Erasmus shall determine whether the operation can be authoritatively performed by a compiler, parser, test runner, static analyzer, solver, database query, schema validator, numerical library, image-processing pipeline or other deterministic tool.

Validated deterministic paths receive stronger reinforcement than unsupported model inference.

For coding, examples include:

- cargo fmt;
- cargo check;
- cargo test;
- clippy;
- rustdoc;
- criterion benchmarks;
- dependency/security audit;
- Tauri build/package verification;
- runtime health probes.

## 10. In-memory routing knowledge graph

Erasmus shall maintain a small, low-latency operational knowledge graph in cache and consult it for every routing decision.

Node classes include:

- task class and task signature;
- capability;
- execution stage;
- model and architecture;
- adapter and adaptation profile;
- runtime and hardware backend;
- deterministic tool;
- context strategy;
- route and route segment;
- outcome and failure mode;
- policy and constraint;
- reward profile;
- environment state;
- lesson and optimization motif;
- hypothesis, test, evidence and resolution.

The hot graph stores current state and compressed statistics. Raw traces remain in durable telemetry.

## 11. Routing RL map and state-vector graph

The Routing RL Map is the learned action-value layer attached to graph nodes, edges and paths. It shall bootstrap with interpretable methods such as contextual bandits, Bayesian estimates or graph-weighted policies.

Each edge or route segment may carry a state vector rather than one scalar weight. Suggested dimensions:

- direction in problem/solution space;
- magnitude or expected value;
- confidence;
- evidence strength;
- expected information gain;
- transferability;
- recency;
- drift;
- cost;
- latency;
- deterministic authority;
- validation quality;
- risk.

This is abstractly akin to angle-and-magnitude representations: the principle is adopted, not the referenced implementation.

Multiple active problem similarities may be superposed to produce a resultant route direction. A disproven branch can rotate or reduce in magnitude without being globally deleted.

## 12. Route optimization

Candidate routes shall be scored under hard constraints and multi-objective utility. A conceptual utility function is:

```text
utility =
    capability_fit
  * architecture_task_fit
  * adaptation_gain
  * reliability
  * context_fit
  * policy_compliance
  * historical_combination_success
  * validation_strength
  - cost
  - latency
  - memory pressure
  - rate-limit risk
  - context-transfer loss
  - repair burden
```

For diagnosis, branch priority shall also include expected information gain:

```text
branch_priority =
    causal_probability
  * expected_information_gain
  * expected_resolution_value
  / execution_cost_and_risk
```

## 13. Problem-resolution memory

Each issue shall produce a persistent resolution-case graph containing:

- normalized problem signature;
- initial observations;
- hypotheses;
- attempted diagnostic branches;
- tools and tests;
- evidence;
- branch status;
- rollback points;
- alternate forks;
- confirmed cause;
- applied resolution;
- validation evidence.

Branch statuses:

- confirmed_cause;
- contributing_cause;
- disproven_here;
- inconclusive;
- blocked;
- invalid_hypothesis;
- obsolete;
- successful_resolution.

`disproven_here` is not a global negative. It preserves a valid diagnostic fork and records the evidence that excludes it in this case.

## 14. Lessons-learned knowledge layer

Erasmus shall derive reusable lessons from validated workflows. A lesson records:

- problem classification and applicability;
- proven or failed path;
- deterministic tools and code used;
- inference and multimodal resources;
- validation sequence;
- response quality;
- confidence;
- exclusion conditions;
- supporting observations;
- supersession and drift state.

Lesson levels:

1. **Case lesson** - specific issue and environment.
2. **Domain lesson** - reusable within a domain.
3. **Project lesson** - constrained to one repository or product.
4. **Meta lesson** - domain-general problem-solving principle.
5. **Optimization motif** - reusable search, diagnostic or validation topology.

Lessons move through candidate, observed, corroborated, validated, enforced and deprecated states.

## 15. Optimization motifs

The system shall reason over structurally similar optimization patterns even when domains differ.

Examples:

- diagnostic narrowing;
- divide and conquer;
- constraint propagation;
- retrieve then verify;
- generate-test-repair;
- coarse-to-fine search;
- rollback and alternate fork;
- independent adjudication;
- deterministic reduction;
- uncertainty-driven exploration.

A novel problem may have no close historical case but still match a known optimization motif.

## 16. Competency projection

“What is Erasmus good at?” shall be a read-only derived projection over:

- Routing KG;
- RL state values;
- lessons;
- validation telemetry;
- tool dependence;
- environment conditions;
- uncertainty and evidence volume.

Competency shall be conditional, not a single vague score. Example:

```text
Rust compile-error repair
under reproducible compiler diagnostics
with repository context and cargo validation
success probability: 0.96
confidence: high
```

No independent authoritative competency database shall exist.

## 17. Feedback and reward

Reward shall incorporate:

- validated correctness;
- acceptance-criteria completion;
- first-pass success;
- evidence strength;
- correct tool use;
- user acceptance;
- artifact quality;
- latency and cost;
- repair cycles;
- escaped defects;
- policy violations;
- human intervention.

Positive, negative, conditional and uncertain signals must all be represented.

A successful route is not assumed optimal. Credit assignment shall use segment rewards, ablation/shadow evaluation, recovery attribution and counterfactual estimates where feasible.

## 18. Exploration and safety

Controlled exploration is permitted where evidence is sparse or resources change. Exploration is prohibited for destructive, irreversible, credential-sensitive or safety-critical actions unless explicitly authorized.

High-risk routes shall prefer independent review and stronger deterministic validation.

## 19. Context transfer

Cross-resource handoff shall use structured packets containing only the stage objective, contracts, relevant evidence, prior attempts, unresolved issues and acceptance criteria. Unbounded transcript transfer is prohibited as the sole state mechanism.

## 20. Coding-domain example using preferred stack

For a Windows-first Tauri 2 application with a Rust backend and mistral.rs primary runtime, Erasmus may route as follows:

1. Compact classifier identifies Rust/Tauri/local-inference/GPU constraints.
2. Lessons retrieve prior crate-boundary, sidecar, packaging and Windows process-start patterns.
3. High-reasoning capability defines architecture and immutable contracts.
4. Rust-specialized model or adapter implements bounded crates.
5. mistral.rs runs local inference; llama.cpp is an eligible fallback.
6. CUDA is selected when compatible; Vulkan/WebGPU remain fallbacks.
7. cargo fmt/check/test/clippy and Tauri packaging are mandatory deterministic stages.
8. Failed forks are recorded with `disproven_here` conditions.
9. Independent review checks unsafe code, IPC boundaries, packaging and policy compliance.
10. Validated outcome updates route vectors, lessons and competency projection.

## 21. Security and governance

Protected control-plane data includes:

- routing policy;
- resource and adapter capability scores;
- user constraints;
- lessons promotion state;
- reward weights;
- audit records.

Models may propose changes but cannot directly mutate protected control-plane state.

Adapters and models are untrusted artifacts until checksummed, provenance-tracked and regression-tested.

## 22. Observability

Every routing decision shall record:

- task and environment signature;
- matched lessons;
- candidate routes;
- selected route and rationale;
- active model/runtime/hardware/adapters;
- tools invoked;
- validation evidence;
- branch transitions;
- reward and credit assignment;
- graph and lesson updates.

Sensitive prompt content shall not be logged unless policy permits.

## 23. Implementation boundary

When promoted, the hot routing path shall be embedded in or colocated with the authoritative Erasmus control plane and shall not depend on a remote graph or routing service.

The current Python kernel is not deprecated by this specification. A Rust component may be introduced only through a separately authorized mission, a narrow versioned contract, measured benefit, deterministic fallback, and a reversible migration. No whole-kernel rewrite is implied.

Preferred future component posture:

- Rust crates for performance-critical contracts, graph cache, routing, policies, bandit/state-vector scoring, lessons, resolution cases, adapters, telemetry, and runtime integration where measurements justify native code;
- the existing Python kernel retained as authority until a versioned migration is independently proven;
- Python permitted for offline training, data preparation, evaluation, and existing governed kernel behavior;
- Tauri 2 only after backend control-plane contracts stabilize, and never as the control-plane authority;
- mistral.rs as the primary local inference runtime, with llama.cpp or another contract-compatible runtime as fallback;
- CUDA acceleration where compatible, with Vulkan/WebGPU or optimized CPU fallback;
- no Docker.

## 24. Definition of done

Documentation landing completes only Track B0. The target architecture itself is not implemented until a sequence of separately authorized missions can demonstrate:

1. Typed task decomposition and capability routing.
2. Provider-neutral resource discovery.
3. Per-call adaptation selection.
4. Transformer and Mamba/state-space support.
5. Deterministic-first tooling.
6. In-memory KG lookup on every call.
7. RL/state-vector path scoring with uncertainty.
8. Conditional preservation of failed forks.
9. Problem-resolution trace and rollback.
10. Lessons extraction, promotion and enforcement.
11. Optimization-motif transfer across domains.
12. Derived competency projection.
13. Controlled exploration.
14. Versioned policy, audit and rollback.
15. A working Windows-first Rust/Tauri reference implementation using mistral.rs, with llama.cpp fallback and CUDA/Vulkan/WebGPU backend negotiation.
