"""Phase 3 knowledge runtime foundations.

This module provides the minimum deterministic runtime surface for:
- policy contract validation (JSON schema check);
- request validation for operator payloads;
- policy evaluation with deterministic conflict rules and receipt materialization;
- immutable inspect for policy/registry/channel foundations.

It intentionally stays bounded: no mutation to model truth state, no publication,
and no silent inference.  Evaluation side effects are append-only receipts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _ROOT / "docs" / "architecture" / "knowledge-system" / "schemas"


class KnowledgeRuntimeError(ValueError):
    """Raised for malformed policy runtime inputs or persistence failures."""


_GOVERNANCE_SCHEMA = _SCHEMA_DIR / "governance-registry.schema.json"
_OPERATOR_SCHEMA = _SCHEMA_DIR / "operator-api.schema.json"

_FAILURE_ACTIONS = {
    "invalid_request": "validate and fix request payload",
    "invalid_policy": "activate a valid policy contract",
    "invalid_registry": "activate a valid registry snapshot",
    "invalid_channel": "register a valid publication channel",
    "insufficient_policy": "supply a stricter or active policy",
    "missing_authority": "supply required authority",
    "requires_human_approval": "route request for human approval",
    "requires_tenth_man": "request tenth-man review",
    "conflict": "resolve conflicting rules in the active policy",
    "missing_review": "supply required review evidence",
}


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    details: Mapping[str, Any]
    retryable: bool = False
    action: str = "inspect"
    related_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "retryable": self.retryable,
            "action": self.action,
            "related_ids": list(self.related_ids),
        }


def _canonical_json(value: Mapping[str, Any] | list[Any] | Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(value: Mapping[str, Any] | list[Any] | Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _load_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise KnowledgeRuntimeError(f"schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(
    payload: Mapping[str, Any] | list[Any] | Any,
    *,
    schema: Mapping[str, Any],
    definition: str,
) -> tuple[bool, list[str]]:
    """Validate *payload* against one named $defs branch."""
    validator = Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"},
    )
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    return (len(errors) == 0, [error.message for error in errors])


def _digest_object(payload: Mapping[str, Any] | list[Any] | Any) -> dict[str, str]:
    return {"algorithm": "sha256", "value": _sha256_hex(payload), "canonicalization": "canonical-json/v1"}


def _json_load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _int_from_bool(value: bool) -> int:
    return 1 if value else 0


def _coerce_str(value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeRuntimeError("policy references must be strings")
    value = value.strip()
    if not value:
        raise KnowledgeRuntimeError("policy references cannot be blank")
    return value


def _coerce_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_coerce_str(value),)
    if value is None:
        return ()
    if isinstance(value, (bytes, bytearray, Mapping)):
        raise KnowledgeRuntimeError("authority sequence must be an array of strings")
    if not isinstance(value, Iterable):
        raise KnowledgeRuntimeError("authority sequence must be an array of strings")
    return tuple(_coerce_str(item) for item in value)


def _require_mapping(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise KnowledgeRuntimeError("payload must be an object")
    return payload


def _sorted_json(value: Mapping[str, Any] | list[Any]) -> tuple[str, ...]:
    return tuple(sorted(str(v) for v in value))


class KnowledgeRuntime:
    """Bounded evaluator and inspector for P3.0A foundations."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    # ------------------------------------------------------------------
    # Public validation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def validate_knowledge_policy(payload: Mapping[str, Any]) -> dict[str, Any]:
        valid, errors = validate_contract(
            payload,
            schema=_load_schema(_GOVERNANCE_SCHEMA),
            definition="knowledgePolicySet",
        )
        return {"valid": valid, "errors": errors}

    @staticmethod
    def validate_semantic_registry(payload: Mapping[str, Any]) -> dict[str, Any]:
        valid, errors = validate_contract(
            payload,
            schema=_load_schema(_GOVERNANCE_SCHEMA),
            definition="semanticRegistrySnapshot",
        )
        return {"valid": valid, "errors": errors}

    @staticmethod
    def validate_publication_channel(payload: Mapping[str, Any]) -> dict[str, Any]:
        valid, errors = validate_contract(
            payload,
            schema=_load_schema(_GOVERNANCE_SCHEMA),
            definition="publicationChannel",
        )
        return {"valid": valid, "errors": errors}

    @staticmethod
    def validate_knowledge_request(payload: Mapping[str, Any]) -> dict[str, Any]:
        valid, errors = validate_contract(
            payload,
            schema=_load_schema(_OPERATOR_SCHEMA),
            definition="knowledgeRequest",
        )
        return {"valid": valid, "errors": errors}

    def _load_policy(self, policy_id: str, version: str) -> sqlite3.Row | None:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        row = self.db.execute(
            """
            SELECT *
            FROM knowledge_policy_sets
            WHERE policy_id = ? AND version = ? AND status = 'active'
              AND effective_at <= ?
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (policy_id, version, now, now),
        ).fetchone()
        if row is None:
            return None
        return row

    def inspect_policy(self, reference: str) -> dict[str, Any]:
        policy_id, version = _policy_ref(reference)
        row = self._load_policy(policy_id, version)
        if row is None:
            raise KnowledgeRuntimeError(f"knowledge policy not found: {reference}")
        payload = json.loads(row["policy_json"])
        payload["status"] = row["status"]
        payload["created_by"] = row["created_by"]
        payload["event_seq"] = row["event_seq"]
        payload["effective_at"] = row["effective_at"]
        payload["created_at"] = row["created_at"]
        return payload

    def inspect_registry(self, snapshot_id: str) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT registry_snapshot_id, sequence, parent_snapshot_id, status, definitions_json,
                manifest_digest, event_seq, approval_id, created_by, created_at
            FROM knowledge_semantic_registry_snapshots
            WHERE registry_snapshot_id = ?
            """,
            (_coerce_str(snapshot_id),),
        ).fetchone()
        if row is None:
            raise KnowledgeRuntimeError(f"registry snapshot not found: {_coerce_str(snapshot_id)}")
        return {
            "registry_snapshot_id": row["registry_snapshot_id"],
            "sequence": row["sequence"],
            "parent_snapshot_id": row["parent_snapshot_id"],
            "status": row["status"],
            "definitions_json": json.loads(row["definitions_json"]),
            "manifest_digest": json.loads(row["manifest_digest"]) if row["manifest_digest"].startswith("{") else row["manifest_digest"],
            "event_seq": row["event_seq"],
            "approval_id": row["approval_id"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
        }

    def inspect_channel(self, channel_id: str) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT *
            FROM knowledge_publication_channels
            WHERE channel_id = ?
            """,
            (_coerce_str(channel_id),),
        ).fetchone()
        if row is None:
            raise KnowledgeRuntimeError(f"publication channel not found: {_coerce_str(channel_id)}")
        return {
            "channel_id": row["channel_id"],
            "name": row["name"],
            "audience": row["audience"],
            "scope_selector": json.loads(row["scope_selector_json"]),
            "root_path": row["root_path"],
            "policy_id": row["policy_id"],
            "policy_version": row["policy_version"],
            "rendering_profile": row["rendering_profile"],
            "retention": json.loads(row["retention_json"]),
            "redaction_profile": row["redaction_profile"],
            "status": row["status"],
            "event_seq": row["event_seq"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
        }

    def evaluate_policy_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        request_mapping = _require_mapping(request)
        valid, errors = validate_contract(
            request_mapping,
            schema=_load_schema(_OPERATOR_SCHEMA),
            definition="knowledgeRequest",
        )
        if not valid:
            return _knowledge_response(
                request_id=_safe_request_id(request_mapping),
                operation=_safe_operation(request_mapping),
                ok=False,
                receipts=(),
                failure=Failure(
                    code="invalid_request",
                    message="knowledge request payload is invalid",
                    details={"errors": errors},
                    action=_FAILURE_ACTIONS["invalid_request"],
                    related_ids=("erasmus.knowledge-request/v1",),
                ),
            )

        policy_id = _coerce_str(request_mapping["policy"]["policy_id"])
        version = _coerce_str(request_mapping["policy"]["version"])
        row = self._load_policy(policy_id, version)
        if row is None:
            return _knowledge_response(
                request_id=request_mapping["request_id"],
                operation=request_mapping["operation"],
                ok=False,
                receipts=(),
                failure=Failure(
                    code="insufficient_policy",
                    message=f"no active policy found for {policy_id}@{version}",
                    details={"policy_id": policy_id, "policy_version": version},
                    action=_FAILURE_ACTIONS["insufficient_policy"],
                    related_ids=(f"{policy_id}@{version}",),
                ),
            )

        policy = json.loads(row["policy_json"])
        policy_valid, policy_errors = validate_contract(
            policy,
            schema=_load_schema(_GOVERNANCE_SCHEMA),
            definition="knowledgePolicySet",
        )
        if not policy_valid:
            return _knowledge_response(
                request_id=request_mapping["request_id"],
                operation=request_mapping["operation"],
                ok=False,
                receipts=(),
                failure=Failure(
                    code="invalid_policy",
                    message="stored policy contract is invalid",
                    details={"errors": policy_errors},
                    action=_FAILURE_ACTIONS["invalid_policy"],
                    related_ids=(f"{policy_id}@{version}",),
                ),
            )

        evaluation = _evaluate_rules(
            policy,
            request_mapping,
            {
                "policy_id": policy_id,
                "policy_version": version,
                "policy_digest": row["policy_digest"],
                "event_seq": row["event_seq"],
            },
        )

        response = _knowledge_response(
            request_id=request_mapping["request_id"],
            operation=request_mapping["operation"],
            ok=evaluation.ok,
            receipts=[evaluation.receipt],
            warnings=[],
            next_actions=evaluation.next_actions,
            failure=evaluation.failure,
        )
        if not request_mapping.get("dry_run", False):
            _persist_evaluation(self.db, row["id"], policy_id, version, row["policy_digest"], request_mapping, evaluation)
        return response


def _policy_ref(value: str) -> tuple[str, str]:
    policy_id, _, version = _coerce_str(value).rpartition("@")
    if not policy_id or not version:
        raise KnowledgeRuntimeError("policy reference must be <policy_id>@<version>")
    return policy_id, version


def _safe_request_id(payload: Mapping[str, Any]) -> str:
    return _coerce_str(payload.get("request_id", "urn:erasmus:knowledge-request:invalid"))


def _safe_operation(payload: Mapping[str, Any]) -> str:
    return _coerce_str(payload.get("operation", "unknown"))


@dataclass(frozen=True)
class Evaluation:
    decision: str
    matched_rule_ids: tuple[str, ...]
    required_authorities: tuple[str, ...]
    required_reviews: tuple[Mapping[str, Any], ...]
    required_approvals: tuple[Mapping[str, Any], ...]
    remaining_conditions: tuple[Mapping[str, Any], ...]
    reason_codes: tuple[str, ...]
    receipt: dict[str, Any]
    next_actions: tuple[Mapping[str, Any], ...]
    failure: Failure | None
    ok: bool


def _match_rules(
    rules: list[Mapping[str, Any]],
    request: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    operation = request["operation"]
    requested_authorities = tuple(sorted(_sorted_json(_coerce_sequence(request.get("authority", [])))))
    requested_risk = str(request.get("risk_class", "routine"))
    subject_kind = request["input"].get("subject_kind")
    matched: list[Mapping[str, Any]] = []
    for rule in rules:
        if operation not in rule.get("operations", ()):
            continue
        if requested_risk not in rule.get("risk_classes", ()):
            continue
        if subject_kind is not None:
            subject_kinds = tuple(rule.get("subject_kinds", ()))
            if subject_kind not in subject_kinds and "subject" not in subject_kinds and "all" not in subject_kinds:
                continue
        matched.append(rule)
    return tuple(sorted(matched, key=lambda item: int(item.get("priority", 0)), reverse=True))


def _evaluate_rules(
    policy: Mapping[str, Any],
    request: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Evaluation:
    rules = _match_rules(policy.get("rules", ()), request)
    if not rules:
        return Evaluation(
            decision="insufficient_policy",
            matched_rule_ids=(),
            required_authorities=(),
            required_reviews=(),
            required_approvals=(),
            remaining_conditions=({"condition": "no_matching_rules"},),
            reason_codes=("no_matching_rule",),
            receipt={},
            next_actions=({"action": "supply active policy", "operation": request["operation"]},),
            failure=Failure(
                code="insufficient_policy",
                message="no policy rule matched request metadata",
                details={"operation": request["operation"]},
                action=_FAILURE_ACTIONS["insufficient_policy"],
                related_ids=(context["policy_id"],),
            ),
            ok=False,
        )

    top_priority = int(rules[0].get("priority", 0))
    candidates = tuple(rule for rule in rules if int(rule.get("priority", 0)) == top_priority)
    automations = _sorted_json(rule.get("automation") for rule in candidates)
    deny = any(auto == "deny" for auto in automations)
    observation_only = any(auto == "observation_only" for auto in automations)
    permit = any(auto == "permit" for auto in automations)

    required_authorities = tuple(sorted(_coerce_set_union(rule.get("required_authorities", []) for rule in candidates)))
    required_reviews = _collect_required_reviews(candidates)
    required_review_ids = tuple(
        _coerce_str(review["review_id"])
        for review in required_reviews
        if isinstance(review, Mapping) and "review_id" in review
    )
    request_review_ids = _sorted_json(request.get("review_ids", ()))
    required_approvals: tuple[Mapping[str, Any], ...] = ()
    required = set(request.get("authority", ()))
    missing_authorities = tuple(authority for authority in required_authorities if authority not in required)
    missing_reviews = tuple(review_id for review_id in required_review_ids if review_id not in request_review_ids)

    remaining: list[Mapping[str, Any]] = []
    next_actions: list[Mapping[str, Any]] = []
    if missing_authorities:
        remaining.append({"kind": "missing_authority", "authorities": list(missing_authorities)})
        next_actions.append({"kind": "obtain_authority", "authorities": list(missing_authorities)})

    human_approval_required = any(rule.get("human_approval") == "required" for rule in candidates)
    if human_approval_required:
        remaining.append({"kind": "human_approval"})
        next_actions.append({"kind": "request_human_approval"})
    if missing_reviews:
        remaining.append({"kind": "missing_review", "review_ids": list(missing_reviews)})
        next_actions.append({"kind": "obtain_review", "review_ids": list(missing_reviews)})

    conflicting = (
        "deny" in automations and ("permit" in automations or "observation_only" in automations)
    ) or (permit and observation_only)
    if conflicting:
        return _evaluation_blocked(
            policy,
            request,
            context,
            candidates,
            missing_authorities,
            remaining,
            next_actions,
            reason="conflicting automation",
            decision="requires_review",
            code="conflict",
            action="conflict",
        )

    if missing_authorities or human_approval_required or missing_reviews:
        if missing_authorities:
            code = "missing_authority"
            action = "missing_authority"
        elif missing_reviews:
            code = "missing_review"
            action = "missing_review"
        else:
            code = "requires_human_approval"
            action = "requires_human_approval"
        return _evaluation_blocked(
            policy,
            request,
            context,
            candidates,
            missing_authorities,
            remaining,
            next_actions,
            reason="policy preconditions not met",
            decision="requires_review",
            code=code,
            action=action,
        )

    if deny:
        return _evaluation_allowed(
            policy, request, context, candidates, matched_decision="deny",
            next_actions=tuple(),
            failure=Failure(
                code="denied",
                message="policy requires deny",
                details={"rule_ids": [rule["rule_id"] for rule in candidates]},
                action="review",
                related_ids=(context["policy_id"],),
            ),
        )
    if permit:
        return _evaluation_allowed(
            policy, request, context, candidates, matched_decision="permit",
            next_actions=tuple(),
            failure=None,
        )
    if observation_only:
        return _evaluation_allowed(
            policy, request, context, candidates, matched_decision="observation_only",
            next_actions=({"kind": "dry_run_only", "policy_id": context["policy_id"]},),
            failure=None,
        )
    return _evaluation_blocked(
        policy,
        request,
        context,
        candidates,
        missing_authorities,
        remaining,
        next_actions,
        reason="unable to compute a supported automation outcome",
        decision="requires_review",
        code="conflict",
        action="review",
    )


def _evaluation_allowed(
    policy: Mapping[str, Any],
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    candidates: tuple[Mapping[str, Any], ...],
    *,
    matched_decision: str,
    next_actions: tuple[Mapping[str, Any], ...],
    failure: Failure | None,
) -> Evaluation:
    matched_rule_ids = tuple(str(rule.get("rule_id", "")) for rule in candidates)
    required_authorities = _coerce_set_union(rule.get("required_authorities", []) for rule in candidates)
    required_reviews = _collect_required_reviews(candidates)
    return Evaluation(
        decision=matched_decision,
        matched_rule_ids=matched_rule_ids,
        required_authorities=tuple(sorted(required_authorities)),
        required_reviews=required_reviews,
        required_approvals=(),
        remaining_conditions=(),
        reason_codes=(f"decision:{matched_decision}",),
        receipt=_build_receipt(policy, request, context, matched_rule_ids, matched_decision, required_authorities, required_reviews),
        next_actions=next_actions,
        failure=failure,
        ok=matched_decision in {"permit", "observation_only"},
    )


def _evaluation_blocked(
    policy: Mapping[str, Any],
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    candidates: tuple[Mapping[str, Any], ...],
    missing_authorities: tuple[str, ...],
    remaining: list[Mapping[str, Any]],
    next_actions: list[Mapping[str, Any]],
    *,
    reason: str,
    decision: str,
    code: str,
    action: str,
) -> Evaluation:
    matched_rule_ids = tuple(str(rule.get("rule_id", "")) for rule in candidates)
    required_authorities = _coerce_set_union(rule.get("required_authorities", []) for rule in candidates)
    required_reviews = _collect_required_reviews(candidates)
    return Evaluation(
        decision=decision,
        matched_rule_ids=matched_rule_ids,
        required_authorities=tuple(sorted(required_authorities)),
        required_reviews=required_reviews,
        required_approvals=(),
        remaining_conditions=tuple(remaining),
        reason_codes=(reason,),
        receipt=_build_receipt(policy, request, context, matched_rule_ids, decision, required_authorities, required_reviews),
        next_actions=tuple(next_actions),
        failure=Failure(
            code=code,
            message=reason,
            details={"rule_ids": list(matched_rule_ids)},
            action=_FAILURE_ACTIONS.get(action, "review"),
            related_ids=(_coerce_str(context["policy_id"]), *missing_authorities),
        ),
        ok=False,
    )


def _knowledge_response(
    *,
    request_id: str,
    operation: str,
    ok: bool,
    receipts: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    failure: Failure | None,
    warnings: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    next_actions: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    started = datetime.now(UTC).isoformat()
    completed = datetime.now(UTC).isoformat()
    if failure is None:
        failure_payload = None
    else:
        failure_payload = failure.as_dict()
    return {
        "contract": "erasmus.knowledge-response/v1",
        "request_id": request_id,
        "operation": operation,
        "ok": bool(ok),
        "receipts": [dict(receipt) for receipt in receipts],
        "evidence_refs": [],
        "warnings": list(warnings),
        "next_actions": list(next_actions),
        "failure": failure_payload,
        "started_at": started,
        "completed_at": completed,
        "duration_ms": 0,
    }


def _persist_evaluation(
    db: sqlite3.Connection,
    policy_set_id: int,
    policy_id: str,
    policy_version: str,
    policy_digest: str,
    request: Mapping[str, Any],
    evaluation: Evaluation,
) -> None:
    request_id = request["request_id"]
    matched = _sorted_json(evaluation.matched_rule_ids)
    required_authorities = _sorted_json(evaluation.required_authorities)
    required_reviews = [dict(item) for item in evaluation.required_reviews]
    required_approvals = [dict(item) for item in evaluation.required_approvals]
    remaining_conditions = [dict(item) for item in evaluation.remaining_conditions]
    reason_codes = _sorted_json(evaluation.reason_codes)
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))
    request_digest = _sha256_hex(request)
    evaluated_at = datetime.now(UTC).isoformat()
    next_event_seq = (db.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM knowledge_policy_evaluations").fetchone()[0])
    evaluation_id = f"urn:erasmus:knowledge-policy-evaluation:{_sha256_hex(request_digest + request['operation'] + policy_id + policy_version + str(next_event_seq))}"
    with db:
        db.execute(
            """
        INSERT INTO knowledge_policy_evaluations(
            evaluation_id, policy_set_id, policy_id, policy_version, policy_digest,
            request_id, operation, subject_ids_json, matched_rule_ids_json, decision,
            required_authorities_json, required_reviews_json, required_approvals_json,
            remaining_conditions_json, reason_codes_json, request_json,
            request_digest, dry_run, evaluated_at, event_seq
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
            (
            evaluation_id, policy_set_id, policy_id, policy_version, policy_digest,
            request_id, request["operation"], json.dumps(request.get("subject_ids", [])),
            json.dumps(matched), evaluation.decision, json.dumps(required_authorities),
            json.dumps(required_reviews), json.dumps(required_approvals),
            json.dumps(remaining_conditions), json.dumps(reason_codes),
            request_json, request_digest, evaluated_at, int(next_event_seq),
            ),
        )


def _collect_required_reviews(rules: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    reviews: list[dict[str, Any]] = []
    for rule in rules:
        reviews.extend(dict(review) for review in rule.get("required_reviews", []))
    return tuple(sorted(reviews, key=_canonical_json))


def _build_receipt(
    policy: Mapping[str, Any],
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    matched_rule_ids: tuple[str, ...],
    decision: str,
    required_authorities: set[str],
    required_reviews: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    event_seq = context["event_seq"]
    policy_digest = policy.get("policy_digest")
    if policy_digest is None:
        policy_digest = context.get("policy_digest")
    if isinstance(policy_digest, Mapping):
        normalized_policy_digest = dict(policy_digest)
    elif isinstance(policy_digest, str) and policy_digest.strip().startswith("{"):
        normalized_policy_digest = json.loads(policy_digest)
    else:
        normalized_policy_digest = _digest_object(policy)
    return {
        "contract": "erasmus.policy-evaluation/v1",
        "evaluation_id": f"urn:erasmus:knowledge-evaluation:{_sha256_hex(policy['policy_id'] + policy['version'] + request['request_id'])}",
        "policy_id": context["policy_id"],
        "policy_version": context["policy_version"],
        "policy_digest": normalized_policy_digest,
        "operation": request["operation"],
        "subject_ids": list(request.get("subject_ids", [])),
        "request_digest": _digest_object(request),
        "matched_rule_ids": list(matched_rule_ids),
        "decision": decision,
        "required_authorities": list(required_authorities),
        "required_reviews": list(required_reviews),
        "required_approvals": [],
        "remaining_conditions": [],
        "budgets": dict(request.get("budgets", {})),
        "reason_codes": ["policy_rationale"],
        "evaluated_by": "process:erasmus-knowledge-runtime",
        "event_seq": int(event_seq),
        "evaluated_at": datetime.now(UTC).isoformat(),
    }


def _coerce_set_union(items: Iterable[Any]) -> set[str]:
    values: set[str] = set()
    for item in items:
        if isinstance(item, str):
            values.add(item)
        elif isinstance(item, Iterable) and not isinstance(item, (bytes, bytearray, dict)):
            values.update(str(value) for value in item)
        else:
            values.add(str(item))
    return values
