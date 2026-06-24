"""Ablation: monthly vs weekly mean-reversion cadence inside the challenger.

Mean reversion is a short-horizon effect, so weekly rebalancing should capture
more of it — but at ~5x the trading. This runs both cadences out-of-sample
through the walk-forward (after costs) so the turnover penalty is paid
honestly. Weekly only earns the default if it wins net of costs.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from trader.backtest.engine import buy_and_hold, run_backtest
from trader.backtest.metrics import annual_turnover, summary
from trader.backtest.walkforward import walk_forward
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.challenger import CHALLENGER_GRID, ChallengerStrategy


def make_factory(mr_rebalance: str):
    def factory(**combo):
        return ChallengerStrategy(mr_rebalance=mr_rebalance, **combo)
    return factory


def main():
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2000-01-01")

    rows = []
    for cadence in ["M", "W"]:
        wf = walk_forward(
            prices, make_factory(cadence), CHALLENGER_GRID,
            train_years=5, test_years=1,
            cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=2,
        )
        bench = buy_and_hold(
            prices[BENCHMARK].loc[wf.equity.index[0]:], initial_capital=INITIAL_CAPITAL
        ).equity
        s = summary(wf.equity, bench)
        # Turnover from a single representative full-history backtest.
        rep = ChallengerStrategy(mr_rebalance=cadence)
        res = run_backtest(prices, rep.generate_weights(prices),
                           cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
        rows.append({
            "MR cadence": "weekly" if cadence == "W" else "monthly",
            "CAGR": f"{s['CAGR']:.1%}",
            "Excess": f"{s['Excess CAGR']:+.1%}",
            "Sharpe": f"{s['Sharpe']:.2f}",
            "Vol": f"{s['Volatility']:.1%}",
            "MaxDD": f"{s['Max Drawdown']:.1%}",
            "AnnTurnover": f"{annual_turnover(res.turnover):.0%}",
        })
        print(f"done: MR cadence={cadence}")

    print("\nMean-reversion cadence ablation — OOS walk-forward (2005-2026, after costs):")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nCurrent live default: monthly.")


if __name__ == "__main__":
    main()
