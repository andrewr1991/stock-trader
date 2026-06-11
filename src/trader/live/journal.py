"""Decision journal: every equity mark, target, order, and event, in SQLite.

The journal is the system's clean record for evaluation and retraining —
if it isn't in the journal, it didn't happen.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trader.config import JOURNAL_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS equity_log (
    date TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    drawdown REAL NOT NULL,
    benchmark_price REAL
);
CREATE TABLE IF NOT EXISTS targets (
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    weight REAL NOT NULL,
    notional REAL NOT NULL,
    PRIMARY KEY (date, symbol)
);
CREATE TABLE IF NOT EXISTS orders (
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    notional REAL NOT NULL,
    status TEXT NOT NULL,
    order_id TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS events (
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    detail TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: Path | str = JOURNAL_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def log_equity(self, date: str, equity: float, drawdown: float,
                   benchmark_price: float | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO equity_log VALUES (?, ?, ?, ?)",
            (date, equity, drawdown, benchmark_price),
        )
        self.conn.commit()

    def peak_equity(self) -> float | None:
        row = self.conn.execute("SELECT MAX(equity) FROM equity_log").fetchone()
        return row[0]

    def log_targets(self, date: str, weights: dict[str, float],
                    notionals: dict[str, float]) -> None:
        self.conn.execute("DELETE FROM targets WHERE date = ?", (date,))
        self.conn.executemany(
            "INSERT INTO targets VALUES (?, ?, ?, ?)",
            [(date, sym, w, notionals[sym]) for sym, w in weights.items()],
        )
        self.conn.commit()

    def log_order(self, symbol: str, side: str, notional: float, status: str,
                  order_id: str = "", detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), symbol, side, notional, status, order_id, detail),
        )
        self.conn.commit()

    def log_event(self, type_: str, detail: str = "") -> None:
        self.conn.execute("INSERT INTO events VALUES (?, ?, ?)", (_now(), type_, detail))
        self.conn.commit()

    def last_event_date(self, type_: str) -> str | None:
        """Date (YYYY-MM-DD, UTC) of the most recent event of this type."""
        row = self.conn.execute(
            "SELECT MAX(ts) FROM events WHERE type = ?", (type_,)
        ).fetchone()
        return row[0][:10] if row and row[0] else None

    def equity_history(self) -> pd.DataFrame:
        return pd.read_sql_query(
            "SELECT * FROM equity_log ORDER BY date", self.conn, parse_dates=["date"]
        )
