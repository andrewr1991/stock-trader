"""Market regime detection — a configurable replacement for the champion's
binary "SPY > 200-day MA" switch.

Three states drive how much of the book is risk-on:

    RISK_ON   full exposure          (uptrend, calm)
    NEUTRAL   reduced exposure       (uptrend but elevated volatility)
    RISK_OFF  defensive / mostly cash (downtrend OR extreme volatility)

Base inputs use what the data loader already provides: SPY trend (vs its long
MA) and SPY realized volatility. Market breadth (% of the universe above its
own 200-day MA) is an OPTIONAL third input (`use_breadth`, off by default
until the walk-forward ablation justifies it). VIX remains a future extension.

Causal by construction: state at date D uses only prices up to and including
D, matching the backtest engine's execute-at-close convention.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.config import BENCHMARK, CASH_ETF

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
        use_breadth: bool = False,
        breadth_ma_days: int = 200,
        breadth_low: float = 0.35,
        breadth_high: float = 0.55,
        cash_ticker: str = CASH_ETF,
    ):
        self.trend_ticker = trend_ticker
        self.trend_ma_days = trend_ma_days
        self.vol_window = vol_window
        self.high_vol = high_vol
        self.extreme_vol = extreme_vol
        self.neutral_exposure = neutral_exposure
        self.risk_off_exposure = risk_off_exposure
        self.use_breadth = use_breadth
        self.breadth_ma_days = breadth_ma_days
        self.breadth_low = breadth_low
        self.breadth_high = breadth_high
        self.cash_ticker = cash_ticker

    def breadth(self, prices: pd.DataFrame) -> pd.Series:
        """Fraction of universe names trading above their own long MA.

        Causal: uses only trailing prices. Names without enough history yet
        (MA is NaN) are excluded from both numerator and denominator, so the
        ratio isn't biased low during early history.
        """
        cols = [c for c in prices.columns if c not in {self.trend_ticker, self.cash_ticker}]
        px = prices[cols]
        ma = px.rolling(self.breadth_ma_days).mean()
        valid = ma.notna() & px.notna()
        above = (px > ma) & valid
        denom = valid.sum(axis=1).replace(0, np.nan)
        return above.sum(axis=1) / denom

    def classify(self, prices: pd.DataFrame) -> pd.Series:
        """Daily series of regime state strings."""
        bench = prices[self.trend_ticker]
        above_trend = bench > bench.rolling(self.trend_ma_days).mean()
        realized_vol = bench.pct_change().rolling(self.vol_window).std() * np.sqrt(TRADING_DAYS)

        state = pd.Series(RISK_ON, index=prices.index)
        state[above_trend & (realized_vol > self.high_vol)] = NEUTRAL
        state[(~above_trend) | (realized_vol > self.extreme_vol)] = RISK_OFF

        if self.use_breadth:
            br = self.breadth(prices)
            # Weak breadth confirms/escalates risk: moderate -> at least
            # NEUTRAL, very weak -> RISK_OFF. Breadth never UPGRADES a state
            # that trend/vol already marked defensive.
            weak = br < self.breadth_high
            state[weak & (state == RISK_ON)] = NEUTRAL
            state[(br < self.breadth_low)] = RISK_OFF
            state[br.isna()] = RISK_OFF  # not enough history -> defensive

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
