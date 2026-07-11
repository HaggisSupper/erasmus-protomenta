from __future__ import annotations

from .store import Store


def consolidate(store: Store) -> dict[str, int]:
    rows = store.db.execute(
        "SELECT id, kind, payload FROM events ORDER BY id"
    ).fetchall()
    counts = {"events": len(rows), "experience_candidates": 0}
    for row in rows:
        if row["kind"] == "correction":
            store.db.execute(
                "INSERT INTO experience_candidates(lesson) VALUES(?)",
                (row["payload"],),
            )
            counts["experience_candidates"] += 1
    store.db.commit()
    return counts
