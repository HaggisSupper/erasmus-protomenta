from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS propositions(
    id INTEGER PRIMARY KEY,
    statement TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS missions(
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    success_condition TEXT NOT NULL,
    risk REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS experience_candidates(
    id INTEGER PRIMARY KEY,
    lesson TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'candidate'
);
CREATE TABLE IF NOT EXISTS immune_state(
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    state_json TEXT NOT NULL,
    wake_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sleeping',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS checkpoints(
    id INTEGER PRIMARY KEY,
    frontier TEXT NOT NULL,
    next_move TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: str = "state/erasmus.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row

    def init(self) -> None:
        self.db.executescript(SCHEMA)
        self.db.commit()

    def add_event(self, kind: str, payload: str) -> None:
        self.db.execute(
            "INSERT INTO events(kind, payload) VALUES(?, ?)",
            (kind, payload),
        )
        self.db.commit()
