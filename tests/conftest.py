"""Shared test fixtures. Synthetic price data keeps tests deterministic and
fast (no network), while exercising the real strategy/engine code paths.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
import pytest

from trader.config import BENCHMARK, CASH_ETF


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """~4 years of daily prices: SPY, BIL (slow riser), and 8 names with
    varied drifts/vols, generated from a fixed seed."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2018-01-01", periods=1000)
    names = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    data = {}
    for i, name in enumerate(names):
        drift = 0.0002 + 0.00005 * i
        vol = 0.01 + 0.002 * (i % 4)
        rets = rng.normal(drift, vol, len(idx))
        data[name] = 100 * np.exp(np.cumsum(rets))
    # Benchmark: broad upward drift with the occasional drawdown.
    spy_rets = rng.normal(0.0003, 0.011, len(idx))
    data[BENCHMARK] = 100 * np.exp(np.cumsum(spy_rets))
    # Cash ETF: steadily rising, tiny vol (T-bills).
    data[CASH_ETF] = 100 * np.exp(np.cumsum(rng.normal(0.00008, 0.0003, len(idx))))
    return pd.DataFrame(data, index=idx)
