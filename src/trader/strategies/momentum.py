"""Cross-sectional momentum with a market trend filter.

The classic 12-1 momentum effect: rank stocks by their return over the past
~12 months excluding the most recent month (which tends to mean-revert),
hold the top N, rebalance monthly. The trend filter moves the whole
portfolio to cash when the benchmark is below its long moving average,
which historically is where momentum crashes happen (2008-09, 2020).

Refinements over the textbook version (each individually testable via flags):
- Rank buffer: buy from the top `top_n`, but keep holding anything still
  ranked above `top_n * hold_buffer` — cuts turnover (and costs) by not
  selling a name over a one-place rank slip (`hold_buffer`).
- Volatility-adjusted ranking (`vol_adjusted`) and inverse-volatility
  sizing (`inverse_vol_weights`): OFF by default. The 2000-2026 walk-forward
  ablation (scripts/run_ablation.py) showed both cut drawdown but cost
  3-7%/yr of excess return in this ~65-name universe — they tilt a small
  concentrated book into low-vol names and dilute the momentum effect.
  Revisit if the universe grows to hundreds of names.
"""
from __future__ import annotations

import pandas as pd

from trader.config import BENCHMARK, CASH_ETF
from trader.strategies.base import Strategy, month_end_dates


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(
        self,
        lookback_days: int = 252,
        skip_days: int = 21,
        top_n: int = 10,
        trend_ticker: str = BENCHMARK,
        trend_ma_days: int = 200,
        use_trend_filter: bool = True,
        vol_adjusted: bool = False,
        vol_days: int = 63,
        inverse_vol_weights: bool = False,
        hold_buffer: float = 2.0,
        cash_ticker: str = CASH_ETF,
    ):
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.top_n = top_n
        self.trend_ticker = trend_ticker
        self.trend_ma_days = trend_ma_days
        self.use_trend_filter = use_trend_filter
        self.vol_adjusted = vol_adjusted
        self.vol_days = vol_days
        self.inverse_vol_weights = inverse_vol_weights
        self.hold_buffer = hold_buffer
        self.cash_ticker = cash_ticker

    def params(self) -> dict:
        return {
            "lookback_days": self.lookback_days,
            "skip_days": self.skip_days,
            "top_n": self.top_n,
            "trend_ma_days": self.trend_ma_days,
            "use_trend_filter": self.use_trend_filter,
            "vol_adjusted": self.vol_adjusted,
            "inverse_vol_weights": self.inverse_vol_weights,
            "hold_buffer": self.hold_buffer,
        }

    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        excluded = {self.trend_ticker, self.cash_ticker}
        candidates = [c for c in prices.columns if c not in excluded]
        has_cash_etf = self.cash_ticker in prices.columns
        px = prices[candidates]

        momentum = px.shift(self.skip_days) / px.shift(self.lookback_days) - 1.0
        vol = px.pct_change().rolling(self.vol_days).std()
        score = momentum / vol if self.vol_adjusted else momentum

        if self.use_trend_filter and self.trend_ticker in prices.columns:
            bench = prices[self.trend_ticker]
            risk_on = bench > bench.rolling(self.trend_ma_days).mean()
        else:
            risk_on = pd.Series(True, index=prices.index)

        rebalance_dates = month_end_dates(prices.index)
        columns = candidates + ([self.cash_ticker] if has_cash_etf else [])
        weights = pd.DataFrame(0.0, index=rebalance_dates, columns=columns)
        buffer_n = max(self.top_n, int(round(self.top_n * self.hold_buffer)))
        held: list[str] = []

        for date in rebalance_dates:
            scores = score.loc[date].dropna()
            # Only names with positive raw momentum qualify at all.
            scores = scores[momentum.loc[date].reindex(scores.index) > 0]
            if not risk_on.loc[date] or scores.empty:
                held = []
                # Risk-off: park everything in T-bills instead of 0% cash.
                # (The engine leaves it as cash if the ETF has no price yet.)
                if has_cash_etf:
                    weights.loc[date, self.cash_ticker] = 1.0
                continue

            ranked = scores.sort_values(ascending=False).index.to_list()
            rank = {ticker: i for i, ticker in enumerate(ranked)}

            held = [t for t in held if rank.get(t, len(ranked)) < buffer_n]
            for ticker in ranked:
                if len(held) >= self.top_n:
                    break
                if ticker not in held:
                    held.append(ticker)

            if self.inverse_vol_weights:
                inv = 1.0 / vol.loc[date].reindex(held).clip(lower=1e-4)
                weights.loc[date, held] = (inv / inv.sum()).values
            else:
                weights.loc[date, held] = 1.0 / len(held)

        return weights
