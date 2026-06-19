"""Walk-forward validation for either bot's strategy.

Parameters are re-chosen each year using only the previous `--train-years`
of data, then applied to the following year out-of-sample. The stitched
out-of-sample curve is the number to trust. No look-ahead: selection uses
training windows only, evaluation uses the untouched test window.

Usage:
    python scripts/run_walkforward.py                          # champion
    python scripts/run_walkforward.py --bot challenger
    python scripts/run_walkforward.py --start 2000-01-01 --save-live-params
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from trader.backtest.engine import buy_and_hold
from trader.backtest.metrics import format_summary, summary
from trader.backtest.walkforward import walk_forward
from trader.bots import get_bot
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, REPORTS_DIR, UNIVERSE
from trader.data.loader import load_prices


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="champion", choices=["champion", "challenger"])
    parser.add_argument("--start", default="2007-01-01")
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--test-years", type=int, default=1)
    parser.add_argument("--ensemble-k", type=int, default=None,
                        help="capital split across top-k param sets (default: bot's own)")
    parser.add_argument("--save-live-params", action="store_true",
                        help="write the latest fold's ensemble to the bot's params file")
    args = parser.parse_args()

    bot = get_bot(args.bot)
    ensemble_k = args.ensemble_k if args.ensemble_k is not None else bot.ensemble_k

    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    print(f"[{bot.name}] Loading prices for {len(tickers)} tickers from {args.start} ...")
    prices = load_prices(tickers, start=args.start)

    n_combos = 1
    for v in bot.param_grid.values():
        n_combos *= len(v)
    print(f"[{bot.name}] Running walk-forward: {n_combos} parameter combos, "
          f"{args.train_years}y train / {args.test_years}y test ...")

    wf = walk_forward(
        prices,
        bot.factory,
        bot.param_grid,
        train_years=args.train_years,
        test_years=args.test_years,
        cost_bps=COST_BPS,
        initial_capital=INITIAL_CAPITAL,
        ensemble_k=ensemble_k,
    )

    print("\nParameters chosen per fold (each chosen WITHOUT seeing its test year):")
    print(wf.params_by_fold().to_string(index=False))

    bench_equity = buy_and_hold(
        prices[BENCHMARK].loc[wf.equity.index[0] :], initial_capital=INITIAL_CAPITAL
    ).equity

    print("\n=== Out-of-sample (stitched test windows) ===")
    print(format_summary(summary(wf.equity, bench_equity)))

    latest = wf.folds[-1].top_params
    print(f"\nLive candidate parameter ensemble (from most recent fold): {latest}")
    if args.save_live_params:
        import json

        bot.params_file.parent.mkdir(parents=True, exist_ok=True)
        bot.params_file.write_text(json.dumps(latest, indent=2))
        print(f"Saved to {bot.params_file} — the {bot.name} live loop will trade this.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    wf.equity.plot(ax=ax, label=f"{bot.name} (out-of-sample)")
    bench_equity.plot(ax=ax, label=f"{BENCHMARK} buy & hold")
    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale)")
    ax.set_title(f"Walk-forward out-of-sample vs. SPY ({bot.name})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out = REPORTS_DIR / f"walkforward_{bot.name}_vs_spy.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"Chart saved to {out}")


if __name__ == "__main__":
    main()
