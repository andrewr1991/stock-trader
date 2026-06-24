"""Short-term mean reversion ("buy the dip on strong names").

Ranks stocks by how oversold they are versus their own recent average, and
buys the most oversold — but only among names still in a longer-term uptrend,
which avoids catching falling knives (the classic failure mode of naive mean
reversion). Same monthly cadence, rank buffer, and cash-ETF risk-off handling
as the momentum sleeve, so it drops into the shared engine/runner unchanged.

Note: mean reversion is usually a shorter-horizon effect; running it on a
monthly rebalance (to match the existing infrastructure) blunts it. It earns
its keep here mainly by being *uncorrelated* with momentum, not by being a
stronger standalone signal.
"""
from __future__ import annotations

import pandas as pd

from trader.config import BENCHMARK, CASH_ETF
from trader.strategies.base import Strategy, rebalance_dates


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(
        self,
        lookback_days: int = 10,
        z_window: int = 20,
        top_n: int = 10,
        quality_ma_days: int = 100,
        trend_ticker: str = BENCHMARK,
        trend_ma_days: int = 200,
        use_trend_filter: bool = True,
        hold_buffer: float = 2.0,
        rebalance: str = "M",
        cash_ticker: str = CASH_ETF,
    ):
        self.lookback_days = lookback_days
        self.z_window = z_window
        self.top_n = top_n
        self.quality_ma_days = quality_ma_days
        self.trend_ticker = trend_ticker
        self.trend_ma_days = trend_ma_days
        self.use_trend_filter = use_trend_filter
        self.hold_buffer = hold_buffer
        self.rebalance = rebalance
        self.cash_ticker = cash_ticker

    def params(self) -> dict:
        return {
            "lookback_days": self.lookback_days,
            "z_window": self.z_window,
            "top_n": self.top_n,
            "quality_ma_days": self.quality_ma_days,
            "use_trend_filter": self.use_trend_filter,
            "hold_buffer": self.hold_buffer,
            "rebalance": self.rebalance,
        }

    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        excluded = {self.trend_ticker, self.cash_ticker}
        candidates = [c for c in prices.columns if c not in excluded]
        has_cash_etf = self.cash_ticker in prices.columns
        px = prices[candidates]

        # Z-score of price vs its own rolling mean: low (negative) = oversold.
        ma = px.rolling(self.z_window).mean()
        sd = px.rolling(self.z_window).std()
        zscore = (px - ma) / sd
        # Short-horizon return, also used as an oversold confirmation.
        recent_ret = px / px.shift(self.lookback_days) - 1.0
        # Quality filter: only dip-buy names still above their longer MA.
        uptrend = px > px.rolling(self.quality_ma_days).mean()

        if self.use_trend_filter and self.trend_ticker in prices.columns:
            bench = prices[self.trend_ticker]
            risk_on = bench > bench.rolling(self.trend_ma_days).mean()
        else:
            risk_on = pd.Series(True, index=prices.index)

        rebal_dates = rebalance_dates(prices.index, self.rebalance)
        columns = candidates + ([self.cash_ticker] if has_cash_etf else [])
        weights = pd.DataFrame(0.0, index=rebal_dates, columns=columns)
        buffer_n = max(self.top_n, int(round(self.top_n * self.hold_buffer)))
        held: list[str] = []

        for date in rebal_dates:
            z = zscore.loc[date]
            # Oversold (z < 0), short-term negative return, in a longer uptrend.
            eligible = z[(z < 0)
                         & (recent_ret.loc[date].reindex(z.index) < 0)
                         & (uptrend.loc[date].reindex(z.index).fillna(False))].dropna()
            if not risk_on.loc[date] or eligible.empty:
                held = []
                if has_cash_etf:
                    weights.loc[date, self.cash_ticker] = 1.0
                continue

            # Most oversold = most negative z = bought first.
            ranked = eligible.sort_values(ascending=True).index.to_list()
            rank = {ticker: i for i, ticker in enumerate(ranked)}

            held = [t for t in held if rank.get(t, len(ranked)) < buffer_n]
            for ticker in ranked:
                if len(held) >= self.top_n:
                    break
                if ticker not in held:
                    held.append(ticker)

            weights.loc[date, held] = 1.0 / len(held)

        return weights
