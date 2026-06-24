"""Ablation for the challenger v2 knobs: covariance lookback (20/60/90) and
market-breadth regime input (off/on). Each config is evaluated out-of-sample
via the existing walk-forward framework, so the verdict is honest — a change
only earns the default if it wins (or matches with a better risk profile)
where the optimizer never saw the test data.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from trader.backtest.engine import buy_and_hold
from trader.backtest.metrics import summary
from trader.backtest.walkforward import walk_forward
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.challenger import CHALLENGER_GRID, ChallengerStrategy

VOL_WINDOWS = [20, 60, 90]
BREADTH = [False, True]


def make_factory(vol_window: int, use_breadth: bool):
    def factory(**combo):
        return ChallengerStrategy(vol_window=vol_window, regime_use_breadth=use_breadth, **combo)
    return factory


def main():
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2000-01-01")

    rows = []
    for vw in VOL_WINDOWS:
        for br in BREADTH:
            wf = walk_forward(
                prices, make_factory(vw, br), CHALLENGER_GRID,
                train_years=5, test_years=1,
                cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=2,
            )
            bench = buy_and_hold(
                prices[BENCHMARK].loc[wf.equity.index[0]:], initial_capital=INITIAL_CAPITAL
            ).equity
            s = summary(wf.equity, bench)
            rows.append({
                "vol_window": vw,
                "breadth": "on" if br else "off",
                "CAGR": f"{s['CAGR']:.1%}",
                "Excess": f"{s['Excess CAGR']:+.1%}",
                "Sharpe": f"{s['Sharpe']:.2f}",
                "Vol": f"{s['Volatility']:.1%}",
                "MaxDD": f"{s['Max Drawdown']:.1%}",
            })
            print(f"done: vol_window={vw}, breadth={'on' if br else 'off'}")

    print("\nChallenger v2 ablation — out-of-sample walk-forward (2005-2026, after costs):")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nCurrent live default: vol_window=20, breadth=off.")


if __name__ == "__main__":
    main()
