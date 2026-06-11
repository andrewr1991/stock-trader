"""Portfolio-level risk limits, enforced independently of any strategy.

The risk layer has veto power: whatever a strategy wants, these limits are
applied afterward. Keep this code boring and conservative.
"""
from __future__ import annotations

import pandas as pd


class RiskManager:
    def __init__(
        self,
        max_position_weight: float = 0.15,
        max_gross_exposure: float = 1.0,
        kill_switch_drawdown: float = 0.15,
    ):
        self.max_position_weight = max_position_weight
        self.max_gross_exposure = max_gross_exposure
        self.kill_switch_drawdown = kill_switch_drawdown

    def apply(self, weights: pd.Series, current_drawdown: float = 0.0) -> pd.Series:
        """Clamp target weights. `current_drawdown` is negative (e.g. -0.12).

        Excess weight goes to cash rather than being redistributed — when a
        limit binds, the safe direction is less exposure, not different bets.
        """
        if current_drawdown <= -self.kill_switch_drawdown:
            return weights * 0.0

        clamped = weights.clip(upper=self.max_position_weight)
        gross = clamped.abs().sum()
        if gross > self.max_gross_exposure:
            clamped = clamped * (self.max_gross_exposure / gross)
        return clamped
