"""Challenger diagnostics: rolling Sharpe, rolling volatility, exposure
history, and momentum-vs-mean-reversion sleeve attribution.

Backtest-based (full history) so the picture is stable; the live journal
remains the source of truth for the actual paper track record. Writes
reports/challenger_diagnostics.png + .md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from trader.backtest.engine import run_backtest
from trader.backtest.metrics import rolling_sharpe, rolling_vol
from trader.bots import challenger_bot
from trader.config import (
    BENCHMARK,
    CASH_ETF,
    CHALLENGER_VOL_TARGET,
    COST_BPS,
    INITIAL_CAPITAL,
    REPORTS_DIR,
    UNIVERSE,
)
from trader.data.loader import load_prices
from trader.strategies.challenger import ChallengerStrategy

PNG_PATH = REPORTS_DIR / "challenger_diagnostics.png"
MD_PATH = REPORTS_DIR / "challenger_diagnostics.md"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2000-01-01")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start=args.start)

    # Combined challenger (live params) + its two standalone sleeves.
    challenger = challenger_bot().strategy()
    cw = challenger.generate_weights(prices)
    cres = run_backtest(prices, cw, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)

    probe = ChallengerStrategy()  # default sleeves (no regime/vol overlay)
    mom_w = probe.momentum.generate_weights(prices)
    mr_w = probe.mean_reversion.generate_weights(prices)
    mom_res = run_backtest(prices, mom_w, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    mr_res = run_backtest(prices, mr_w, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)

    exposure = (1.0 - cw.get(CASH_ETF, 0.0)).clip(0, 1) if CASH_ETF in cw.columns else cw.sum(axis=1)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    rolling_sharpe(cres.returns).plot(ax=axes[0, 0])
    axes[0, 0].axhline(0, color="gray", lw=0.8)
    axes[0, 0].set_title("Rolling 1-year Sharpe (challenger)")
    axes[0, 0].grid(True, alpha=0.3)

    rolling_vol(cres.returns).plot(ax=axes[0, 1], label="realized")
    axes[0, 1].axhline(CHALLENGER_VOL_TARGET, color="red", ls="--", label=f"{CHALLENGER_VOL_TARGET:.0%} target")
    axes[0, 1].set_title("Rolling 1-year volatility (challenger)")
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)

    exposure.plot(ax=axes[1, 0], drawstyle="steps-post")
    axes[1, 0].set_ylim(0, 1.05)
    axes[1, 0].set_title("Risk exposure (1 - cash weight) over time")
    axes[1, 0].grid(True, alpha=0.3)

    mom_res.equity.plot(ax=axes[1, 1], label="momentum sleeve (standalone)")
    mr_res.equity.plot(ax=axes[1, 1], label="mean-reversion sleeve (standalone)")
    cres.equity.plot(ax=axes[1, 1], label="challenger (combined+overlay)", lw=2, color="black")
    axes[1, 1].set_yscale("log")
    axes[1, 1].set_title("Sleeve attribution (standalone sleeves vs combined)")
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=110)

    avg_exp = float(exposure.mean())
    MD_PATH.write_text(
        f"# Challenger diagnostics\n\n"
        f"Backtest {cres.equity.index[0].date()} to {cres.equity.index[-1].date()}, "
        f"after {COST_BPS:.0f} bps.\n\n"
        f"- Average risk exposure: {avg_exp:.0%} (rest in T-bills via vol targeting + regime)\n"
        f"- Standalone sleeve CAGRs and the combined curve are charted below.\n\n"
        f"![diagnostics](challenger_diagnostics.png)\n\n"
        f"Standalone sleeves carry NO regime/vol overlay — they show each "
        f"signal's raw character. The combined challenger applies the regime "
        f"model and 12% vol target on top, which is why it sits lower and "
        f"smoother than the raw momentum sleeve.\n"
    )
    print(f"Wrote {PNG_PATH} and {MD_PATH}")
    print(f"Average challenger risk exposure: {avg_exp:.1%}")


if __name__ == "__main__":
    main()
