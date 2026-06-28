"""Bot registry: the single abstraction that makes Champion and Challenger
two independent bots over one shared codebase.

A BotConfig bundles everything that differs between bots — strategy builder,
Alpaca credentials, journal, params file, walk-forward grid, report paths.
Everything else (engine, walk-forward, risk layer, runner, broker, journal
class) is shared and untouched. The champion config reproduces the original
behavior exactly, so the existing live bot is unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from trader.config import (
    ALPACA_API_KEY,
    ALPACA_PAPER,
    ALPACA_SECRET_KEY,
    BENCHMARK,
    CASH_ETF,
    CHALLENGER_ALPACA_KEY,
    CHALLENGER_ALPACA_SECRET,
    CHALLENGER_JOURNAL_DB,
    CHALLENGER_PARAMS_FILE,
    JOURNAL_DB,
    LIVE_PARAMS_FILE,
    MULTIASSET_ALPACA_KEY,
    MULTIASSET_ALPACA_SECRET,
    MULTIASSET_JOURNAL_DB,
    MULTIASSET_PARAMS_FILE,
    REPORTS_DIR,
    UNIVERSE,
)
from trader.strategies.base import Strategy
from trader.strategies.challenger import (
    CHALLENGER_DEFAULT_PARAMS,
    CHALLENGER_GRID,
    ChallengerStrategy,
    build_challenger_ensemble,
)
from trader.strategies.ensemble import EnsembleStrategy
from trader.strategies.momentum import MomentumStrategy
from trader.strategies.trend_multi_asset import DEFAULT_ASSETS, MultiAssetTrendStrategy

EQUITY_TICKERS = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
ETF_TICKERS = sorted(set(DEFAULT_ASSETS) | {BENCHMARK, CASH_ETF})


@dataclass
class BotConfig:
    name: str
    api_key: str
    secret_key: str
    paper: bool
    journal_db: Path
    params_file: Path
    default_params: list[dict]
    build_strategy: Callable[[list[dict]], Strategy]  # live: list-of-params -> Strategy
    factory: Callable[..., Strategy]                   # walk-forward: **combo -> Strategy
    param_grid: dict
    ensemble_k: int
    data_tickers: list[str]   # which symbols this bot's strategy trades/needs
    data_start: str           # earliest date to load for backtests/refits
    report_md: Path
    report_png: Path

    def has_credentials(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def load_params(self) -> list[dict]:
        if self.params_file.exists():
            return json.loads(self.params_file.read_text())
        return self.default_params

    def strategy(self) -> Strategy:
        return self.build_strategy(self.load_params())


def _build_momentum_ensemble(params_list: list[dict]) -> Strategy:
    return EnsembleStrategy([MomentumStrategy(**p) for p in params_list])


def champion_bot() -> BotConfig:
    return BotConfig(
        name="champion",
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        paper=ALPACA_PAPER,
        journal_db=JOURNAL_DB,
        params_file=LIVE_PARAMS_FILE,
        default_params=[{"lookback_days": 126, "top_n": 5}],
        build_strategy=_build_momentum_ensemble,
        factory=MomentumStrategy,
        param_grid={"lookback_days": [126, 189, 252], "top_n": [5, 10, 15]},
        ensemble_k=3,
        data_tickers=EQUITY_TICKERS,
        data_start="2000-01-01",
        report_md=REPORTS_DIR / "performance.md",
        report_png=REPORTS_DIR / "performance.png",
    )


def challenger_bot() -> BotConfig:
    return BotConfig(
        name="challenger",
        api_key=CHALLENGER_ALPACA_KEY,
        secret_key=CHALLENGER_ALPACA_SECRET,
        paper=ALPACA_PAPER,
        journal_db=CHALLENGER_JOURNAL_DB,
        params_file=CHALLENGER_PARAMS_FILE,
        default_params=CHALLENGER_DEFAULT_PARAMS,
        build_strategy=build_challenger_ensemble,
        factory=ChallengerStrategy,
        param_grid=CHALLENGER_GRID,
        ensemble_k=2,
        data_tickers=EQUITY_TICKERS,
        data_start="2000-01-01",
        report_md=REPORTS_DIR / "performance_challenger.md",
        report_png=REPORTS_DIR / "performance_challenger.png",
    )


def _build_multiasset_ensemble(params_list: list[dict]) -> Strategy:
    strategies = [MultiAssetTrendStrategy(**p) for p in params_list]
    return EnsembleStrategy(strategies) if len(strategies) > 1 else strategies[0]


def multiasset_bot() -> BotConfig:
    return BotConfig(
        name="multiasset",
        api_key=MULTIASSET_ALPACA_KEY,
        secret_key=MULTIASSET_ALPACA_SECRET,
        paper=ALPACA_PAPER,
        journal_db=MULTIASSET_JOURNAL_DB,
        params_file=MULTIASSET_PARAMS_FILE,
        default_params=[{"trend_ma_days": 200}],
        build_strategy=_build_multiasset_ensemble,
        factory=MultiAssetTrendStrategy,
        param_grid={"trend_ma_days": [150, 200, 250]},
        ensemble_k=2,
        data_tickers=ETF_TICKERS,
        data_start="2005-01-01",  # clean window where all four ETFs exist
        report_md=REPORTS_DIR / "performance_multiasset.md",
        report_png=REPORTS_DIR / "performance_multiasset.png",
    )


_BOTS = {"champion": champion_bot, "challenger": challenger_bot, "multiasset": multiasset_bot}
BOT_NAMES = list(_BOTS)


def get_bot(name: str) -> BotConfig:
    if name not in _BOTS:
        raise ValueError(f"unknown bot '{name}'; choose from {list(_BOTS)}")
    return _BOTS[name]()
