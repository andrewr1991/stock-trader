"""Monthly learning refresh with a champion/challenger promotion gate.

This is the PARAMETER-level gate that runs inside EACH bot independently
(distinct from the bot-level Champion-vs-Challenger A/B test between the two
live accounts). For the selected bot:

1. Re-run the walk-forward on the freshest data; the latest fold's top-k
   parameter ensemble is the CANDIDATE.
2. The ensemble currently in the bot's params file is the INCUMBENT.
3. The candidate is promoted only if it differs from the incumbent AND its
   simulated after-cost Sharpe over the trailing 12 months beats it. Ties and
   losses keep the incumbent — switching has costs, so the burden of proof is
   on the newcomer.

Every decision is logged to the bot's journal.

Usage:
    python scripts/run_monthly_refresh.py                   # champion
    python scripts/run_monthly_refresh.py --bot challenger
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse
import json

import pandas as pd

from trader.backtest.engine import run_backtest
from trader.backtest.metrics import sharpe
from trader.backtest.walkforward import walk_forward
from trader.bots import BotConfig, get_bot
from trader.config import BENCHMARK, CASH_ETF, COST_BPS, INITIAL_CAPITAL, UNIVERSE
from trader.data.loader import load_prices
from trader.live.journal import Journal

TRAILING_DAYS = 252


def trailing_sharpe(prices: pd.DataFrame, params_list: list[dict], bot: BotConfig) -> float:
    weights = bot.build_strategy(params_list).generate_weights(prices)
    result = run_backtest(prices, weights, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    return sharpe(result.returns.iloc[-TRAILING_DAYS:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="champion", choices=["champion", "challenger"])
    args = parser.parse_args()

    bot = get_bot(args.bot)
    journal = Journal(bot.journal_db)
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    print(f"[{bot.name}] Downloading fresh prices ...")
    prices = load_prices(tickers, start="2000-01-01", refresh=True)

    print(f"[{bot.name}] Running walk-forward to produce the candidate ...")
    wf = walk_forward(
        prices, bot.factory, bot.param_grid,
        train_years=5, test_years=1,
        cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=bot.ensemble_k,
    )
    candidate = wf.folds[-1].top_params
    incumbent = bot.load_params()

    def canon(p):
        return json.dumps(sorted(p, key=json.dumps), sort_keys=True)

    if canon(candidate) == canon(incumbent):
        journal.log_event("REFRESH", "candidate identical to incumbent; no change")
        print(f"[{bot.name}] Candidate identical to incumbent. Nothing to do.")
        return

    print(f"[{bot.name}] Candidate differs; comparing trailing 12-month Sharpe ...")
    s_incumbent = trailing_sharpe(prices, incumbent, bot)
    s_candidate = trailing_sharpe(prices, candidate, bot)
    detail = (
        f"incumbent {incumbent} sharpe={s_incumbent:.2f} vs "
        f"candidate {candidate} sharpe={s_candidate:.2f}"
    )
    print(f"  incumbent {s_incumbent:.2f}  {incumbent}")
    print(f"  candidate {s_candidate:.2f}  {candidate}")

    if pd.notna(s_candidate) and s_candidate > s_incumbent:
        bot.params_file.parent.mkdir(parents=True, exist_ok=True)
        bot.params_file.write_text(json.dumps(candidate, indent=2))
        journal.log_event("PROMOTION", detail)
        print(f"[{bot.name}] PROMOTED: candidate becomes the new live ensemble.")
    else:
        journal.log_event("RETAINED", detail)
        print(f"[{bot.name}] RETAINED: incumbent keeps its seat; candidate wasn't better.")


if __name__ == "__main__":
    main()
