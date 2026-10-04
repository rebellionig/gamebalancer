"""Явное хранилище состояния задачи (SQLite): что предложено, что насчитано, какой баланс получился."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path("state/state.db")


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS iterations (
                   run_id TEXT, iteration INTEGER,
                   proposal TEXT, result TEXT, balance TEXT,
                   PRIMARY KEY (run_id, iteration))"""
        )

    def save_iteration(self, run_id: str, iteration: int, proposal: dict, result: dict, balance: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO iterations VALUES (?,?,?,?,?)",
            (run_id, iteration, json.dumps(proposal), json.dumps(result), json.dumps(balance)),
        )
        self.db.commit()

    def history(self, run_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT iteration, proposal, result, balance FROM iterations WHERE run_id=? ORDER BY iteration",
            (run_id,),
        ).fetchall()
        return [
            {"iteration": i, "proposal": json.loads(p), "result": json.loads(r), "balance": json.loads(b)}
            for i, p, r, b in rows
        ]
