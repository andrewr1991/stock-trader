"""Strategy interface.

A strategy converts a price history into target portfolio weights at each
rebalance date. Signals must be causal: weights dated D may only use prices
up to and including D (the backtest engine executes at D's close).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

TRADING_DAYS = 252


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


def exante_vol(daily_ret: pd.DataFrame, weights: pd.Series, vol_window: int,
               asof: pd.Timestamp) -> float:
    """Annualized ex-ante volatility of a fully-invested book.

    Uses the trailing covariance of the held names up to (and including)
    `asof` — causal, no look-ahead. Weights are normalized to sum to 1 so the
    result is the vol of the fully-invested book (callers scale from there).
    Shared by the challenger and multi-asset sleeves.
    """
    held = weights[weights > 0].index
    window = daily_ret[held].loc[:asof].iloc[-vol_window:].dropna(axis=1)
    held = window.columns
    if len(held) == 0 or len(window) < 2:
        return float("nan")
    w = weights[held].to_numpy(dtype=float)
    w = w / w.sum()
    cov = window.cov().to_numpy() * TRADING_DAYS
    var = float(w @ cov @ w)
    return float(np.sqrt(var)) if var > 0 else float("nan")
