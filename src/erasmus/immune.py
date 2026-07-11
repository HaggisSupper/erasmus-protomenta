from __future__ import annotations

from dataclasses import asdict
import json

from .models import ImmuneAlert


def deterministic_screen(
    *,
    confidence_delta: float,
    new_evidence: int,
    authority_delta: int,
    consequence: float,
) -> list[ImmuneAlert]:
    alerts: list[ImmuneAlert] = []
    if confidence_delta > 0.20 and new_evidence == 0:
        alerts.append(
            ImmuneAlert(
                "confidence_without_evidence",
                "confidence rose without new evidence",
                min(1.0, confidence_delta + consequence / 2),
            )
        )
    if authority_delta > 0:
        alerts.append(
            ImmuneAlert(
                "authority_creep",
                "capability requested undeclared authority",
                min(1.0, 0.5 + 0.1 * authority_delta + consequence / 2),
            )
        )
    return alerts


def serialize(alerts: list[ImmuneAlert]) -> str:
    return json.dumps([asdict(alert) for alert in alerts], indent=2)
