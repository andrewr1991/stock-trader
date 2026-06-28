"""Generate a bot's performance report: equity vs SPY since inception.

Reads the bot's live journal (equity marks logged by every daily run) and
writes its report .md + .png. The daily workflow commits both, so the latest
report is always visible on GitHub.

Usage:
    python scripts/run_report.py                  # champion
    python scripts/run_report.py --bot challenger
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from trader.backtest.metrics import max_drawdown, sharpe
from trader.bots import BOT_NAMES, get_bot
from trader.config import BENCHMARK, REPORTS_DIR
from trader.data.loader import load_prices
from trader.live.journal import Journal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="champion", choices=BOT_NAMES)
    args = parser.parse_args()

    bot = get_bot(args.bot)
    md_path = bot.report_md
    png_path = bot.report_png
    png_name = png_path.name
    title = f"{bot.name.capitalize()} bot vs SPY (paper account)"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df = Journal(bot.journal_db).equity_history()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if len(df) < 2:
        md_path.write_text(
            f"# {title}\n\n_Last updated: {stamp}_\n\n"
            f"Not enough history yet ({len(df)} equity mark(s) logged). "
            f"The chart appears after the second trading day.\n"
        )
        print(f"[{bot.name}] Only {len(df)} equity rows; wrote placeholder report.")
        return

    df = df.sort_values("date").set_index("date")
    start = df.index[0] - pd.Timedelta(days=7)
    spy = load_prices([BENCHMARK], start=start.strftime("%Y-%m-%d"), refresh=True)[BENCHMARK]
    spy.index = spy.index.normalize()
    spy_aligned = spy.reindex(df.index.normalize(), method="ffill")

    robot_norm = df["equity"] / df["equity"].iloc[0]
    spy_norm = (spy_aligned / spy_aligned.iloc[0]).set_axis(df.index)

    robot_ret = robot_norm.iloc[-1] - 1
    spy_ret = spy_norm.iloc[-1] - 1
    days_live = (df.index[-1] - df.index[0]).days
    robot_dd = max_drawdown(df["equity"])
    robot_sharpe = sharpe(robot_norm.pct_change().dropna()) if len(df) >= 30 else None

    fig, ax = plt.subplots(figsize=(10, 5))
    (robot_norm * 100).plot(ax=ax, label=bot.name, linewidth=2)
    (spy_norm * 100).plot(ax=ax, label="SPY buy & hold", linewidth=2, linestyle="--")
    ax.set_ylabel("Growth of 100 (paper)")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)

    sharpe_row = (
        f"| Sharpe (since inception) | {robot_sharpe:.2f} | — |\n" if robot_sharpe is not None
        else "| Sharpe | _needs 30+ days_ | — |\n"
    )
    md_path.write_text(
        f"# {title}\n\n"
        f"_Last updated: {stamp} · live for {days_live} days · "
        f"equity ${df['equity'].iloc[-1]:,.0f}_\n\n"
        f"| Metric | {bot.name} | SPY |\n|---|---|---|\n"
        f"| Total return | {robot_ret:+.2%} | {spy_ret:+.2%} |\n"
        f"| Excess vs SPY | {robot_ret - spy_ret:+.2%} | — |\n"
        f"| Max drawdown | {robot_dd:.2%} | — |\n"
        f"{sharpe_row}\n"
        f"![{bot.name} vs SPY]({png_name})\n\n"
        f"Reminder: these strategies trail the index for months at a time "
        f"even when working. Judge on 3-6 months minimum, not weeks.\n"
    )
    print(f"[{bot.name}] Report: {robot_ret:+.2%} vs SPY {spy_ret:+.2%} over {days_live} days.")


if __name__ == "__main__":
    main()
