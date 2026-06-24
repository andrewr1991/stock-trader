"""No look-ahead bias. The contract: weights dated D depend ONLY on prices up
to D. So generating weights on the full history and on a copy truncated after
D must yield IDENTICAL weights for every rebalance date <= D.

This is the single most important property of the whole system — if it fails,
every backtest is a lie. Tested on all three live strategies.
"""
import numpy as np
import pytest

from trader.strategies.challenger import ChallengerStrategy
from trader.strategies.mean_reversion import MeanReversionStrategy
from trader.strategies.momentum import MomentumStrategy


def _assert_causal(strategy, prices, cutoff_pos=700):
    cutoff = prices.index[cutoff_pos]
    full = strategy.generate_weights(prices)
    trunc = strategy.generate_weights(prices.loc[:cutoff])

    shared = full.index.intersection(trunc.index)
    shared = shared[shared <= cutoff]
    assert len(shared) >= 5, "not enough overlapping rebalance dates to test"

    cols = full.columns.union(trunc.columns)
    f = full.reindex(columns=cols, fill_value=0.0).loc[shared]
    t = trunc.reindex(columns=cols, fill_value=0.0).loc[shared]
    assert np.allclose(f.to_numpy(), t.to_numpy(), atol=1e-9), \
        "future data changed past weights -> LOOK-AHEAD BIAS"


def test_momentum_causal(synthetic_prices):
    _assert_causal(MomentumStrategy(lookback_days=126, top_n=4), synthetic_prices)


def test_mean_reversion_causal(synthetic_prices):
    _assert_causal(MeanReversionStrategy(lookback_days=10, top_n=4), synthetic_prices)


def test_challenger_causal(synthetic_prices):
    _assert_causal(ChallengerStrategy(), synthetic_prices)


def test_challenger_causal_with_breadth(synthetic_prices):
    _assert_causal(ChallengerStrategy(regime_use_breadth=True), synthetic_prices)


def test_challenger_causal_weekly_mr(synthetic_prices):
    _assert_causal(ChallengerStrategy(mr_rebalance="W"), synthetic_prices)
