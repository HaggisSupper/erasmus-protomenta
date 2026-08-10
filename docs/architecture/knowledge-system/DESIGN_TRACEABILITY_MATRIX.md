# Phase 3 Design Traceability Matrix

- **Version:** 1.0.0
- **Status:** Static contract-coverage audit
- **Purpose:** Map declared Phase 3 design concerns to their normative document, contract, implementation increment, and still-required verification evidence

A row marked **Defined** means the target behavior and boundary are specified. It does not mean the runtime increment is implemented or authorized.

Static design validation is not runtime evidence for crash safety, concurrency, recovery, filesystem durability, or cross-platform behavior.

| Design concern | Authoritative definition | Contract/schema | Roadmap increment | Required verification | Status |
|---|---|---|---|---|---|
| Phase boundary from Foundry | [`../okf-knowledge-foundry.md`](../okf-knowledge-foundry.md), [`ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md`](ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md) | Candidate/source contracts | P3.2 | Candidate cannot mutate ledger/current-channel selection | **Defined** |
| Source bytes and immutable identity | [`STORAGE_PROJECTION_AND_RETRIEVAL.md`](STORAGE_PROJECTION_AND_RETRIEVAL.md) | `SourceArtifact`, `SourceSpan`, `ExtractionReceipt`; `knowledge-system.schema.json` | P3.1 | Digest, root confinement, extraction reproduction | **Defined** |
| OCR/textless pages | [`SECURITY_PRIVACY_AND_GOVERNANCE.md`](SECURITY_PRIVACY_AND_GOVERNANCE.md) | Separate extractor/receipt profile | P3.1 or later source mission | OCR provenance, budgets, no silent substitution | **Defined** |
| Candidate quarantine and admission | [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) | `CandidateConcept`, `CandidateClaim` | P3.2–P3.3 | Exhaustive disposition transitions | **Defined** |
| Atomic claim decomposition | [`CONTRACT_CATALOGUE.md`](CONTRACT_CATALOGUE.md) | `CandidateClaim` | P3.3 | Claim atomicity, qualifiers, span links | **Defined** |
| Stable subject/entity identity | [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) | `EntityRecord`, `EntityAlias`, `IdentityResolutionDecision`; `governance-registry.schema.json` | P3.3A | Alias/merge/split/conflict fixtures | **Defined** |
| Candidate comparison recall | [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) | `ComparisonTarget` | P3.4 | Exact duplicate recall, scope safety, latency | **Defined** |
| Reconciliation semantics | [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) | `ReconciliationProposal`, `ReconciliationDecision` | P3.5–P3.6 | Decision-table fixtures and insufficient-evidence behavior | **Defined** |
| Evidence independence | [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) | Source lineage on decisions | P3.5–P3.6 | Copies/shared-upstream do not corroborate | **Defined** |
| Claim truth authority | [`ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md`](ERASMUS_PHASE_3_KNOWLEDGE_SYSTEM_SPEC.md), ADR | `LedgerClaimBinding` | P3.6 | Existing ledger transitions remain sole authority | **Defined** |
| Contradiction preservation | [`KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md`](KNOWLEDGE_LIFECYCLE_AND_RECONCILIATION.md) | Contradiction-set record | P3.6–P3.8 | Both sides retained and retrieval-visible | **Defined** |
| Supersession and correction | Lifecycle specification, storage specification | Ledger supersession + concept revisions | P3.6–P3.9 | Acyclic chains, history, aliases, rollback | **Defined** |
| Concept identity and revisions | [`CONTRACT_CATALOGUE.md`](CONTRACT_CATALOGUE.md) | `KnowledgeConcept`, `ConceptRevision` | P3.7 | Rename stability, optimistic revision conflicts | **Defined** |
| Semantic relationship behavior | [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) | `RelationshipTypeDefinition`, semantic registry | P3.0A/P3.7 | Type, inverse, transitivity, cycle, cardinality tests | **Defined** |
| Policy authority and precedence | [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) | `KnowledgePolicySet`, `PolicyEvaluationReceipt`; governance schema | P3.0A | Deny precedence, no broadening, deterministic receipt | **Defined** |
| Risk-based review | Architecture, lifecycle, security specifications | `ReviewRecord`, `PromotionDecision` | P3.8 | Producer/reviewer independence, human/10th-Man gates | **Defined** |
| Internal lifecycle vocabulary | [`STATE_MODEL.md`](STATE_MODEL.md) | Schema enums | P3.0 and every increment | No status-plane conflation | **Defined** |
| Channel-relative publication | State, lifecycle, storage, and temporal specifications | Channel ID + receipted snapshot membership | P3.9–P3.10 | Same revision current-private/unpublished-public without lifecycle mutation | **Defined** |
| Open questions and hypotheses | [`OPEN_QUESTIONS_AND_SYNTHESIS.md`](OPEN_QUESTIONS_AND_SYNTHESIS.md) | `OpenQuestion`, `QuestionTransition`; question schema | P3.8A | Closure criteria, child questions, ledger hypotheses | **Defined** |
| Grounded synthesis | [`OPEN_QUESTIONS_AND_SYNTHESIS.md`](OPEN_QUESTIONS_AND_SYNTHESIS.md) | `SynthesisRecord`, `SynthesisTransition` | P3.8A | Every material statement maps to claims; bridge claims quarantined | **Defined** |
| Canonical OKF representation | Architecture and storage specifications | `ConceptRevision`, rendering profile | P3.9 | OKF v0.2, sources, generated/verified, unknown field preservation | **Defined** |
| Source of truth | [`ADR-KNOWLEDGE-001`](../../adr/ADR-KNOWLEDGE-001-authoritative-state-and-okf-publication.md) | Operational records + immutable snapshots | All | Projection deletion cannot lose knowledge | **Defined** |
| Crash-consistent publication | [`STORAGE_PROJECTION_AND_RETRIEVAL.md`](STORAGE_PROJECTION_AND_RETRIEVAL.md) | `PublicationIntent`, conditional `PublicationReceipt`, `CanonicalSnapshot`, success-only `ChannelSelectionEvent` | P3.9 | Pre-artifact terminal failures, generation-free expected pointer payload, bootstrap generation 0, receipt-before-pointer, rollback/reselection without duplicate artifacts, all failpoints and recovery | **Defined** |
| Global historical order | Storage and temporal specifications | `knowledge_events.event_seq` | Every authoritative increment | Total committed event order; no timestamp tie-break | **Defined** |
| Minimum serving suspension | [`UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md`](UNCERTAINTY_IMPACT_AND_SERVING_CONTROLS.md) | `InvalidationEvent`, `ServingDirective` | P3.8B before P3.9/P3.10 | Apply/supersede/suspend before pointer/cache/context | **Defined** |
| Multiple audience/scope publications | [`POLICY_IDENTITY_AND_REGISTRIES.md`](POLICY_IDENTITY_AND_REGISTRIES.md) | `PublicationChannel` | P3.0A/P3.9 | Independent per-channel pointer and rollback | **Defined** |
| Human-authored OKF changes | Architecture/ADR | Source registration -> candidate import | P3.2–P3.9 | Direct current-snapshot edit rejected/imported as candidate | **Defined** |
| Lexical retrieval | [`STORAGE_PROJECTION_AND_RETRIEVAL.md`](STORAGE_PROJECTION_AND_RETRIEVAL.md) | `ProjectionManifest`, `RetrievalRequest` | P3.10 | Exact/rare identifiers, scope filters, rebuild | **Defined** |
| Vector retrieval | Storage/retrieval specification | Projection profile + manifest | P3.11 | Model/config identity, no truth decisions, quality delta | **Defined** |
| Graph projection/world model | Storage/retrieval specification | Relationships + graph projection profile | P3.11 | Scope per hop, fan-out, cycle, derived-edge labels | **Defined** |
| Evidence packets/context boundary | Storage/retrieval and operator specifications | Event-ordered immutable `EvidencePacket` receipt, request/response envelope | P3.10 | Exact receipt/pointer/directive/as-known boundary plus source/truth/lifecycle/freshness/contradiction retained | **Defined** |
| Freshness and revalidation | Architecture, storage, lifecycle specifications | `FreshnessAssessment`, `RevalidationRequest` | P3.12 | Stale != false; source-change candidate diff | **Defined** |
| Continuous intake/backpressure | Roadmap and operator runbook | `KnowledgeJob`, outbox | P3.13 | Queue budgets, pause, resume, flood control | **Defined** |
| Adaptive routing integration | Phase 3 roadmap and routing package | Read-only evidence packet seam | P3.14 | Routing cannot mutate knowledge or gain authority | **Defined** |
| Prompt injection | [`SECURITY_PRIVACY_AND_GOVERNANCE.md`](SECURITY_PRIVACY_AND_GOVERNANCE.md) | Strict semantic outputs | Every semantic increment | Hostile source remains data; no side effect | **Defined** |
| Corpus/RAG poisoning | Security specification | Lineage, trust signals, findings | P3.2 onward | Copies do not corroborate; anomaly fixtures | **Defined** |
| Parser and filesystem safety | Security specification | Extraction receipt/root policy | P3.1 | Resource caps, path/junction/alias tests | **Defined** |
| Privacy, scope, and redaction | Security/policy/storage specifications | Scope, channel, tombstone/redaction receipts | Every increment | Zero cross-scope leakage; removal propagation | **Defined** |
| Secrets and supply chain | Security specification | Exact tool/runtime/model identities | Every executing increment | Secret publication block; no ambient PATH trust | **Defined** |
| Long-running execution | [`OPERATOR_API_AND_RUNBOOK.md`](OPERATOR_API_AND_RUNBOOK.md) | `KnowledgeJob`, progress event; operator schema | Each applicable increment | Resume/cancel/retry/idempotency/lease fixtures | **Defined** |
| CLI/API contracts | Operator runbook | Request/response envelopes | Each increment | Stable JSON, exit codes, dry-run, version negotiation | **Defined** |
| Tauri/MCP boundaries | Operator runbook/security | Transport adapters over same service | After backend stabilization | No direct DB or authority bypass | **Defined** |
| Backup, restore, and recovery | Storage/operator/test specifications | Backup/publication/recovery receipts | P3.1 onward | Isolated restore, projection rebuild, pointer recovery | **Defined** |
| Observability and audit | Main spec/operator/security | `KnowledgeAuditEvent`, JSONL logs | Every increment | Exact IDs/versions/evidence, no secrets/CoT | **Defined** |
| Contract versioning and compatibility | Contract catalogue/policy registry | Versioned schemas/profiles | P3.0A onward | Unsupported majors fail closed; old semantics preserved | **Defined** |
| Performance/resource bounds | Test plan/operator/storage | Per-request budgets and manifests | Every increment | Declared reference-hardware metrics and safe caps | **Defined** |
| Windows-first operation | Operator runbook, security, roadmap | PowerShell commands and path policy | Every increment | Windows CI and local verification | **Defined** |
| Rust migration seam | Main spec/contract catalogue | Language-neutral canonical JSON contracts | Only measured hot paths | Rust/Python contract parity and rollback | **Defined** |
| Tauri deployment seam | Main spec/operator runbook | Service/IPC contracts | Post-backend stabilization | UI disposable; headless complete | **Defined** |
| No Docker | Main spec, roadmap, runbook | N/A | All | No container dependency in setup or CI | **Defined** |
| Complete acceptance evidence | [`TEST_AND_ACCEPTANCE_PLAN.md`](TEST_AND_ACCEPTANCE_PLAN.md) | Validation reports and receipts | Every increment | Full CI, recovery, review, rollback, 10th-Man | **Defined** |

## Residual uncertainties deliberately deferred

These are deferred implementation choices bounded by the contracts above; their runtime fitness remains unproved:

- exact embedded vector-store crate/library;
- exact graph projection storage representation;
- whether a measured hot path moves from Python to Rust;
- the local embedding model selected for a specific corpus/hardware target;
- the first domain-specific entity/predicate/relationship registry contents;
- exact corpus-scale performance thresholds after representative data exists;
- whether signed cross-device exchange is required;
- Tauri UI composition after headless contracts are implemented.

Each choice requires a future bounded mission and cannot change the authoritative-state, authority, evidence, lifecycle, publication, or rollback decisions in this package without a new ADR.

## Runtime evidence still required

The package provides deterministic static checks for declared documents, schema structure, dependency ordering, and selected cross-document invariants. It does not execute the future database migrations, filesystem publication protocol, directive evaluator, retrieval broker, concurrency controls, crash recovery, or Windows durability behavior.

The implementation remains intentionally unstarted except for the bounded Foundry seam in PR #68.
