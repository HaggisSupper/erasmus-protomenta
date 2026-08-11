"""Deterministic contract package validator for bootstrap control-plane planning."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contracts" / "bootstrap"
SCHEMA_FILES: tuple[str, ...] = (
    "component-spec.schema.json",
    "bootstrap-plan.schema.json",
    "service-observation.schema.json",
    "recovery-decision.schema.json",
    "bootstrap-result.schema.json",
)

KNOWN_STATES = ("discovery", "starting", "running", "stopping", "stopped", "exited", "orphaned")
KNOWN_HEALTH_STATES = ("unknown", "healthy", "degraded", "unhealthy", "blocked", "not_applicable")
KNOWN_READINESS_STATES = ("not_ready", "ready", "degraded_ready", "blocked")
KNOWN_TRANSITIONS = {
    ("discovery", "starting"),
    ("starting", "running"),
    ("running", "stopping"),
    ("running", "exited"),
    ("stopped", "starting"),
    ("stopping", "stopped"),
    ("stopping", "exited"),
    ("stopped", "orphaned"),
}
KNOWN_RECOVERY_ACTIONS = frozenset(
    {
        "retry_within_budget",
        "restart_owned_process",
        "stop_owned_process",
        "resume_interrupted_mission",
        "remove_stale_lock",
        "rollback_required",
        "human_approval_required",
        "safe_reuse",
    }
)
OWNERSHIP_GATED_ACTIONS = frozenset({"restart_owned_process", "stop_owned_process"})


@dataclass(frozen=True)
class ValidationResult:
    """Machine-readable result used by scripts and tests."""

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    derived_startup_order: tuple[str, ...]
    derived_shutdown_order: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "derived_startup_order": list(self.derived_startup_order),
            "derived_shutdown_order": list(self.derived_shutdown_order),
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_json_schema(schema: dict[str, Any], payload: Any) -> list[str]:
    return sorted(
        f"schema:{'/'.join(map(str, error.path)) or '/'}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(payload)
    )


def _validate_known_schema(schema_file: str) -> tuple[dict[str, Any], list[str]]:
    path = SCHEMA_DIR / schema_file
    schema: dict[str, Any]
    try:
        schema = _load_json(path)
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        return {}, [f"schema:{schema_file}: {exc}"]
    validator_errs = []
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # pragma: no cover - defensive
        validator_errs.append(f"schema:{schema_file}: {exc}")
    return schema, validator_errs


def _load_all_schemas() -> tuple[dict[str, dict[str, Any]], list[str]]:
    schemas: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for schema_file in SCHEMA_FILES:
        schema, schema_errors = _validate_known_schema(schema_file)
        if schema:
            schemas[schema_file] = schema
        errors.extend(schema_errors)
    return schemas, errors


def _topological_order(nodes: Iterable[str], edges: dict[str, set[str]]) -> list[str]:
    node_list = list(dict.fromkeys(nodes))
    order_index = {node: index for index, node in enumerate(node_list)}

    remaining_incoming: dict[str, set[str]] = {node: set() for node in node_list}
    dependents: dict[str, set[str]] = {node: set() for node in node_list}

    for source, dependencies in edges.items():
        remaining_incoming.setdefault(source, set())
        for dependency in dependencies:
            remaining_incoming[source].add(dependency)
            dependents.setdefault(dependency, set()).add(source)

    for node in list(dependents.keys()):
        remaining_incoming.setdefault(node, set())

    resolved: list[str] = []
    ready = [node for node, dependencies in remaining_incoming.items() if not dependencies]
    ready.sort(key=order_index.get)

    while ready:
        node = ready.pop(0)
        resolved.append(node)
        for dependent in sorted(dependents.get(node, set()), key=order_index.get):
            remaining_incoming[dependent].discard(node)
            if not remaining_incoming[dependent] and dependent not in resolved and dependent not in ready:
                ready.append(dependent)
        ready.sort(key=order_index.get)
    if len(resolved) != len(remaining_incoming):
        return []
    return resolved


def _component_id_map(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {component["component_id"]: component for component in components}


def _validate_plan_schema_and_components(
    schemas: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    plan_schema = schemas.get("bootstrap-plan.schema.json")
    if not plan_schema:
        return ["schema:bootstrap-plan.schema.json: missing or invalid"]

    errors.extend(_validate_json_schema(plan_schema, plan_payload.get("plan")))

    components = plan_payload.get("components")
    if not isinstance(components, list):
        return errors

    component_schema = schemas.get("component-spec.schema.json")
    if not component_schema:
        errors.append("schema:component-spec.schema.json: missing or invalid")
        return errors
    for component in components:
        if not isinstance(component, dict):
            errors.append("components: each component must be an object")
            continue
        errors.extend(_validate_json_schema(component_schema, component))

    return sorted(set(errors))


def _validate_service_observations(
    schemas: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
    known_component_ids: set[str],
) -> list[str]:
    observations = plan_payload.get("service_observations")
    if observations is None:
        return ["service_observations: required for contract determinism"]
    if not isinstance(observations, list) or not observations:
        return ["service_observations: must be a non-empty array"]
    schema = schemas.get("service-observation.schema.json")
    if not schema:
        return ["schema:service-observation.schema.json: missing or invalid"]

    errors: list[str] = []
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"service_observations[{index}]: must be an object")
            continue
        errors.extend(_validate_json_schema(schema, item))
        component_id = item.get("component_id")
        if component_id not in known_component_ids:
            errors.append(f"service_observations[{index}].component_id: unknown component {component_id}")
        if not item.get("probe_capability") and item.get("observation_type") in {"health", "readiness"}:
            errors.append(
                f"service_observations[{index}].probe_capability: required for health/readiness observation"
            )
        if item.get("observation_type") == "health" and not item.get("health_evidence"):
            errors.append(f"service_observations[{index}].health_evidence: required for health observation")
        ownership = item.get("ownership")
        if not isinstance(ownership, dict):
            continue
        required_ownership_fields = {"status", "proof", "source"}
        missing = sorted(required_ownership_fields - set(ownership.keys()))
        if missing:
            errors.append(
                f"service_observations[{index}].ownership: missing required fields {missing}"
            )
    return sorted(set(errors))


def _validate_recovery_decisions(
    schemas: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
    known_component_ids: set[str],
) -> list[str]:
    decisions = plan_payload.get("recovery_decisions")
    if not isinstance(decisions, list):
        return ["recovery_decisions: must be an array"]
    schema = schemas.get("recovery-decision.schema.json")
    if not schema:
        return ["schema:recovery-decision.schema.json: missing or invalid"]
    errors: list[str] = []
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f"recovery_decisions[{index}]: must be an object")
            continue
        errors.extend(_validate_json_schema(schema, decision))
        actions = decision.get("permitted_actions", [])
        if any(action in OWNERSHIP_GATED_ACTIONS for action in actions):
            ownership = decision.get("ownership", {}).get("status")
            if ownership != "owned":
                errors.append(
                    f"recovery_decisions[{index}]: restart/stop is only allowed for owned process evidence"
                )
        for action in actions:
            if action not in KNOWN_RECOVERY_ACTIONS:
                errors.append(f"recovery_decisions[{index}].permitted_actions: unknown action {action}")
        for component_id in decision.get("required_component_ids", []):
            if component_id not in known_component_ids:
                errors.append(f"recovery_decisions[{index}].required_component_ids: unknown component {component_id}")
        if decision.get("classification") == "blocked" and not decision.get("blocked_reason"):
            errors.append(f"recovery_decisions[{index}].blocked_reason: required for blocked")
    return sorted(set(errors))


def _validate_bootstrap_result(
    schemas: dict[str, dict[str, Any]],
    plan_payload: dict[str, Any],
    known_component_ids: set[str],
    _derived_startup_order: tuple[str, ...],
) -> list[str]:
    result_payload = plan_payload.get("bootstrap_result")
    if not isinstance(result_payload, dict):
        return ["bootstrap_result: must be an object"]
    schema = schemas.get("bootstrap-result.schema.json")
    if not schema:
        return ["schema:bootstrap-result.schema.json: missing or invalid"]
    errors: list[str] = _validate_json_schema(schema, result_payload)
    transitions = result_payload.get("ordered_component_transitions", [])
    if not isinstance(transitions, list):
        errors.append("bootstrap_result.ordered_component_transitions: must be an array")
        return sorted(set(errors))

    lifecycle_seen = set()
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            errors.append(f"bootstrap_result.ordered_component_transitions[{index}]: must be an object")
            continue
        component_id = transition.get("component_id")
        source = transition.get("from_state")
        target = transition.get("to_state")
        if component_id not in known_component_ids:
            errors.append(
                f"bootstrap_result.ordered_component_transitions[{index}].component_id: unknown component {component_id}"
            )
        if source not in KNOWN_STATES or target not in KNOWN_STATES:
            errors.append(
                f"bootstrap_result.ordered_component_transitions[{index}]: unknown lifecycle state transition {source}->{target}"
            )
        elif (source, target) not in KNOWN_TRANSITIONS:
            errors.append(
                f"bootstrap_result.ordered_component_transitions[{index}]: invalid lifecycle transition {source}->{target}"
            )
        lifecycle_seen.add(transition.get("component_id"))
    if not lifecycle_seen:
        errors.append("bootstrap_result.ordered_component_transitions: transitions cannot be empty")
    final_status = result_payload.get("status")
    if final_status == "blocked":
        if not result_payload.get("stop_reason"):
            errors.append("bootstrap_result.stop_reason: required when status is blocked")
    else:
        if result_payload.get("stop_reason") not in (None, "", {}):
            errors.append("bootstrap_result.stop_reason: should be empty when status is not blocked")
    return sorted(set(errors))


def _validate_runtime_policy(plan_payload: dict[str, Any], known_component_ids: set[str]) -> list[str]:
    errors: list[str] = []
    runtime_policy = plan_payload.get("runtime_policy")
    if not isinstance(runtime_policy, dict):
        return ["plan.runtime_policy: required object"]
    primary = runtime_policy.get("primary_runtime")
    if primary not in known_component_ids:
        errors.append("plan.runtime_policy.primary_runtime: must point to declared component id")
    if primary != "mistral-rs":
        override = runtime_policy.get("authorized_fallback_override")
        if not override:
            errors.append("runtime_policy: mistral.rs must be primary runtime unless explicitly overridden")
    has_llama = "llama-cpp" in known_component_ids
    fallback = runtime_policy.get("fallback_runtime")
    if has_llama and not fallback:
        errors.append("runtime_policy: llama.cpp fallback component declared without fallback_runtime policy")
    return errors


def _validate_plan_logic(payload: dict[str, Any]) -> tuple[list[str], tuple[str, ...], tuple[str, ...]]:
    plan = payload.get("plan")
    components = payload.get("components")
    if not isinstance(plan, dict) or not isinstance(components, list):
        return ["plan: invalid payload shape"], (), ()

    try:
        component_specs = [component for component in components if isinstance(component, dict)]
    except TypeError:  # pragma: no cover - impossible with checked shape
        return ["components: must be an array"], (), ()

    component_ids = [component.get("component_id") for component in component_specs if isinstance(component.get("component_id"), str)]
    duplicates = sorted(
        [component_id for component_id in set(component_ids) if component_ids.count(component_id) > 1]
    )
    if duplicates:
        return [f"components: duplicate IDs {duplicates}"], (), ()

    component_map = _component_id_map(component_specs)
    component_ids = list(dict.fromkeys(component_ids))
    if not component_ids:
        return ["components: at least one component is required"], (), ()

    declared_ids = set(component_ids)
    required_ids = set(plan.get("required_components", []))
    optional_ids = set(plan.get("optional_components", []))
    if not (required_ids <= declared_ids):
        missing = sorted(required_ids - declared_ids)
        return [f"plan.required_components: unknown component reference {missing}"], (), ()
    if optional_ids - declared_ids:
        missing = sorted(optional_ids - declared_ids)
        return [f"plan.optional_components: unknown component reference {missing}"], (), ()

    edges: dict[str, set[str]] = {component_id: set() for component_id in component_ids}
    for component_id in component_ids:
        spec = component_map[component_id]
        for dependency in spec.get("dependencies", []):
            if dependency not in declared_ids:
                return [f"components[{component_id}].dependencies: unknown dependency {dependency}"], (), ()
            edges[component_id].add(dependency)

    startup_order = _topological_order(component_ids, edges)
    if not startup_order:
        return ["plan.dependency_graph: dependency cycle detected"], (), ()

    declared_startup_order = plan.get("startup_order")
    if declared_startup_order:
        if sorted(declared_startup_order) != sorted(startup_order):
            return [
                "plan.startup_order: component membership differs from deterministic dependency graph"
            ], (), ()
        if list(declared_startup_order) != startup_order:
            return [
                "plan.startup_order: must match deterministic dependency order (stable lexical tie-break)"
            ], (), ()

    declared_shutdown_order = plan.get("shutdown_order")
    derived_shutdown = tuple(reversed(startup_order))
    if declared_shutdown_order and list(declared_shutdown_order) != list(derived_shutdown):
        return ["plan.shutdown_order: must be deterministic reverse of startup order"], (), ()

    return [], tuple(startup_order), derived_shutdown


def validate_bootstrap_contract_payload(payload: dict[str, Any]) -> ValidationResult:
    schemas, schema_errors = _load_all_schemas()
    errors: list[str] = schema_errors[:]
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ValidationResult(False, ("payload: must be a JSON object",), tuple(), tuple())

    plan_errors, startup_order, shutdown_order = _validate_plan_logic(payload)
    errors.extend(plan_errors)

    component_map = _component_id_map(
        [component for component in payload.get("components", []) if isinstance(component, dict)]
    )
    known_components = set(component_map.keys())

    section_errors = _validate_plan_schema_and_components(schemas, payload)
    errors.extend(section_errors)
    errors.extend(_validate_service_observations(schemas, payload, known_components))
    errors.extend(_validate_recovery_decisions(schemas, payload, known_components))
    errors.extend(_validate_bootstrap_result(schemas, payload, known_components, startup_order))
    errors.extend(_validate_runtime_policy(payload.get("plan", {}), known_components))

    # Lifecycle and authority checks are intentionally separate from schema-level checks.
    for component_id, spec in component_map.items():
        transitions = spec.get("lifecycle_transitions", [])
        if not isinstance(transitions, list) or not transitions:
            errors.append(f"components[{component_id}].lifecycle_transitions: required")
            continue
        for index, transition in enumerate(transitions):
            if not isinstance(transition, dict):
                errors.append(f"components[{component_id}].lifecycle_transitions[{index}]: must be an object")
                continue
            source = transition.get("from")
            target = transition.get("to")
            if source not in KNOWN_STATES or target not in KNOWN_STATES:
                errors.append(
                    f"components[{component_id}].lifecycle_transitions[{index}]: invalid state names"
                )
                continue
            if (source, target) not in KNOWN_TRANSITIONS:
                errors.append(
                    f"components[{component_id}].lifecycle_transitions[{index}]: unsupported transition {source}->{target}"
                )
        if spec.get("readiness_state", "not_ready") not in KNOWN_READINESS_STATES:
            errors.append(f"components[{component_id}].readiness_state: unknown readiness state")
        if spec.get("health_state", "unknown") not in KNOWN_HEALTH_STATES:
            errors.append(f"components[{component_id}].health_state: unknown health state")
        if spec.get("evidence_requirements", {}).get("health_readiness_required") is not True:
            warnings.append(
                f"components[{component_id}].evidence_requirements.health_readiness_required: should be true"
            )

    ordered_unique = tuple(sorted(dict.fromkeys(startup_order).keys()))
    for index in range(len(ordered_unique) - 1):
        source = ordered_unique[index]
        target = ordered_unique[index + 1]
        if source > target:
            # if topological sort is deterministic and lexical, this is invalid.
            warnings.append(f"topological order: {source}->{target} is non-lexical")

    stable_errors = sorted(set(errors))
    stable_warnings = sorted(set(warnings))
    ok = len(stable_errors) == 0
    return ValidationResult(
        ok=ok,
        errors=tuple(stable_errors),
        warnings=tuple(stable_warnings),
        derived_startup_order=startup_order,
        derived_shutdown_order=shutdown_order,
    )


def validate_bootstrap_contract_file(path: str | Path) -> ValidationResult:
    contract_path = Path(path)
    payload = _load_json(contract_path)
    return validate_bootstrap_contract_payload(payload)
