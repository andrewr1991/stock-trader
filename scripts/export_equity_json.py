"""Export monthly walk-forward equity curves as JSON (for charting).

Runs the walk-forward twice — once with the classic brain (raw momentum,
equal weights, no buffer, winner-take-all params) and once with the improved
brain (vol-adjusted, inverse-vol weights, rank buffer, top-3 ensemble) — so
the two can be compared out-of-sample on identical data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trader.backtest.engine import buy_and_hold
from trader.backtest.walkforward import walk_forward
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.momentum import MomentumStrategy

GRID = {"lookback_days": [126, 189, 252], "top_n": [5, 10, 15]}


def classic_factory(**params):
    return MomentumStrategy(
        vol_adjusted=False, inverse_vol_weights=False, hold_buffer=1.0, **params
    )


def main():
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2000-01-01")

    improved = walk_forward(
        prices, MomentumStrategy, GRID,
        train_years=5, test_years=1,
        cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=3,
    )
    classic = walk_forward(
        prices, classic_factory, GRID,
        train_years=5, test_years=1,
        cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=1,
    )
    bench = buy_and_hold(
        prices[BENCHMARK].loc[improved.equity.index[0]:], initial_capital=INITIAL_CAPITAL
    ).equity

    m_improved = improved.equity.resample("ME").last().dropna()
    m_classic = classic.equity.resample("ME").last().reindex(m_improved.index).ffill()
    m_bench = bench.resample("ME").last().reindex(m_improved.index).ffill()

    out = {
        "dates": [d.strftime("%Y-%m") for d in m_improved.index],
        "improved": [round(float(v)) for v in m_improved.values],
        "classic": [round(float(v)) for v in m_classic.values],
        "spy": [round(float(v)) for v in m_bench.values],
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
