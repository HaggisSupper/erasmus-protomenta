"""Compact resume-checkpoint model for the Erasmus cognitive frontier.

A :class:`Checkpoint` captures the full resumable state at a moment in time.
All fields that reference propositions or evidence are plain text that can be
inspected without model assistance (10th-Man requirement).  Source event ids
link the checkpoint back to the append-only event log so the checkpoint is
auditable rather than a lossy opaque summary.

Public API
----------
- :class:`Checkpoint` — frozen snapshot of the cognitive frontier.
- :func:`save_checkpoint` — validate and persist atomically.
- :func:`load_latest_checkpoint` — retrieve the most recent checkpoint.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "frontier",
    "proposition",
    "strongest_support",
    "strongest_contradiction",
    "unresolved_tension",
    "active_mode",
    "next_move",
)


@dataclass(slots=True)
class Checkpoint:
    """Resumable snapshot of the active cognitive frontier.

    Required fields
    ---------------
    frontier
        Plain-text description of the current reasoning boundary.
    proposition
        The central claim under evaluation.
    strongest_support
        Best evidence or argument in favour of the proposition.
    strongest_contradiction
        Strongest counter-evidence or argument against the proposition.
    unresolved_tension
        The most important open question or conflict.
    active_mode
        Current processing mode (e.g. ``'dialogue'``, ``'analysis'``,
        ``'synthesis'``).
    next_move
        The concrete next action to take on resumption.

    Optional fields
    ---------------
    pending_leap
        A leap-of-faith hypothesis that has not yet been tested.
    relevant_tangible_wrongness
        A recent concrete prediction failure that constrains inference.
    source_event_ids
        Ids of events in the ``events`` table that this checkpoint
        synthesises.  Preserves provenance without relying on generated
        text as a sole record.
    """

    frontier: str
    proposition: str
    strongest_support: str
    strongest_contradiction: str
    unresolved_tension: str
    active_mode: str
    next_move: str
    pending_leap: str | None = None
    relevant_tangible_wrongness: str | None = None
    source_event_ids: list[int] = field(default_factory=list)


def _validate(cp: Checkpoint) -> None:
    """Raise :exc:`ValueError` for any invalid checkpoint field."""
    for field_name in _REQUIRED_TEXT_FIELDS:
        value = getattr(cp, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Checkpoint field '{field_name}' must be a non-empty string; "
                f"got {value!r}"
            )
    if not isinstance(cp.source_event_ids, list) or not all(
        isinstance(i, int) for i in cp.source_event_ids
    ):
        raise ValueError(
            "source_event_ids must be a list of integers; "
            f"got {cp.source_event_ids!r}"
        )


def save_checkpoint(store: "Store", cp: Checkpoint) -> int:
    """Validate *cp* and persist it atomically.

    Returns the new checkpoint ``id``.

    Raises:
        ValueError: If any required field is empty or of the wrong type.
    """
    _validate(cp)
    with store.db:
        cur = store.db.execute(
            """
            INSERT INTO checkpoints(
                frontier, proposition, strongest_support,
                strongest_contradiction, unresolved_tension,
                active_mode, next_move, pending_leap,
                relevant_tangible_wrongness, source_event_ids
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cp.frontier,
                cp.proposition,
                cp.strongest_support,
                cp.strongest_contradiction,
                cp.unresolved_tension,
                cp.active_mode,
                cp.next_move,
                cp.pending_leap,
                cp.relevant_tangible_wrongness,
                json.dumps(cp.source_event_ids),
            ),
        )
    return int(cur.lastrowid)


def load_latest_checkpoint(store: "Store") -> Checkpoint | None:
    """Return the most recently committed :class:`Checkpoint`, or ``None``.

    Only committed checkpoints are visible (WAL reader sees the last
    committed state).
    """
    row = store.db.execute(
        """
        SELECT frontier, proposition, strongest_support,
               strongest_contradiction, unresolved_tension,
               active_mode, next_move, pending_leap,
               relevant_tangible_wrongness, source_event_ids
        FROM   checkpoints
        ORDER  BY id DESC
        LIMIT  1
        """
    ).fetchone()
    if row is None:
        return None
    return Checkpoint(
        frontier=row["frontier"],
        proposition=row["proposition"],
        strongest_support=row["strongest_support"],
        strongest_contradiction=row["strongest_contradiction"],
        unresolved_tension=row["unresolved_tension"],
        active_mode=row["active_mode"],
        next_move=row["next_move"],
        pending_leap=row["pending_leap"],
        relevant_tangible_wrongness=row["relevant_tangible_wrongness"],
        source_event_ids=json.loads(row["source_event_ids"] or "[]"),
    )
