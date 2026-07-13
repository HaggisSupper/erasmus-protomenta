"""Deterministic OKF-profile capability graph and planner."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

PROFILE = "erasmus.okf.capability-set/v1"
EDGE_TYPES = {
    "requires", "produces", "validates", "implements", "authorized_by",
    "conflicts_with", "may_follow", "can_rollback", "escalates_to",
}
CLASS_ORDER = {"deterministic": 0, "statistical": 1, "semantic": 2}
ROOT = Path(__file__).parents[2]
SCHEMA_PATH = ROOT / "capabilities" / "contracts" / "capability.schema.json"


class GraphValidationError(ValueError):
    """Raised when a capability set fails closed."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class PlannedStep:
    capability_id: str
    capability_version: str
    implementation_id: str
    implementation_version: str


@dataclass(frozen=True)
class CandidatePlan:
    plan_id: int
    goal: str
    steps: tuple[PlannedStep, ...]


def _ref(capability: dict[str, Any]) -> str:
    return f"{capability['id']}@{capability['version']}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _read_okf_bundle(path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    root = Path(path)
    documents = {
        file.relative_to(root).as_posix(): file.read_text(encoding="utf-8")
        for file in sorted(root.rglob("*.md"))
    }
    capabilities: list[dict[str, Any]] = []
    implementations: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for relative_path, content in documents.items():
        if Path(relative_path).name in {"index.md", "log.md"}:
            continue
        lines = content.replace("\r\n", "\n").splitlines()
        if not lines or lines[0] != "---" or "---" not in lines[1:]:
            raise ValueError(f"OKF concept lacks YAML frontmatter: {relative_path}")
        closing = lines[1:].index("---") + 1
        try:
            frontmatter = json.loads("\n".join(lines[1:closing]))
        except json.JSONDecodeError as exc:
            raise ValueError(f"unsupported OKF frontmatter in {relative_path}: {exc}") from exc
        if not isinstance(frontmatter, dict):
            raise ValueError(f"OKF frontmatter is not a mapping: {relative_path}")
        if not isinstance(frontmatter.get("type"), str) or not frontmatter["type"].strip():
            raise ValueError(f"OKF concept has no non-empty type: {relative_path}")
        if frontmatter["type"] != "Erasmus Capability":
            continue
        capability = frontmatter.get("contract")
        implementation = frontmatter.get("implementation")
        if not isinstance(capability, dict) or not isinstance(implementation, dict):
            raise ValueError(f"capability concept lacks contract or implementation: {relative_path}")
        capabilities.append(capability)
        implementations.append(implementation)
        source = _ref(capability)
        relationships = frontmatter.get("relationships", [])
        if not isinstance(relationships, list) or any(
            not isinstance(relationship, dict) for relationship in relationships
        ):
            raise ValueError(f"capability relationships are not a list of mappings: {relative_path}")
        for relationship in relationships:
            edges.append(
                {"from": source, "type": relationship.get("type"), "to": relationship.get("to")}
            )
    if not capabilities:
        raise ValueError(f"OKF bundle contains no Erasmus Capability concepts: {root}")
    return {
        "profile": PROFILE,
        "capabilities": capabilities,
        "implementations": implementations,
        "edges": edges,
    }, documents


