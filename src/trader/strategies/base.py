"""Strategy interface.

A strategy converts a price history into target portfolio weights at each
rebalance date. Signals must be causal: weights dated D may only use prices
up to and including D (the backtest engine executes at D's close).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "strategy"

    @abstractmethod
    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Return target weights.

        Index: rebalance dates (subset of prices.index).
        Columns: tickers. Rows may sum to < 1.0; the remainder is cash.
        """

    def params(self) -> dict:
        """Parameters for logging/reporting."""
        return {}


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each month present in the index."""
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([index.year, index.month]).last().values)


def week_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last trading day of each ISO week present in the index (usually Friday)."""
    iso = index.isocalendar()
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby([iso["year"].values, iso["week"].values]).last().values)


def rebalance_dates(index: pd.DatetimeIndex, freq: str = "M") -> pd.DatetimeIndex:
    """Dispatch on cadence: 'M' = month-end, 'W' = week-end."""
    if freq == "W":
        return week_end_dates(index)
    if freq == "M":
        return month_end_dates(index)
    raise ValueError(f"unknown rebalance freq '{freq}' (use 'M' or 'W')")
