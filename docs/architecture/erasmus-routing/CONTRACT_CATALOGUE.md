# Adaptive Routing Contract Catalogue

- **Status:** Target contract set; experimental and non-authoritative
- **Runtime registration:** None
- **Promotion requirement:** Separate bounded mission, versioned contract review, tests, migration and rollback

The existing Erasmus mission, capability, tool, evidence, governance, runtime, sleep, immune, and skill-promotion contracts remain canonical. The names below describe the intended future boundary; they do not replace or mutate current repository contracts.

## Target contract families

1. `TaskRequest`
2. `TaskSignature`
3. `CapabilityRequirement`
4. `ResourceProfile`
5. `AdaptationProfile`
6. `EnvironmentState`
7. `PolicyDecision`
8. `CandidateRoute`
9. `ExecutionStage`
10. `StageHandoff`
11. `ToolInvocation`
12. `ToolResult`
13. `ValidationResult`
14. `RouteObservation`
15. `ResolutionCase`
16. `DiagnosticBranch`
17. `Lesson`
18. `OptimizationMotif`
19. `CompetencyProjection`
20. `AuditEvent`

When promoted, contracts shall be:

- versioned and namespaced;
- serializable through the implementation language's typed data model;
- JSON-Schema exportable where the boundary is JSON;
- backward-compatibility tested or introduced through an explicit migration;
- immutable once emitted where provenance matters;
- referenced by stable identifiers rather than copied where possible;
- subordinate to authority, provenance, quarantine and rollback rules in the existing immutable contract.

## Experimental schema seeds in this change

- `task_signature.schema.json`
- `resource_profile.schema.json`
- `route_observation.schema.json`
- `resolution_case.schema.json`
- `lesson.schema.json`

These files are design fixtures only. They are deliberately permissive, are not imported by the runtime, and must not be treated as production validation contracts.

## Target error taxonomy

Minimum typed errors:

- `policy_violation`;
- `no_eligible_resource`;
- `runtime_unavailable`;
- `rate_limited`;
- `context_overflow`;
- `adapter_incompatible`;
- `unsupported_architecture`;
- `unsupported_backend`;
- `malformed_output`;
- `tool_failure`;
- `validation_failure`;
- `decomposition_failure`;
- `unresolved_classification`;
- `graph_corruption`;
- `lesson_conflict`;
- `stale_route_knowledge`.

Typed errors become authoritative only when defined by a promoted implementation contract.
