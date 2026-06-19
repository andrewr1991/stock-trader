"""Market regime detection — a configurable replacement for the champion's
binary "SPY > 200-day MA" switch.

Three states drive how much of the book is risk-on:

    RISK_ON   full exposure          (uptrend, calm)
    NEUTRAL   reduced exposure       (uptrend but elevated volatility)
    RISK_OFF  defensive / mostly cash (downtrend OR extreme volatility)

Inputs are deliberately limited to what the existing data loader already
provides: SPY trend (vs its long MA) and SPY realized volatility. VIX and
market-breadth inputs are natural future extensions but are intentionally
omitted to avoid adding a data dependency and extra free parameters.

Causal by construction: state at date D uses only prices up to and including
D, matching the backtest engine's execute-at-close convention.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.config import BENCHMARK

RISK_ON = "RISK_ON"
NEUTRAL = "NEUTRAL"
RISK_OFF = "RISK_OFF"

TRADING_DAYS = 252


class RegimeModel:
    def __init__(
        self,
        trend_ticker: str = BENCHMARK,
        trend_ma_days: int = 200,
        vol_window: int = 20,
        high_vol: float = 0.20,
        extreme_vol: float = 0.35,
        neutral_exposure: float = 0.5,
        risk_off_exposure: float = 0.0,
    ):
        self.trend_ticker = trend_ticker
        self.trend_ma_days = trend_ma_days
        self.vol_window = vol_window
        self.high_vol = high_vol
        self.extreme_vol = extreme_vol
        self.neutral_exposure = neutral_exposure
        self.risk_off_exposure = risk_off_exposure

    def classify(self, prices: pd.DataFrame) -> pd.Series:
        """Daily series of regime state strings."""
        bench = prices[self.trend_ticker]
        above_trend = bench > bench.rolling(self.trend_ma_days).mean()
        realized_vol = bench.pct_change().rolling(self.vol_window).std() * np.sqrt(TRADING_DAYS)

        state = pd.Series(RISK_ON, index=prices.index)
        state[above_trend & (realized_vol > self.high_vol)] = NEUTRAL
        state[(~above_trend) | (realized_vol > self.extreme_vol)] = RISK_OFF
        # Before the trend MA has enough history, stay defensive.
        state[bench.rolling(self.trend_ma_days).mean().isna()] = RISK_OFF
        return state

    def exposure(self, prices: pd.DataFrame) -> pd.Series:
        """Daily exposure multiplier in [0, 1] mapped from the regime state."""
        state = self.classify(prices)
        mapping = {
            RISK_ON: 1.0,
            NEUTRAL: self.neutral_exposure,
            RISK_OFF: self.risk_off_exposure,
        }
        return state.map(mapping).astype(float)
