"""Metrics on known inputs — guards the math behind every report."""
import numpy as np
import pandas as pd

from trader.backtest.metrics import (
    annual_vol,
    cagr,
    max_drawdown,
    rolling_sharpe,
    sharpe,
    sortino,
    win_rate,
)

TRADING_DAYS = 252


def test_cagr_doubling_in_one_year():
    eq = pd.Series(np.linspace(100, 200, TRADING_DAYS))
    assert abs(cagr(eq) - 1.0) < 0.02  # ~100% over ~1 year


def test_max_drawdown_known():
    eq = pd.Series([100, 120, 60, 90, 150])  # trough 60 from peak 120
    assert abs(max_drawdown(eq) - (-0.5)) < 1e-9


def test_sharpe_zero_when_flat():
    flat = pd.Series([0.0] * 100)
    assert np.isnan(sharpe(flat))  # zero vol -> undefined


def test_sortino_only_penalizes_downside():
    # Right-skewed: big varied upside, small varied downside. Downside
    # deviation < total deviation, so Sortino should exceed Sharpe.
    rets = pd.Series([0.08, -0.01, 0.06, -0.02, 0.07, -0.015, 0.05, -0.005] * 30)
    assert sharpe(rets) > 0
    assert sortino(rets) > sharpe(rets)


def test_annual_vol_scales_with_sqrt_time():
    rng = np.random.default_rng(0)
    daily = pd.Series(rng.normal(0, 0.01, 5000))
    assert abs(annual_vol(daily) - 0.01 * np.sqrt(TRADING_DAYS)) < 0.01


def test_win_rate_bounds():
    eq = pd.Series(np.linspace(100, 200, 600),
                   index=pd.bdate_range("2020-01-01", periods=600))
    wr = win_rate(eq)
    assert 0.0 <= wr <= 1.0 and wr > 0.5  # mostly-up series


def test_rolling_sharpe_length_matches():
    rng = np.random.default_rng(1)
    rets = pd.Series(rng.normal(0.0005, 0.01, 400))
    rs = rolling_sharpe(rets, window=252)
    assert len(rs) == len(rets)
    assert rs.iloc[:251].isna().all()  # not enough history early
    assert rs.iloc[252:].notna().any()
