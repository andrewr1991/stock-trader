"""Engine math, checkable by hand."""
import numpy as np
import pandas as pd

from trader.backtest.engine import buy_and_hold, run_backtest


def test_full_weight_single_asset_tracks_price():
    idx = pd.bdate_range("2020-01-01", periods=50)
    prices = pd.DataFrame({"X": np.linspace(100, 150, 50)}, index=idx)
    weights = pd.DataFrame({"X": [1.0]}, index=[idx[0]])  # all-in on day 0

    res = run_backtest(prices, weights, cost_bps=0.0, initial_capital=100_000)
    # No costs, bought at 100, ends at 150 -> +50%.
    assert abs(res.equity.iloc[-1] / 100_000 - 1.5) < 1e-6


def test_costs_reduce_equity():
    idx = pd.bdate_range("2020-01-01", periods=10)
    prices = pd.DataFrame({"X": [100.0] * 10}, index=idx)
    weights = pd.DataFrame({"X": [1.0]}, index=[idx[0]])

    free = run_backtest(prices, weights, cost_bps=0.0, initial_capital=100_000)
    charged = run_backtest(prices, weights, cost_bps=50.0, initial_capital=100_000)
    assert charged.equity.iloc[-1] < free.equity.iloc[-1]
    assert charged.total_costs > 0


def test_buy_and_hold_matches_ratio():
    s = pd.Series([10.0, 20.0], index=pd.bdate_range("2020-01-01", periods=2))
    res = buy_and_hold(s, initial_capital=1000)
    assert abs(res.equity.iloc[-1] - 2000) < 1e-9
