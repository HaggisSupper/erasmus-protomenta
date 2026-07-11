from __future__ import annotations

from .store import Store


def consolidate(store: Store) -> dict[str, int]:
    """Promote qualifying events to experience candidates.

    Only events with an id greater than the last processed event are
    considered, making the function safe to call multiple times without
    double-counting.  The progress marker and any new experience candidates
    are written in a single atomic transaction so an interrupted run leaves
    no partial state.

    Returns a dict with keys:
        ``events``               — number of new events processed this call.
        ``experience_candidates``— number of new candidates created this call.
        ``last_event_id``        — the highest event id now marked as processed.
    """
    row = store.db.execute(
        "SELECT last_event_id FROM sleep_progress WHERE id = 1"
    ).fetchone()
    last_id: int = row["last_event_id"] if row is not None else 0

    rows = store.db.execute(
        "SELECT id, kind, payload FROM events WHERE id > ? ORDER BY id",
        (last_id,),
    ).fetchall()

    counts: dict[str, int] = {
        "events": len(rows),
        "experience_candidates": 0,
        "last_event_id": last_id,
    }

    if not rows:
        return counts

    new_last_id = last_id
    new_candidates = 0

    with store.db:
        for row in rows:
            if row["kind"] == "correction":
                store.db.execute(
                    "INSERT INTO experience_candidates(lesson) VALUES(?)",
                    (row["payload"],),
                )
                new_candidates += 1
            new_last_id = row["id"]

        store.db.execute(
            """
            INSERT INTO sleep_progress(id, last_event_id)
                VALUES(1, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_event_id = excluded.last_event_id,
                updated_at    = CURRENT_TIMESTAMP
            """,
            (new_last_id,),
        )

    counts["experience_candidates"] = new_candidates
    counts["last_event_id"] = new_last_id
    return counts
