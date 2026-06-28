"""Multi-asset trend following (the "B" design): an independent time-series
trend filter per asset class, vol-sized, with cash when nothing is trending.

Why this structure (vs. cross-asset relative strength):
  - Each asset is judged against ITS OWN trend, so heterogeneous volatilities
    (SPY vs TLT vs GLD) don't distort a cross-sectional ranking.
  - When every asset is below its trend, the book is NATURALLY in cash — the
    crisis behavior you want, which relative-strength (always holding the
    "least bad" asset) does not give you.
  - Held assets are inverse-vol weighted (risk parity), then the whole book is
    scaled to a volatility target, capped at fully invested (no leverage).

Reuses the same trend-filter + vol-target machinery as the equity sleeves;
just applied to a small ETF set. Causal throughout.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.config import CASH_ETF
from trader.strategies.base import Strategy, exante_vol, rebalance_dates

TRADING_DAYS = 252
DEFAULT_ASSETS = ("SPY", "EFA", "TLT", "GLD")  # US eq, intl eq, long bonds, gold


class MultiAssetTrendStrategy(Strategy):
    name = "multi_asset_trend"

    def __init__(
        self,
        assets: tuple[str, ...] = DEFAULT_ASSETS,
        trend_ma_days: int = 200,
        vol_window: int = 60,
        vol_target: float = 0.10,
        max_exposure: float = 1.0,
        rebalance: str = "M",
        cash_ticker: str = CASH_ETF,
    ):
        self.assets = list(assets)
        self.trend_ma_days = trend_ma_days
        self.vol_window = vol_window
        self.vol_target = vol_target
        self.max_exposure = max_exposure
        self.rebalance = rebalance
        self.cash_ticker = cash_ticker

    def params(self) -> dict:
        return {
            "assets": self.assets,
            "trend_ma_days": self.trend_ma_days,
            "vol_window": self.vol_window,
            "vol_target": self.vol_target,
        }

    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        assets = [a for a in self.assets if a in prices.columns]
        px = prices[assets]
        ma = px.rolling(self.trend_ma_days).mean()
        above_trend = px > ma
        daily_ret = px.pct_change()
        asset_vol = daily_ret.rolling(self.vol_window).std() * np.sqrt(TRADING_DAYS)

        has_cash = self.cash_ticker in prices.columns
        rebal = rebalance_dates(prices.index, self.rebalance)
        cols = assets + ([self.cash_ticker] if has_cash else [])
        weights = pd.DataFrame(0.0, index=rebal, columns=cols)

        for date in rebal:
            held = [a for a in assets
                    if bool(above_trend.loc[date, a]) and not np.isnan(px.loc[date, a])]
            if not held:
                if has_cash:
                    weights.loc[date, self.cash_ticker] = 1.0
                continue

            inv = 1.0 / asset_vol.loc[date, held].clip(lower=1e-4)
            w = inv / inv.sum()  # inverse-vol (risk parity) across held assets
            vol = exante_vol(daily_ret, w, self.vol_window, date)
            scale = (min(self.max_exposure, self.vol_target / vol)
                     if vol and not np.isnan(vol) and vol > 0 else 0.0)
            weights.loc[date, held] = (w * scale).to_numpy()
            leftover = 1.0 - scale
            if leftover > 0 and has_cash:
                weights.loc[date, self.cash_ticker] += leftover

        return weights
