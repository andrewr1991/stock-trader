"""Beta-stability report for the challenger — validates its headline claim
(low market beta) by checking whether that beta is STABLE rather than a
flattering average.

Outputs:
  - static beta, and down-market vs up-market beta (the decision-relevant cut)
  - rolling 1y and 3y beta over time
  - per-fold out-of-sample beta dispersion across the walk-forward

reports/challenger_beta_stability.png + .md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from trader.backtest.engine import run_backtest
from trader.backtest.metrics import beta_alpha, conditional_beta, rolling_beta
from trader.backtest.walkforward import walk_forward
from trader.bots import challenger_bot
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, REPORTS_DIR, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.challenger import CHALLENGER_GRID, ChallengerStrategy

PNG_PATH = REPORTS_DIR / "challenger_beta_stability.png"
MD_PATH = REPORTS_DIR / "challenger_beta_stability.md"


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2000-01-01")
    spy_ret = prices[BENCHMARK].pct_change()

    res = run_backtest(prices, challenger_bot().strategy().generate_weights(prices),
                       cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    r = res.returns

    static_beta, _ = beta_alpha(r, spy_ret)
    down_beta = conditional_beta(r, spy_ret, side="down")
    up_beta = conditional_beta(r, spy_ret, side="up")
    rb1 = rolling_beta(r, spy_ret, window=252)
    rb3 = rolling_beta(r, spy_ret, window=756)

    # Per-fold OOS beta dispersion.
    wf = walk_forward(prices, ChallengerStrategy, CHALLENGER_GRID,
                      train_years=5, test_years=1, cost_bps=COST_BPS,
                      initial_capital=INITIAL_CAPITAL, ensemble_k=2)
    fold_betas = []
    for f in wf.folds:
        b, _ = beta_alpha(f.test_returns, spy_ret.reindex(f.test_returns.index))
        if not np.isnan(b):
            fold_betas.append((f.test_end.year, b))
    fb = pd.Series({y: b for y, b in fold_betas})

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    rb1.plot(ax=axes[0], label="rolling 1y", alpha=0.7)
    rb3.plot(ax=axes[0], label="rolling 3y", lw=2)
    axes[0].axhline(static_beta, color="black", ls="--", label=f"static {static_beta:.2f}")
    axes[0].axhline(down_beta, color="red", ls=":", label=f"down-market {down_beta:.2f}")
    axes[0].set_title("Challenger beta to SPY over time")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    fb.plot(kind="bar", ax=axes[1], color="steelblue")
    axes[1].axhline(fb.mean(), color="black", ls="--", label=f"mean {fb.mean():.2f}")
    axes[1].set_title("Per-fold out-of-sample beta")
    axes[1].set_xlabel("test-window year")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=110)

    MD_PATH.write_text(
        f"# Challenger beta stability\n\n"
        f"| Beta measure | Value |\n|---|---|\n"
        f"| Static (all days) | {static_beta:.2f} |\n"
        f"| Down-market days | {down_beta:.2f} |\n"
        f"| Up-market days | {up_beta:.2f} |\n"
        f"| Per-fold OOS mean | {fb.mean():.2f} |\n"
        f"| Per-fold OOS std | {fb.std():.2f} |\n"
        f"| Per-fold OOS range | {fb.min():.2f} to {fb.max():.2f} |\n\n"
        f"![beta stability](challenger_beta_stability.png)\n\n"
        f"The number that matters for a diversifier is **down-market beta** "
        f"({down_beta:.2f}): if it were much higher than the static beta "
        f"({static_beta:.2f}), the low-beta property would be illusory in "
        f"exactly the crises where it's supposed to help. Per-fold dispersion "
        f"(std {fb.std():.2f}) shows how stable the estimate is across the "
        f"walk-forward's independent test windows.\n"
    )
    print(f"static beta {static_beta:.2f} | down {down_beta:.2f} | up {up_beta:.2f}")
    print(f"per-fold OOS beta: mean {fb.mean():.2f}, std {fb.std():.2f}, "
          f"range {fb.min():.2f}..{fb.max():.2f}")
    print(f"Wrote {PNG_PATH} and {MD_PATH}")


if __name__ == "__main__":
    main()
