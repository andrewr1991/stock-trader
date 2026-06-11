"""Ablation: turn the brain upgrades on one at a time and compare
out-of-sample walk-forward results, so each change earns its place.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import functools

import pandas as pd

from trader.backtest.engine import buy_and_hold
from trader.backtest.metrics import summary
from trader.backtest.walkforward import walk_forward
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.momentum import MomentumStrategy

GRID = {"lookback_days": [126, 189, 252], "top_n": [5, 10, 15]}

VARIANTS = {
    "classic": dict(vol_adjusted=False, inverse_vol_weights=False, hold_buffer=1.0),
    "+ buffer": dict(vol_adjusted=False, inverse_vol_weights=False, hold_buffer=2.0),
    "+ vol-adj rank": dict(vol_adjusted=True, inverse_vol_weights=False, hold_buffer=2.0),
    "+ inv-vol weights": dict(vol_adjusted=True, inverse_vol_weights=True, hold_buffer=2.0),
}


def factory(fixed: dict, **params):
    return MomentumStrategy(**fixed, **params)


def main():
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2000-01-01")

    rows = []
    first_equity = None
    for name, fixed in VARIANTS.items():
        for k in (1, 3):
            wf = walk_forward(
                prices, functools.partial(factory, fixed), GRID,
                train_years=5, test_years=1,
                cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=k,
            )
            if first_equity is None:
                first_equity = wf.equity
            bench = buy_and_hold(
                prices[BENCHMARK].loc[wf.equity.index[0]:], initial_capital=INITIAL_CAPITAL
            ).equity
            stats = summary(wf.equity, bench)
            rows.append({
                "variant": name,
                "ensemble_k": k,
                "CAGR": f"{stats['CAGR']:.1%}",
                "Excess": f"{stats['Excess CAGR']:+.1%}",
                "Sharpe": f"{stats['Sharpe']:.2f}",
                "MaxDD": f"{stats['Max Drawdown']:.1%}",
                "Vol": f"{stats['Volatility']:.1%}",
            })
            print(f"done: {name} (k={k})")

    print("\nOut-of-sample walk-forward, 2005-2026, after costs:")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
