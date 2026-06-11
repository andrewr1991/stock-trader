"""Monthly learning refresh with a champion/challenger promotion gate.

1. Re-run the walk-forward on the freshest data; the latest fold's top-3
   parameter ensemble is the CHALLENGER.
2. The ensemble currently in data/live_params.json is the CHAMPION (it's
   what the robot trades).
3. The challenger is promoted only if it differs from the champion AND its
   simulated after-cost Sharpe over the trailing 12 months beats the
   champion's. Ties and losses keep the incumbent — switching has costs,
   so the burden of proof is on the newcomer.

Every decision (promoted or retained, with the numbers) is logged to the
journal, building the idea-loop's honest record.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json

import pandas as pd

from trader.backtest.engine import run_backtest
from trader.backtest.metrics import sharpe
from trader.backtest.walkforward import walk_forward
from trader.config import (
    BENCHMARK,
    CASH_ETF,
    COST_BPS,
    INITIAL_CAPITAL,
    LIVE_PARAMS_FILE,
    UNIVERSE,
)
from trader.data.loader import load_prices
from trader.live.journal import Journal
from trader.live.runner import DEFAULT_LIVE_PARAMS
from trader.strategies.ensemble import EnsembleStrategy
from trader.strategies.momentum import MomentumStrategy

PARAM_GRID = {"lookback_days": [126, 189, 252], "top_n": [5, 10, 15]}
TRAILING_DAYS = 252


def trailing_sharpe(prices: pd.DataFrame, params_list: list[dict]) -> float:
    ensemble = EnsembleStrategy([MomentumStrategy(**p) for p in params_list])
    weights = ensemble.generate_weights(prices)
    result = run_backtest(prices, weights, cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
    return sharpe(result.returns.iloc[-TRAILING_DAYS:])


def main():
    journal = Journal()
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    print("Downloading fresh prices ...")
    prices = load_prices(tickers, start="2000-01-01", refresh=True)

    print("Running walk-forward to produce the challenger ...")
    wf = walk_forward(
        prices, MomentumStrategy, PARAM_GRID,
        train_years=5, test_years=1,
        cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL, ensemble_k=3,
    )
    challenger = wf.folds[-1].top_params

    champion = (
        json.loads(LIVE_PARAMS_FILE.read_text())
        if LIVE_PARAMS_FILE.exists() else DEFAULT_LIVE_PARAMS
    )

    def canon(p):
        return json.dumps(sorted(p, key=json.dumps), sort_keys=True)

    if canon(challenger) == canon(champion):
        journal.log_event("REFRESH", "challenger identical to champion; no change")
        print("Challenger identical to champion. Nothing to do.")
        return

    print("Challenger differs; comparing trailing 12-month Sharpe ...")
    s_champion = trailing_sharpe(prices, champion)
    s_challenger = trailing_sharpe(prices, challenger)
    detail = (
        f"champion {champion} sharpe={s_champion:.2f} vs "
        f"challenger {challenger} sharpe={s_challenger:.2f}"
    )
    print(f"  champion   {s_champion:.2f}  {champion}")
    print(f"  challenger {s_challenger:.2f}  {challenger}")

    if pd.notna(s_challenger) and s_challenger > s_champion:
        LIVE_PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        LIVE_PARAMS_FILE.write_text(json.dumps(challenger, indent=2))
        journal.log_event("PROMOTION", detail)
        print("PROMOTED: challenger becomes the new champion.")
    else:
        journal.log_event("RETAINED", detail)
        print("RETAINED: champion keeps its seat; challenger wasn't better.")


if __name__ == "__main__":
    main()
