"""Historical price loading with local caching.

Uses yfinance for long history (Alpaca's free historical feed only goes back
to ~2016, and honest backtests need 2008 and 2020 in them). Live trading
reads prices from Alpaca so the execution path matches the broker.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from trader.config import CACHE_DIR


def _cache_key(tickers: list[str], start: str, end: str) -> str:
    raw = ",".join(sorted(tickers)) + f"|{start}|{end}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def load_prices(
    tickers: list[str],
    start: str = "2007-01-01",
    end: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Return a DataFrame of dividend/split-adjusted daily closes.

    Index: trading days (DatetimeIndex). Columns: tickers. Tickers that
    listed after `start` have leading NaNs; strategies must tolerate that.
    """
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    cache_file = Path(CACHE_DIR) / f"prices_{_cache_key(tickers, start, end)}.parquet"

    if cache_file.exists() and not refresh:
        return pd.read_parquet(cache_file)

    import yfinance as yf

    raw = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    closes = closes.dropna(how="all")
    # Forward-fill so a missing print mid-history doesn't read as a delisting;
    # leading NaNs (pre-IPO) are preserved.
    closes = closes.ffill()

    missing = [t for t in tickers if t not in closes.columns or closes[t].dropna().empty]
    if missing:
        print(f"WARNING: no data for {missing}; continuing without them")
    closes = closes[[t for t in tickers if t in closes.columns]]

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    closes.to_parquet(cache_file)
    return closes
