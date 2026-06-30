"""Build the assets for the client-side Strategy Lab (docs/lab/).

The lab runs the REAL backtest engine + strategies in the visitor's browser via
Pyodide (Python compiled to WebAssembly). This script ships two things:

  docs/lab/bundle.json  — the `trader` package source (engine, metrics,
                          walk-forward, strategies) plus a browser-safe config
                          shim (constants only, no Alpaca/dotenv). Using the
                          real source guarantees the lab can't drift from the
                          live bots.
  docs/lab/prices.csv    — cached daily closes for the universe + ETFs, so the
                          browser has data without a live feed.

Re-run whenever the strategy code or desired data window changes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader.config import (  # noqa: E402
    BENCHMARK, CASH_ETF, CHALLENGER_MOMENTUM_WEIGHT, CHALLENGER_MR_WEIGHT,
    CHALLENGER_VOL_TARGET, COST_BPS, INITIAL_CAPITAL, UNIVERSE,
)
from trader.data.loader import load_prices  # noqa: E402
from trader.strategies.trend_multi_asset import DEFAULT_ASSETS  # noqa: E402

LAB = ROOT / "docs" / "lab"
SRC = ROOT / "src" / "trader"

# Real source files shipped to the browser (all pure pandas/numpy).
MODULES = [
    "__init__.py",
    "backtest/__init__.py", "backtest/engine.py", "backtest/metrics.py",
    "backtest/walkforward.py",
    "strategies/__init__.py", "strategies/base.py", "strategies/ensemble.py",
    "strategies/momentum.py", "strategies/mean_reversion.py",
    "strategies/regime.py", "strategies/challenger.py",
    "strategies/trend_multi_asset.py",
]

CONFIG_SHIM = f'''"""Browser-safe config shim for the Strategy Lab (constants only)."""
BENCHMARK = {BENCHMARK!r}
CASH_ETF = {CASH_ETF!r}
COST_BPS = {COST_BPS!r}
INITIAL_CAPITAL = {INITIAL_CAPITAL!r}
UNIVERSE = {UNIVERSE!r}
CHALLENGER_VOL_TARGET = {CHALLENGER_VOL_TARGET!r}
CHALLENGER_MOMENTUM_WEIGHT = {CHALLENGER_MOMENTUM_WEIGHT!r}
CHALLENGER_MR_WEIGHT = {CHALLENGER_MR_WEIGHT!r}
'''


def main():
    LAB.mkdir(parents=True, exist_ok=True)

    files = {"trader/config.py": CONFIG_SHIM}
    for rel in MODULES:
        files[f"trader/{rel}"] = (SRC / rel).read_text(encoding="utf-8")
    (LAB / "bundle.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    print(f"Wrote bundle.json ({len(files)} files)")

    tickers = sorted(set(UNIVERSE) | set(DEFAULT_ASSETS) | {BENCHMARK, CASH_ETF})
    prices = load_prices(tickers, start="2005-01-01").round(3)
    prices.index.name = "date"
    prices.to_csv(LAB / "prices.csv")
    size_mb = (LAB / "prices.csv").stat().st_size / 1e6
    print(f"Wrote prices.csv ({len(prices)} rows x {len(prices.columns)} cols, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
