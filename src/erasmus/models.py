from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EpistemicStatus(StrEnum):
    ESTABLISHED = "established"
    SUPPORTED = "supported"
    PLAUSIBLE = "plausible"
    SPECULATIVE = "speculative"
    ANALOGY = "analogy"
    LEAP = "leap"
    CONTRADICTED = "contradicted"
    FALSIFIED = "falsified"
    UNRESOLVED = "unresolved"


@dataclass(slots=True)
class Mission:
    title: str
    objective: str
    success_condition: str
    risk: float = 0.0
    status: str = "proposed"


@dataclass(slots=True)
class ImmuneAlert:
    detector: str
    signature: str
    score: float
    context: dict[str, Any] = field(default_factory=dict)
