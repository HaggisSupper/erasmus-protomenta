from __future__ import annotations

from .store import Store


def create_mission(
    store: Store,
    title: str,
    objective: str,
    success: str,
    risk: float = 0.0,
) -> int:
    cur = store.db.execute(
        "INSERT INTO missions(title, objective, success_condition, risk) "
        "VALUES(?, ?, ?, ?)",
        (title, objective, success, risk),
    )
    store.db.commit()
    return int(cur.lastrowid)
