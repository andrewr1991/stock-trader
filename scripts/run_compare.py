"""Champion vs Challenger comparison report.

Runs BOTH bots' strategies over identical price history through the shared
backtest engine (apples-to-apples, same costs and capital), computes the full
metric set, and writes:

    reports/champion_vs_challenger.csv
    reports/champion_vs_challenger.html   (table + embedded equity chart)

This is the backtest comparison (full history, rich metrics). The live paper
track records accumulate separately in each bot's journal and report.

Usage:
    python scripts/run_compare.py [--start 2000-01-01]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse
import base64
import csv
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from trader.backtest.engine import buy_and_hold, run_backtest
from trader.backtest.metrics import (
    annual_turnover,
    annual_vol,
    cagr,
    max_drawdown,
    sharpe,
    sortino,
    win_rate,
    TRADING_DAYS,
)
from trader.bots import champion_bot, challenger_bot
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, REPORTS_DIR, UNIVERSE
from trader.data.loader import load_prices

CSV_PATH = REPORTS_DIR / "champion_vs_challenger.csv"
HTML_PATH = REPORTS_DIR / "champion_vs_challenger.html"
PNG_PATH = REPORTS_DIR / "champion_vs_challenger.png"


def metrics_for(equity: pd.Series, turnover: pd.Series | None) -> dict:
    returns = equity.pct_change().fillna(0.0)
    return {
        "CAGR": cagr(equity),
        "Annual return": float(returns.mean() * TRADING_DAYS),
        "Sharpe": sharpe(returns),
        "Sortino": sortino(returns),
        "Volatility": annual_vol(returns),
        "Max drawdown": max_drawdown(equity),
        "Win rate (monthly)": win_rate(equity),
        "Annual turnover": annual_turnover(turnover),
    }


PCT_ROWS = {"CAGR", "Annual return", "Volatility", "Max drawdown",
            "Win rate (monthly)", "Annual turnover"}


def fmt(metric: str, value: float) -> str:
    if value != value:  # NaN
        return "—"
    return f"{value:.1%}" if metric in PCT_ROWS else f"{value:.2f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2000-01-01")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    print(f"Loading prices from {args.start} ...")
    prices = load_prices(tickers, start=args.start)

    champion = champion_bot()
    challenger = challenger_bot()

    print("Backtesting champion ...")
    champ_res = run_backtest(prices, champion.strategy().generate_weights(prices),
                             cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    print("Backtesting challenger ...")
    chal_res = run_backtest(prices, challenger.strategy().generate_weights(prices),
                            cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    spy_eq = buy_and_hold(prices[BENCHMARK].loc[champ_res.equity.index[0]:],
                          initial_capital=INITIAL_CAPITAL).equity

    cols = {
        "Champion (momentum)": metrics_for(champ_res.equity, champ_res.turnover),
        "Challenger (multi-sleeve)": metrics_for(chal_res.equity, chal_res.turnover),
        "SPY buy & hold": metrics_for(spy_eq, None),
    }
    metric_names = list(next(iter(cols.values())).keys())

    # CSV
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", *cols.keys()])
        for m in metric_names:
            writer.writerow([m, *(f"{cols[c][m]:.6f}" for c in cols)])
    print(f"Wrote {CSV_PATH}")

    # Chart
    fig, ax = plt.subplots(figsize=(11, 6))
    (champ_res.equity).plot(ax=ax, label="Champion (momentum)", linewidth=2)
    (chal_res.equity).plot(ax=ax, label="Challenger (multi-sleeve)", linewidth=2)
    spy_eq.plot(ax=ax, label="SPY buy & hold", linewidth=2, linestyle="--")
    ax.set_yscale("log")
    ax.set_ylabel("Equity ($, log scale)")
    ax.set_title("Champion vs Challenger (backtest, after costs)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PNG_PATH, dpi=120)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    b64 = base64.b64encode(buf.getvalue()).decode()

    # HTML
    header = "".join(f"<th>{c}</th>" for c in cols)
    rows = ""
    for m in metric_names:
        cells = "".join(f"<td>{fmt(m, cols[c][m])}</td>" for c in cols)
        rows += f"<tr><th class='m'>{m}</th>{cells}</tr>"
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Champion vs Challenger</title>
<style>
 body{{font-family:system-ui,Arial,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-weight:600}} table{{border-collapse:collapse;width:100%;margin:1rem 0}}
 th,td{{border:1px solid #ddd;padding:8px 12px;text-align:right}}
 th.m{{text-align:left}} thead th{{background:#f4f4f4}}
 tr:nth-child(even){{background:#fafafa}} .note{{color:#666;font-size:.9em}}
 img{{width:100%;margin-top:1rem}}
</style></head><body>
<h1>Champion vs Challenger</h1>
<p class="note">Backtest over {champ_res.equity.index[0].date()} to {champ_res.equity.index[-1].date()},
after {COST_BPS:.0f} bps costs. Universe is today's survivors, so absolute numbers
are optimistic — read the columns relative to each other and to SPY.</p>
<table><thead><tr><th class="m">Metric</th>{header}</tr></thead><tbody>{rows}</tbody></table>
<img src="data:image/png;base64,{b64}" alt="Champion vs Challenger equity curves">
</body></html>"""
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {HTML_PATH}")

    print("\nSummary:")
    print(f"{'Metric':<20}" + "".join(f"{c:<28}" for c in cols))
    for m in metric_names:
        print(f"{m:<20}" + "".join(f"{fmt(m, cols[c][m]):<28}" for c in cols))


if __name__ == "__main__":
    main()
