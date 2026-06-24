"""ChallengerStrategy — a multi-sleeve portfolio that competes with the
champion (pure momentum) on its own paper account.

Construction, in order:
  1. Two independent sleeves generate target weights on the shared monthly
     cadence: a momentum sleeve and a mean-reversion sleeve.
  2. Blend them (default 60/40). The sleeves run with their own trend filter
     OFF, because exposure is governed centrally by the regime model below
     (filtering in two places would double-count).
  3. Regime model scales total exposure (RISK_ON / NEUTRAL / RISK_OFF).
  4. Volatility targeting scales the risk book so its ex-ante volatility hits
     the target (default 12% annualized), never exceeding full investment
     (no leverage -> existing risk limits are never breached).
  5. Whatever is not in the risk book sits in the T-bill cash ETF.

Same `generate_weights(prices) -> DataFrame` interface as every other
strategy, so it reuses the engine, walk-forward, risk layer, and live runner
without modification.

v2 ablation (scripts/run_challenger_ablation.py, walk-forward 2005-2026):
both a longer covariance lookback (60/90 vs 20) and a market-breadth regime
input were tested and REJECTED — each cut out-of-sample CAGR/Sharpe with no
drawdown benefit. The shorter 20-day cov window adapts to vol spikes faster.
Both remain available behind flags (vol_window, regime_use_breadth) but stay
OFF/short by default. Revisit if the universe expands to hundreds of names.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.config import (
    BENCHMARK,
    CASH_ETF,
    CHALLENGER_MOMENTUM_WEIGHT,
    CHALLENGER_MR_WEIGHT,
    CHALLENGER_VOL_TARGET,
)
from trader.strategies.base import Strategy
from trader.strategies.ensemble import EnsembleStrategy
from trader.strategies.mean_reversion import MeanReversionStrategy
from trader.strategies.momentum import MomentumStrategy
from trader.strategies.regime import RegimeModel

TRADING_DAYS = 252


class ChallengerStrategy(Strategy):
    name = "challenger"

    def __init__(
        self,
        # --- searched in walk-forward ---
        momentum_lookback_days: int = 252,
        mr_lookback_days: int = 10,
        # --- sleeve sizing ---
        momentum_top_n: int = 10,
        mr_top_n: int = 10,
        momentum_weight: float = CHALLENGER_MOMENTUM_WEIGHT,
        mr_weight: float = CHALLENGER_MR_WEIGHT,
        # --- volatility targeting ---
        vol_target: float = CHALLENGER_VOL_TARGET,
        vol_window: int = 20,
        max_exposure: float = 1.0,
        # --- regime model ---
        trend_ma_days: int = 200,
        regime_vol_window: int = 20,
        regime_high_vol: float = 0.20,
        regime_extreme_vol: float = 0.35,
        neutral_exposure: float = 0.5,
        risk_off_exposure: float = 0.0,
        regime_use_breadth: bool = False,
        regime_breadth_low: float = 0.35,
        regime_breadth_high: float = 0.55,
        benchmark: str = BENCHMARK,
        cash_ticker: str = CASH_ETF,
    ):
        self.momentum_weight = momentum_weight
        self.mr_weight = mr_weight
        self.vol_target = vol_target
        self.vol_window = vol_window
        self.max_exposure = max_exposure
        self.benchmark = benchmark
        self.cash_ticker = cash_ticker

        # Sleeves: trend filter OFF (regime governs exposure centrally).
        self.momentum = MomentumStrategy(
            lookback_days=momentum_lookback_days, top_n=momentum_top_n,
            use_trend_filter=False, cash_ticker=cash_ticker,
        )
        self.mean_reversion = MeanReversionStrategy(
            lookback_days=mr_lookback_days, top_n=mr_top_n,
            use_trend_filter=False, cash_ticker=cash_ticker,
        )
        self.regime = RegimeModel(
            trend_ticker=benchmark, trend_ma_days=trend_ma_days,
            vol_window=regime_vol_window, high_vol=regime_high_vol,
            extreme_vol=regime_extreme_vol, neutral_exposure=neutral_exposure,
            risk_off_exposure=risk_off_exposure,
            use_breadth=regime_use_breadth, breadth_low=regime_breadth_low,
            breadth_high=regime_breadth_high, cash_ticker=cash_ticker,
        )

    def params(self) -> dict:
        return {
            "momentum_lookback_days": self.momentum.lookback_days,
            "mr_lookback_days": self.mean_reversion.lookback_days,
            "momentum_weight": self.momentum_weight,
            "mr_weight": self.mr_weight,
            "vol_target": self.vol_target,
            "vol_window": self.vol_window,
            "use_breadth": self.regime.use_breadth,
        }

    def _exante_vol(self, daily_ret: pd.DataFrame, weights: pd.Series,
                    asof: pd.Timestamp) -> float:
        """Annualized ex-ante volatility of a fully-invested risk book.

        Uses the trailing covariance of the held names up to (and including)
        the rebalance date — causal, no look-ahead.
        """
        held = weights[weights > 0].index
        window = daily_ret[held].loc[:asof].iloc[-self.vol_window:].dropna(axis=1)
        held = window.columns
        if len(held) == 0 or len(window) < 2:
            return float("nan")
        w = weights[held].to_numpy(dtype=float)
        w = w / w.sum()  # normalize to a fully-invested book
        cov = window.cov().to_numpy() * TRADING_DAYS
        var = float(w @ cov @ w)
        return float(np.sqrt(var)) if var > 0 else float("nan")

    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        mom_w = self.momentum.generate_weights(prices)
        mr_w = self.mean_reversion.generate_weights(prices)

        cols = sorted(set(mom_w.columns) | set(mr_w.columns))
        mom_w = mom_w.reindex(columns=cols, fill_value=0.0)
        mr_w = mr_w.reindex(index=mom_w.index, columns=cols, fill_value=0.0)
        blended = self.momentum_weight * mom_w + self.mr_weight * mr_w

        exposure = self.regime.exposure(prices)
        risk_cols = [c for c in cols if c != self.cash_ticker]
        daily_ret = prices[risk_cols].pct_change()

        out = pd.DataFrame(0.0, index=blended.index, columns=cols)
        for date in blended.index:
            row = blended.loc[date]
            risk = row[risk_cols]
            risk = risk[risk > 0]
            if risk.empty:
                out.loc[date, self.cash_ticker] = 1.0
                continue

            risk_norm = risk / risk.sum()  # fully-invested risk book
            vol = self._exante_vol(daily_ret, risk_norm, date)
            vol_scale = (
                min(self.max_exposure, self.vol_target / vol)
                if vol and not np.isnan(vol) and vol > 0 else 0.0
            )
            regime_scale = float(exposure.loc[date]) if date in exposure.index else 0.0
            gross = max(0.0, vol_scale * regime_scale)

            out.loc[date, risk_norm.index] = (risk_norm * gross).to_numpy()
            leftover = 1.0 - gross
            if leftover > 0 and self.cash_ticker in out.columns:
                out.loc[date, self.cash_ticker] += leftover

        return out


def build_challenger_ensemble(params_list: list[dict]) -> Strategy:
    """Live builder: blend the top-k challenger parameter sets at equal capital,
    mirroring how the champion bot ensembles its top-k momentum params."""
    strategies = [ChallengerStrategy(**p) for p in params_list]
    return EnsembleStrategy(strategies) if len(strategies) > 1 else strategies[0]


# Small, principled walk-forward grid (4 combos). Kept tiny on purpose: the
# challenger already has many fixed parameters, and every searched dimension
# is another overfitting surface.
CHALLENGER_GRID = {
    "momentum_lookback_days": [126, 252],
    "mr_lookback_days": [5, 10],
}

# Used until the first walk-forward writes live_params_challenger.json.
CHALLENGER_DEFAULT_PARAMS = [{"momentum_lookback_days": 252, "mr_lookback_days": 10}]