def load_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        return _read_okf_bundle(path)[0]
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return every deterministic validation error; an empty list is valid."""
    with SCHEMA_PATH.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    validator = jsonschema.Draft202012Validator(schema)
    errors = [
        f"schema:{'/'.join(map(str, error.path)) or '/'}: {error.message}"
        for error in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path))
    ]
    if errors:
        return errors

    capabilities: dict[str, dict[str, Any]] = {}
    for capability in manifest["capabilities"]:
        ref = _ref(capability)
        if ref in capabilities:
            errors.append(f"duplicate capability version: {ref}")
        capabilities[ref] = capability
        for direction in ("inputs", "outputs"):
            names = [port["name"] for port in capability[direction]]
            if len(names) != len(set(names)):
                errors.append(f"duplicate {direction} port on {ref}")
        if not capability["authority_required"]:
            errors.append(f"missing authority declaration: {ref}")
        if "inherit" in capability["authority_required"]:
            errors.append(f"silent authority inheritance is forbidden: {ref}")
        if capability["side_effects"] and not (capability["rollback_behavior"] or "").strip():
            errors.append(f"missing rollback for side-effecting capability: {ref}")
        if not capability["required_evidence"]:
            errors.append(f"missing required evidence: {ref}")

    implementations: dict[str, dict[str, Any]] = {}
    for implementation in manifest["implementations"]:
        impl_ref = f"{implementation['id']}@{implementation['version']}"
        cap_ref = f"{implementation['capability_id']}@{implementation['capability_version']}"
        if impl_ref in implementations:
            errors.append(f"duplicate implementation version: {impl_ref}")
        implementations[impl_ref] = implementation
        capability = capabilities.get(cap_ref)
        if capability is None:
            errors.append(f"implementation endpoint does not exist: {impl_ref} -> {cap_ref}")
        elif implementation["id"] not in capability["allowed_implementations"]:
            errors.append(f"undeclared implementation: {impl_ref} for {cap_ref}")

    for ref, capability in capabilities.items():
        declared = set(capability["allowed_implementations"])
        actual = {
            item["id"] for item in manifest["implementations"]
            if f"{item['capability_id']}@{item['capability_version']}" == ref
        }
        for missing in sorted(declared - actual):
            errors.append(f"allowed implementation is not declared: {missing} for {ref}")

    adjacency: dict[str, list[str]] = {ref: [] for ref in capabilities}
    for edge in manifest["edges"]:
        source, target, edge_type = edge["from"], edge["to"], edge["type"]
        if edge_type not in EDGE_TYPES:
            errors.append(f"invalid edge type: {edge_type}")
        if source not in capabilities:
            errors.append(f"edge source does not exist: {source}")
        if target not in capabilities:
            errors.append(f"edge target does not exist: {target}")
        if source in capabilities and target in capabilities and edge_type == "requires":
            adjacency[source].append(target)
        elif source in capabilities and target in capabilities and edge_type == "may_follow":
            adjacency[source].append(target)

    for source, dependencies in adjacency.items():
        required_edges = [
            edge for edge in manifest["edges"]
            if edge["from"] == source and edge["type"] == "requires"
            and edge["to"] in capabilities
        ]
        if not required_edges:
            continue
        available = {
            port["name"]: port["schema"]
            for edge in required_edges
            for port in capabilities[edge["to"]]["outputs"]
        }
        for required in capabilities[source]["inputs"]:
            if available.get(required["name"]) != required["schema"]:
                errors.append(f"incompatible required port: {source}.{required['name']}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"forbidden execution cycle at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        visit(node)
    return errors


class CapabilityGraph:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def import_bundle(self, path: str | Path) -> None:
        manifest, documents = _read_okf_bundle(path)
        self.import_manifest(manifest, documents)

    def import_manifest(
        self, manifest: dict[str, Any], documents: dict[str, str] | None = None
    ) -> None:
        errors = validate_manifest(manifest)
        if errors:
            raise GraphValidationError(errors)
        with self.db:
            for table in (
                "capability_edges", "capability_ports", "capability_authorities",
                "capability_implementations", "capabilities", "capability_manifest_sets",
                "capability_okf_documents",
            ):
                self.db.execute(f"DELETE FROM {table}")  # noqa: S608
            self.db.execute(
                "INSERT INTO capability_manifest_sets(profile, manifest_json) VALUES(?, ?)",
                (manifest["profile"], _canonical(manifest)),
            )
            self.db.executemany(
                "INSERT INTO capability_okf_documents(path, content) VALUES(?, ?)",
                sorted((documents or {}).items()),
            )
            for capability in manifest["capabilities"]:
                values = (
                    capability["id"], capability["version"], capability["purpose"],
                    capability["classification"], _canonical(capability["goals"]),
                    _canonical(capability["authority_required"]),
                    _canonical(capability["side_effects"]),
                    _canonical(capability["provenance_requirements"]),
                    capability["failure_behavior"], capability["rollback_behavior"],
                    _canonical(capability["cost"]), _canonical(capability["required_evidence"]),
                    _canonical(capability["allowed_implementations"]),
                    _canonical(capability["tenth_man_triggers"]),
                )
                self.db.execute(
                    "INSERT INTO capabilities VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                for direction in ("inputs", "outputs"):
                    for port in capability[direction]:
                        self.db.execute(
                            "INSERT INTO capability_ports VALUES(?, ?, ?, ?, ?)",
                            (capability["id"], capability["version"], direction[:-1],
                             port["name"], _canonical(port["schema"])),
                        )
                for authority in capability["authority_required"]:
                    self.db.execute(
                        "INSERT INTO capability_authorities VALUES(?, ?, ?)",
                        (capability["id"], capability["version"], authority),
                    )
            for implementation in manifest["implementations"]:
                self.db.execute(
                    "INSERT INTO capability_implementations VALUES(?, ?, ?, ?)",
                    (implementation["id"], implementation["version"],
                     implementation["capability_id"], implementation["capability_version"]),
                )
            for edge in manifest["edges"]:
                source_id, source_version = edge["from"].rsplit("@", 1)
                target_id, target_version = edge["to"].rsplit("@", 1)
                self.db.execute(
                    "INSERT INTO capability_edges VALUES(?, ?, ?, ?, ?)",
                    (source_id, source_version, edge["type"], target_id, target_version),
                )

    def export_manifest(self) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT manifest_json FROM capability_manifest_sets WHERE profile = ?", (PROFILE,)
        ).fetchone()
        if row is None:
            raise LookupError("no capability manifest has been imported")
        return json.loads(row[0])

    def export_bundle(self, destination: str | Path) -> None:
        rows = self.db.execute(
            "SELECT path, content FROM capability_okf_documents ORDER BY path"
        ).fetchall()
        if not rows:
            raise LookupError("the imported graph has no OKF source documents")
        root = Path(destination)
        for relative_path, content in rows:
            target = (root / relative_path).resolve()
            if not target.is_relative_to(root.resolve()):
                raise ValueError(f"unsafe OKF document path: {relative_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def list_capabilities(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT id, version, purpose, classification FROM capabilities ORDER BY id, version"
        ).fetchall()
        return [dict(row) for row in rows]

    def inspect(self, capability_id: str, version: str | None = None) -> dict[str, Any]:
        manifest = self.export_manifest()
        matches = [
            item for item in manifest["capabilities"]
            if item["id"] == capability_id and (version is None or item["version"] == version)
        ]
        if not matches:
            raise LookupError(f"capability not found: {capability_id}{'@' + version if version else ''}")
        return sorted(matches, key=lambda item: item["version"], reverse=True)[0]

    def plan(self, goal: str, authorities: set[str], head_sha: str | None = None) -> list[CandidatePlan]:
        manifest = self.export_manifest()
        capabilities = {_ref(item): item for item in manifest["capabilities"]}
        requires: dict[str, list[str]] = {ref: [] for ref in capabilities}
        conflicts: set[frozenset[str]] = set()
        for edge in manifest["edges"]:
            if edge["type"] == "requires":
                requires[edge["from"]].append(edge["to"])
            elif edge["type"] == "conflicts_with":
                conflicts.add(frozenset((edge["from"], edge["to"])))

        candidates = [ref for ref, item in capabilities.items() if goal in item["goals"]]
        candidates.sort(key=lambda ref: (CLASS_ORDER[capabilities[ref]["classification"]], ref))
        plans: list[CandidatePlan] = []
        for candidate in candidates:
            ordered: list[str] = []

            def add(ref: str) -> None:
                for dependency in sorted(requires[ref]):
                    add(dependency)
                if ref not in ordered:
                    ordered.append(ref)

            add(candidate)
            if any(pair <= set(ordered) for pair in conflicts):
                continue
            if any(not set(capabilities[ref]["authority_required"]) <= authorities for ref in ordered):
                continue
            implementations: dict[str, list[dict[str, Any]]] = {}
            for item in manifest["implementations"]:
                implementations.setdefault(
                    f"{item['capability_id']}@{item['capability_version']}", []
                ).append(item)
            if any(len(implementations.get(ref, [])) != 1 for ref in ordered):
                continue
            # A merge plan is executable only when every prerequisite has
            # successful evidence bound to this exact head. Other goals may
            # be planned before their evidence exists because they produce it.
            if goal == "merge_guarded_pull_request":
                if head_sha is None or any(
                    self.db.execute(
                        "SELECT 1 FROM capability_evidence WHERE capability_id=? AND capability_version=? AND head_sha=? AND result='success' ORDER BY id DESC LIMIT 1",
                        (*ref.rsplit("@", 1), head_sha),
                    ).fetchone() is None
                    for ref in ordered[:-1]
                ):
                    continue
            with self.db:
                cursor = self.db.execute(
                    "INSERT INTO capability_plans(goal, authority_json, head_sha, status) VALUES(?, ?, ?, 'validated')",
                    (goal, _canonical(sorted(authorities)), head_sha),
                )
                plan_id = int(cursor.lastrowid)
                steps = tuple(
                    PlannedStep(
                        capabilities[ref]["id"], capabilities[ref]["version"],
                        implementations[ref][0]["id"], implementations[ref][0]["version"],
                    )
                    for ref in ordered
                )
                for position, step in enumerate(steps):
                    self.db.execute(
                        "INSERT INTO capability_execution_steps VALUES(?, ?, ?, ?, ?, ?)",
                        (plan_id, position, step.capability_id,
                         step.capability_version, step.implementation_id,
                         step.implementation_version),
                    )
            plans.append(CandidatePlan(plan_id, goal, steps))
        if not plans:
            return []
        best_rank = min(
            CLASS_ORDER[capabilities[f"{plan.steps[-1].capability_id}@{plan.steps[-1].capability_version}"]["classification"]]
            for plan in plans
        )
        preferred = [
            plan for plan in plans
            if CLASS_ORDER[capabilities[f"{plan.steps[-1].capability_id}@{plan.steps[-1].capability_version}"]["classification"]]
            == best_rank
        ]
        selected = preferred if len(preferred) == 1 else []
        discarded = [plan.plan_id for plan in plans if plan not in selected]
        if discarded:
            with self.db:
                self.db.executemany(
                    "DELETE FROM capability_plans WHERE id=?",
                    ((plan_id,) for plan_id in discarded),
                )
        return selected

    def record_evidence(
        self, capability_id: str, capability_version: str,
        implementation_id: str, implementation_version: str,
        inputs: Any, outputs: Any, result: str, head_sha: str | None = None,
    ) -> int:
        implementation = self.db.execute(
            "SELECT 1 FROM capability_implementations WHERE id=? AND version=? AND capability_id=? AND capability_version=?",
            (implementation_id, implementation_version, capability_id, capability_version),
        ).fetchone()
        if implementation is None:
            raise ValueError("evidence references an undeclared implementation")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO capability_evidence(capability_id, capability_version, implementation_id, implementation_version, inputs_json, outputs_json, head_sha, result) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (capability_id, capability_version, implementation_id,
                 implementation_version, _canonical(inputs), _canonical(outputs),
                 head_sha, result),
            )
        return int(cursor.lastrowid)
