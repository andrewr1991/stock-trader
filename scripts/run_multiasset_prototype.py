"""Prototype evaluation of the multi-asset trend sleeve (design "B").

Reports backtest + out-of-sample walk-forward metrics, crisis-year behavior
(the selling point — does it sidestep equity bear markets?), beta to SPY, and
its return correlation to the existing equity Challenger (low correlation =
genuine diversifier worth combining).

reports/multiasset_prototype.png + .md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from trader.backtest.engine import buy_and_hold, run_backtest
from trader.backtest.metrics import beta_alpha, conditional_beta, summary
from trader.backtest.walkforward import walk_forward
from trader.bots import challenger_bot
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, REPORTS_DIR, UNIVERSE
from trader.data.loader import load_prices
from trader.strategies.trend_multi_asset import DEFAULT_ASSETS, MultiAssetTrendStrategy

PNG_PATH = REPORTS_DIR / "multiasset_prototype.png"
MD_PATH = REPORTS_DIR / "multiasset_prototype.md"
START = "2005-01-01"  # clean window where all four ETFs exist (GLD from 2004-11)
GRID = {"trend_ma_days": [150, 200, 250]}


def crisis_returns(equity: pd.Series) -> dict:
    yr = equity.resample("YE").last().pct_change()
    yr.index = yr.index.year
    return {y: yr.get(y, float("nan")) for y in (2008, 2018, 2020, 2022)}


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    etfs = list(DEFAULT_ASSETS) + [BENCHMARK, CASH_ETF]
    prices = load_prices(sorted(set(etfs)), start=START, refresh=True)

    strat = MultiAssetTrendStrategy()
    res = run_backtest(prices, strat.generate_weights(prices),
                       cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    spy_eq = buy_and_hold(prices[BENCHMARK].loc[res.equity.index[0]:],
                          initial_capital=INITIAL_CAPITAL).equity
    spy_ret = prices[BENCHMARK].pct_change()

    stats = summary(res.equity, spy_eq)
    beta, _ = beta_alpha(res.returns, spy_ret)
    down_beta = conditional_beta(res.returns, spy_ret, side="down")

    # Out-of-sample walk-forward over the trend lookback.
    wf = walk_forward(prices, MultiAssetTrendStrategy, GRID,
                      train_years=4, test_years=1, cost_bps=COST_BPS,
                      initial_capital=INITIAL_CAPITAL, ensemble_k=1)
    oos = summary(wf.equity, buy_and_hold(
        prices[BENCHMARK].loc[wf.equity.index[0]:], initial_capital=INITIAL_CAPITAL).equity)

    # Correlation to the equity challenger over the shared window.
    eq_tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    eq_prices = load_prices(eq_tickers, start=START)
    ch_res = run_backtest(eq_prices, challenger_bot().strategy().generate_weights(eq_prices),
                          cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    joint = pd.concat([res.returns.rename("MA"), ch_res.returns.rename("CH")],
                      axis=1, join="inner").dropna()
    corr_d = joint["MA"].corr(joint["CH"])
    m = joint.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    corr_m = m["MA"].corr(m["CH"])

    cr = crisis_returns(res.equity)
    cr_spy = crisis_returns(spy_eq)

    fig, ax = plt.subplots(figsize=(11, 6))
    res.equity.plot(ax=ax, label="multi-asset trend", lw=2)
    spy_eq.plot(ax=ax, label="SPY buy & hold", lw=2, ls="--")
    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log)")
    ax.set_title("Multi-asset trend sleeve vs SPY (backtest, after costs)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=120)

    def pct(x):
        return "n/a" if x != x else f"{x:+.1%}"

    MD_PATH.write_text(
        f"# Multi-asset trend sleeve — prototype\n\n"
        f"Assets: {', '.join(DEFAULT_ASSETS)} + cash. Backtest from {START}, after {COST_BPS:.0f} bps.\n\n"
        f"## Backtest (full history)\n"
        f"| Metric | Multi-asset | SPY |\n|---|---|---|\n"
        f"| CAGR | {stats['CAGR']:.1%} | {stats['Benchmark CAGR']:.1%} |\n"
        f"| Sharpe | {stats['Sharpe']:.2f} | — |\n"
        f"| Volatility | {stats['Volatility']:.1%} | — |\n"
        f"| Max drawdown | {stats['Max Drawdown']:.1%} | — |\n"
        f"| Beta to SPY | {beta:.2f} | — |\n"
        f"| Down-market beta | {down_beta:.2f} | — |\n\n"
        f"## Out-of-sample walk-forward\n"
        f"CAGR {oos['CAGR']:.1%}, Sharpe {oos['Sharpe']:.2f}, "
        f"vol {oos['Volatility']:.1%}, maxDD {oos['Max Drawdown']:.1%}, "
        f"excess vs SPY {oos['Excess CAGR']:+.1%}.\n\n"
        f"## Crisis years (the point of the sleeve)\n"
        f"| Year | Multi-asset | SPY |\n|---|---|---|\n"
        + "".join(f"| {y} | {pct(cr[y])} | {pct(cr_spy[y])} |\n" for y in (2008, 2018, 2020, 2022))
        + f"\n## Diversification vs the equity challenger\n"
        f"Return correlation: daily {corr_d:.2f}, monthly {corr_m:.2f}. "
        f"Low correlation = combining the two would smooth the blended book.\n\n"
        f"![multi-asset](multiasset_prototype.png)\n"
    )

    print(f"Backtest: CAGR {stats['CAGR']:.1%}, Sharpe {stats['Sharpe']:.2f}, "
          f"maxDD {stats['Max Drawdown']:.1%}, beta {beta:.2f} (down {down_beta:.2f})")
    print(f"OOS walk-forward: CAGR {oos['CAGR']:.1%}, Sharpe {oos['Sharpe']:.2f}, "
          f"maxDD {oos['Max Drawdown']:.1%}")
    print("Crisis years (MA vs SPY): " +
          ", ".join(f"{y} {pct(cr[y])}/{pct(cr_spy[y])}" for y in (2008, 2020, 2022)))
    print(f"Correlation to challenger: daily {corr_d:.2f}, monthly {corr_m:.2f}")
    print(f"Wrote {PNG_PATH} and {MD_PATH}")


if __name__ == "__main__":
    main()
