"""Strategy invariants: no leverage, weight bounds, regime behavior."""
import numpy as np
import pandas as pd

from trader.config import BENCHMARK, CASH_ETF
from trader.strategies.base import month_end_dates, week_end_dates
from trader.strategies.challenger import ChallengerStrategy
from trader.strategies.mean_reversion import MeanReversionStrategy
from trader.strategies.momentum import MomentumStrategy
from trader.strategies.regime import RISK_OFF, RISK_ON, RegimeModel


def test_momentum_weights_sum_to_one_or_cash(synthetic_prices):
    w = MomentumStrategy(top_n=5).generate_weights(synthetic_prices)
    # Each row is fully invested or in cash; never leveraged.
    assert (w.sum(axis=1) <= 1.0 + 1e-9).all()
    assert (w.sum(axis=1) >= -1e-9).all()


def test_challenger_never_leverages(synthetic_prices):
    w = ChallengerStrategy().generate_weights(synthetic_prices)
    assert (w.sum(axis=1) <= 1.0 + 1e-6).all(), "challenger exceeded 100% gross"
    assert (w.to_numpy() >= -1e-9).all(), "challenger produced a short weight"


def test_challenger_vol_target_holds_cash(synthetic_prices):
    # With a 12% target on a noisy book, some capital should sit in the cash
    # ETF on average (vol scaling rarely runs fully invested).
    w = ChallengerStrategy().generate_weights(synthetic_prices)
    assert w.get(CASH_ETF, pd.Series(0)).mean() > 0.0


def test_regime_risk_off_below_trend():
    # Benchmark in a steady downtrend -> never RISK_ON.
    idx = pd.bdate_range("2018-01-01", periods=400)
    falling = pd.DataFrame({
        BENCHMARK: np.linspace(200, 100, 400),
        CASH_ETF: np.linspace(100, 101, 400),
        "AAA": np.linspace(200, 100, 400),
    }, index=idx)
    states = RegimeModel().classify(falling)
    tail = states.iloc[300:]  # past MA warmup
    assert (tail != RISK_ON).all()
    assert (tail == RISK_OFF).any()


def test_regime_breadth_fraction_bounds(synthetic_prices):
    br = RegimeModel(use_breadth=True).breadth(synthetic_prices).dropna()
    assert ((br >= 0) & (br <= 1)).all()


def test_regime_exposure_in_unit_interval(synthetic_prices):
    exp = RegimeModel().exposure(synthetic_prices)
    assert ((exp >= 0) & (exp <= 1)).all()


def test_week_end_dates_more_frequent_than_month(synthetic_prices):
    idx = synthetic_prices.index
    assert len(week_end_dates(idx)) > 3 * len(month_end_dates(idx))


def test_weekly_mr_rebalances_more_and_no_leverage(synthetic_prices):
    monthly = MeanReversionStrategy(rebalance="M").generate_weights(synthetic_prices)
    weekly = MeanReversionStrategy(rebalance="W").generate_weights(synthetic_prices)
    assert len(weekly) > 3 * len(monthly)
    assert (weekly.sum(axis=1) <= 1.0 + 1e-9).all()


def test_challenger_weekly_no_leverage(synthetic_prices):
    w = ChallengerStrategy(mr_rebalance="W").generate_weights(synthetic_prices)
    assert (w.sum(axis=1) <= 1.0 + 1e-6).all()
