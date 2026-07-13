"""Compact resume-checkpoint model for the Erasmus cognitive frontier.

A :class:`Checkpoint` captures the full resumable state at a moment in time.
Human-readable frontier fields remain plain text. An optional proposition id
links to the append-only epistemic ledger without copying its history. Source
event ids link the checkpoint back to the append-only event log.

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
    proposition_id
        Optional stable reference to the active epistemic-ledger proposition.
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
    proposition_id: int | None = None


def _validate(cp: "Checkpoint", store: "Store") -> None:
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
    if not cp.source_event_ids:
        raise ValueError(
            "source_event_ids must reference at least one event; "
            "provide the ids of the events this checkpoint synthesises"
        )
    # Validate that every referenced event actually exists in the store.
    placeholders = ",".join("?" * len(cp.source_event_ids))
    found = {
        row["id"]
        for row in store.db.execute(
            f"SELECT id FROM events WHERE id IN ({placeholders})",  # noqa: S608
            cp.source_event_ids,
        ).fetchall()
    }
    missing = set(cp.source_event_ids) - found
    if missing:
        raise ValueError(
            f"source_event_ids references event ids that do not exist: {sorted(missing)}"
        )
    if cp.proposition_id is not None and store.db.execute(
        "SELECT 1 FROM propositions WHERE id = ?", (cp.proposition_id,)
    ).fetchone() is None:
        raise ValueError(f"proposition_id does not exist: {cp.proposition_id}")


def save_checkpoint(store: "Store", cp: Checkpoint) -> int:
    """Validate *cp* and persist it atomically.

    Returns the new checkpoint ``id``.

    Raises:
        ValueError: If any required field is empty or of the wrong type.
    """
    _validate(cp, store)
    with store.db:
        cur = store.db.execute(
            """
            INSERT INTO checkpoints(
                frontier, proposition, strongest_support,
                strongest_contradiction, unresolved_tension,
                active_mode, next_move, pending_leap,
                relevant_tangible_wrongness, source_event_ids, proposition_id
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                cp.proposition_id,
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
               relevant_tangible_wrongness, source_event_ids, proposition_id
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
        proposition_id=row["proposition_id"],
    )
