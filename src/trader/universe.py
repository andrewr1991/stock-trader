"""Tradable-universe abstraction.

The backtests in this repo run over `config.UNIVERSE` — today's surviving large
caps — which carries survivorship bias (delisted names like Lehman/Enron are
absent). This module is the plug-in point for fixing that: a `Universe`
provides the tradable set *as of a date*, so a real historical index-membership
file can be dropped in later without touching strategy code.

What this DOES give you now:
  - A clean by-date membership interface (the spec's "support different
    universes by date").
  - `StaticUniverse` — the current behavior (every name is always a member);
    the champion uses this and is unchanged.
  - `PointInTimeUniverse` — loads dated membership intervals from a CSV.
  - `apply_universe(prices, universe)` — masks a price panel so a name is NaN
    on dates it isn't a member; the existing strategies already skip NaNs, so
    no strategy signature changes.

What it does NOT give you yet (be honest): a full survivorship fix also needs
PRICE history for delisted names, which yfinance does not provide. Point a
paid feed (CRSP/Norgate/etc.) at both the membership CSV and the price loader
to complete it. The framework is ready; the data is the missing piece.
"""
from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from trader.config import UNIVERSE


class Universe(ABC):
    @abstractmethod
    def members_asof(self, date) -> set[str]:
        """Tickers that are tradable as of `date`."""

    @abstractmethod
    def all_tickers(self) -> list[str]:
        """Every ticker that is ever a member (for data loading)."""

    def member_mask(self, index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
        """Boolean DataFrame (index x tickers): True where a member as of the date."""
        rows = [
            [t in self.members_asof(d) for t in tickers]
            for d in index
        ]
        return pd.DataFrame(rows, index=index, columns=tickers, dtype=bool)


class StaticUniverse(Universe):
    """Every name is always a member — reproduces the original behavior."""

    def __init__(self, tickers: list[str]):
        self._tickers = list(tickers)
        self._set = set(tickers)

    def members_asof(self, date) -> set[str]:
        return self._set

    def all_tickers(self) -> list[str]:
        return list(self._tickers)

    def member_mask(self, index: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
        # Short-circuit: all members always -> all True (fast path).
        return pd.DataFrame(True, index=index, columns=tickers, dtype=bool)


class PointInTimeUniverse(Universe):
    """Membership from dated intervals: {ticker: [(start, end_or_None), ...]}.

    CSV schema (header required): `ticker,start,end`
      - dates as YYYY-MM-DD
      - blank `end` means "still a member"
    One row per membership spell (a name may leave and rejoin).
    """

    def __init__(self, intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp | None]]]):
        self._intervals = intervals

    @classmethod
    def from_csv(cls, path: str | Path) -> "PointInTimeUniverse":
        intervals: dict[str, list] = {}
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                t = row["ticker"].strip()
                start = pd.Timestamp(row["start"].strip())
                end = pd.Timestamp(row["end"].strip()) if row.get("end", "").strip() else None
                intervals.setdefault(t, []).append((start, end))
        return cls(intervals)

    def members_asof(self, date) -> set[str]:
        d = pd.Timestamp(date)
        return {
            t for t, spells in self._intervals.items()
            if any(s <= d and (e is None or d <= e) for s, e in spells)
        }

    def all_tickers(self) -> list[str]:
        return sorted(self._intervals)


def default_universe() -> Universe:
    """The system default: today's survivor list, static. Champion uses this."""
    return StaticUniverse(UNIVERSE)


def apply_universe(prices: pd.DataFrame, universe: Universe) -> pd.DataFrame:
    """Mask `prices` so a universe name is NaN on dates it isn't a member.

    Columns not owned by the universe (e.g. the benchmark and cash ETF) pass
    through untouched. Strategies already ignore NaN names, so membership is
    enforced without changing any strategy code.
    """
    owned = [c for c in prices.columns if c in set(universe.all_tickers())]
    if not owned:
        return prices
    mask = universe.member_mask(prices.index, owned)
    out = prices.copy()
    out[owned] = prices[owned].where(mask)
    return out
