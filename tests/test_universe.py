"""Point-in-time universe framework."""
import pandas as pd

from trader.config import BENCHMARK
from trader.universe import (
    PointInTimeUniverse,
    StaticUniverse,
    apply_universe,
    default_universe,
)


def test_static_universe_is_identity(synthetic_prices):
    uni = StaticUniverse([c for c in synthetic_prices.columns if c != BENCHMARK])
    masked = apply_universe(synthetic_prices, uni)
    assert masked.equals(synthetic_prices)


def test_default_universe_is_static():
    assert isinstance(default_universe(), StaticUniverse)


def test_point_in_time_membership_by_date():
    uni = PointInTimeUniverse({
        "AAA": [(pd.Timestamp("2019-01-01"), pd.Timestamp("2020-12-31"))],
        "BBB": [(pd.Timestamp("2021-01-01"), None)],
    })
    assert uni.members_asof("2019-06-01") == {"AAA"}
    assert uni.members_asof("2021-06-01") == {"BBB"}        # AAA left, BBB joined
    assert uni.members_asof("2018-01-01") == set()          # before anyone joined
    assert sorted(uni.all_tickers()) == ["AAA", "BBB"]


def test_apply_universe_masks_and_passes_benchmark(synthetic_prices):
    cutoff = synthetic_prices.index[500]
    uni = PointInTimeUniverse({"AAA": [(cutoff, None)]})
    masked = apply_universe(synthetic_prices, uni)
    # AAA NaN before its join date, present after; benchmark untouched.
    assert masked["AAA"].loc[:cutoff].iloc[:-1].isna().all()
    assert masked["AAA"].loc[cutoff:].notna().any()
    assert masked[BENCHMARK].equals(synthetic_prices[BENCHMARK])


def test_from_csv_roundtrip(tmp_path):
    p = tmp_path / "members.csv"
    p.write_text("ticker,start,end\nAAA,2019-01-01,2020-12-31\nBBB,2021-01-01,\n")
    uni = PointInTimeUniverse.from_csv(p)
    assert uni.members_asof("2019-06-01") == {"AAA"}
    assert uni.members_asof("2022-01-01") == {"BBB"}
