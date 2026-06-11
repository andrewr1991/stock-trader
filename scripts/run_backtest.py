"""Backtest the momentum strategy vs. SPY buy-and-hold.

Usage:
    python scripts/run_backtest.py [--start 2007-01-01] [--no-trend-filter] [--refresh]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from trader.backtest.engine import buy_and_hold, run_backtest
from trader.backtest.metrics import format_summary, summary
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, REPORTS_DIR, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.momentum import MomentumStrategy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2007-01-01")
    parser.add_argument("--no-trend-filter", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="re-download price data")
    args = parser.parse_args()

    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    print(f"Loading prices for {len(tickers)} tickers from {args.start} ...")
    prices = load_prices(tickers, start=args.start, refresh=args.refresh)
    print(f"  {len(prices)} trading days, {prices.index[0].date()} -> {prices.index[-1].date()}")

    strategy = MomentumStrategy(use_trend_filter=not args.no_trend_filter)
    print(f"\nStrategy: {strategy.name} {strategy.params()}")

    weights = strategy.generate_weights(prices)
    result = run_backtest(prices, weights, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    bench = buy_and_hold(prices[BENCHMARK], initial_capital=INITIAL_CAPITAL)

    print(f"\n=== {strategy.name} (after {COST_BPS:.0f} bps costs) ===")
    print(format_summary(summary(result.equity, bench.equity)))
    print(f"  {'Total costs':<16} ${result.total_costs:>10,.0f}")

    print(f"\n=== {BENCHMARK} buy & hold ===")
    print(format_summary(summary(bench.equity)))

    print(
        "\nNOTE: universe is today's survivors -> absolute numbers are optimistic."
        "\nUse these results to compare strategies, not to forecast returns."
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    result.equity.plot(ax=ax, label=f"{strategy.name}")
    bench.equity.plot(ax=ax, label=f"{BENCHMARK} buy & hold")
    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale)")
    ax.set_title("Momentum strategy vs. SPY")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out = REPORTS_DIR / "backtest_momentum_vs_spy.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"\nChart saved to {out}")


if __name__ == "__main__":
    main()
