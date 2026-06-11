"""Share-based daily backtest engine.

Positions drift between rebalances (no implicit daily rebalancing), trades
execute at the close of the signal date, and transaction costs are charged
on traded value. Deliberately simple and transparent — every number it
produces can be audited by hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series = field(init=False)
    turnover: pd.Series | None = None
    total_costs: float = 0.0

    def __post_init__(self):
        self.returns = self.equity.pct_change().fillna(0.0)


def run_backtest(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    cost_bps: float = 10.0,
    initial_capital: float = 100_000.0,
) -> BacktestResult:
    """Simulate trading `target_weights` (indexed by rebalance dates) over `prices`."""
    prices = prices.sort_index()
    tickers = list(target_weights.columns)
    px = prices[tickers]

    rebalance_dates = set(target_weights.index)
    cash = initial_capital
    shares = np.zeros(len(tickers))

    equity = pd.Series(index=prices.index, dtype=float)
    turnover = pd.Series(0.0, index=prices.index)
    total_costs = 0.0

    px_values = px.to_numpy()
    valid = ~np.isnan(px_values)

    for i, date in enumerate(prices.index):
        row = np.where(valid[i], px_values[i], 0.0)
        port_value = cash + float(shares @ row)

        if date in rebalance_dates:
            w = target_weights.loc[date].to_numpy(dtype=float)
            w = np.where(valid[i], w, 0.0)  # can't trade names with no price
            target_value = w * port_value
            current_value = shares * row
            traded = float(np.abs(target_value - current_value).sum())
            cost = traded * cost_bps / 10_000.0

            shares = np.divide(
                target_value, row, out=np.zeros_like(target_value), where=row > 0
            )
            cash = port_value - float(target_value.sum()) - cost
            total_costs += cost
            turnover.iloc[i] = traded / port_value if port_value > 0 else 0.0
            port_value = cash + float(shares @ row)

        equity.iloc[i] = port_value

    return BacktestResult(equity=equity, turnover=turnover, total_costs=total_costs)


def buy_and_hold(prices: pd.Series, initial_capital: float = 100_000.0) -> BacktestResult:
    """Benchmark: put everything in one asset on day one and never touch it."""
    series = prices.dropna()
    equity = initial_capital * series / series.iloc[0]
    return BacktestResult(equity=equity)
