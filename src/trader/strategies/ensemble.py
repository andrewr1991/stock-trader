"""Equal-capital blend of several strategies.

Used by the live loop to hold the top-k parameter sets from the latest
walk-forward fold simultaneously, mirroring how the out-of-sample numbers
were produced (ensemble_k sleeves with equal capital).
"""
from __future__ import annotations

import pandas as pd

from trader.strategies.base import Strategy


class EnsembleStrategy(Strategy):
    name = "ensemble"

    def __init__(self, strategies: list[Strategy]):
        if not strategies:
            raise ValueError("EnsembleStrategy needs at least one strategy")
        self.strategies = strategies

    def params(self) -> dict:
        return {"members": [s.params() for s in self.strategies]}

    def generate_weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        frames = [s.generate_weights(prices) for s in self.strategies]
        combined = sum(f.reindex(columns=frames[0].columns, fill_value=0.0).fillna(0.0)
                       for f in frames)
        return combined / len(frames)
