"""Experiment ledger — the lean part of a "research coordinator" that's
actually worth having: a single queryable record of every idea we've tried,
who proposed it, and how it fared out-of-sample.

Deliberately NOT a multi-LLM orchestration platform. The bottleneck in this
project was never generating ideas — it was validating them, and the
walk-forward ablation already does that. This just remembers the verdicts so
we don't re-litigate dead ideas. Answers questions like:
  - "Have we already tested risk-adjusted momentum?"
  - "What killed weekly mean reversion?"
  - "Which ideas came from Claude vs ChatGPT, and which shipped?"

Storage is one SQLite table; `to_markdown()` renders a browsable view.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

import pandas as pd

from trader.config import PROJECT_ROOT

LEDGER_DB = PROJECT_ROOT / "data" / "experiment_ledger.db"

# What ultimately happened to an idea:
DECISIONS = {
    "shipped",    # adopted as default behavior
    "flag",       # implemented but kept OFF by default (tested, didn't win)
    "rejected",   # tried and not adopted
    "prototype",  # built and evaluated, not wired into a live bot
    "deferred",   # discussed, not yet tested
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    idea TEXT NOT NULL,
    area TEXT,
    proposed_by TEXT,
    decision TEXT NOT NULL,
    result TEXT,
    reason TEXT,
    ref TEXT
);
"""


@dataclass
class Experiment:
    idea: str
    decision: str
    area: str = ""
    proposed_by: str = ""
    result: str = ""
    reason: str = ""
    ref: str = ""
    date: str = ""

    def __post_init__(self):
        if self.decision not in DECISIONS:
            raise ValueError(f"decision must be one of {sorted(DECISIONS)}, got '{self.decision}'")
        self.date = self.date or _date.today().isoformat()


class Ledger:
    def __init__(self, path: Path | str = LEDGER_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def add(self, exp: Experiment) -> int:
        cur = self.conn.execute(
            "INSERT INTO experiments (date, idea, area, proposed_by, decision, result, reason, ref)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (exp.date, exp.idea, exp.area, exp.proposed_by, exp.decision, exp.result,
             exp.reason, exp.ref),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def all(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM experiments ORDER BY date, id", self.conn)

    def search(self, term: str) -> pd.DataFrame:
        like = f"%{term}%"
        return pd.read_sql_query(
            "SELECT * FROM experiments WHERE idea LIKE ? OR area LIKE ? OR result LIKE ?"
            " OR reason LIKE ? OR proposed_by LIKE ? ORDER BY date, id",
            self.conn, params=(like, like, like, like, like),
        )

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0])

    def to_markdown(self) -> str:
        df = self.all()
        if df.empty:
            return "# Experiment ledger\n\n_No experiments recorded yet._\n"

        by_decision = df["decision"].value_counts().to_dict()
        by_proposer = df["proposed_by"].replace("", "unknown").value_counts().to_dict()
        tally = "  ·  ".join(f"{k}: {v}" for k, v in by_decision.items())
        proposers = "  ·  ".join(f"{k}: {v}" for k, v in by_proposer.items())

        lines = [
            "# Experiment ledger",
            "",
            f"_{len(df)} experiments · {tally}_",
            "",
            f"_By proposer: {proposers}_",
            "",
            "| Date | Idea | Area | By | Decision | Result | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
        for _, r in df.iterrows():
            cells = [r["date"], r["idea"], r["area"] or "", r["proposed_by"] or "",
                     r["decision"], (r["result"] or "").replace("|", "/"),
                     (r["reason"] or "").replace("|", "/")]
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        lines.append("")
        return "\n".join(lines)
