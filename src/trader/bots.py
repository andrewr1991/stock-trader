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
    CHALLENGER_ALPACA_KEY,
    CHALLENGER_ALPACA_SECRET,
    CHALLENGER_JOURNAL_DB,
    CHALLENGER_PARAMS_FILE,
    JOURNAL_DB,
    LIVE_PARAMS_FILE,
    REPORTS_DIR,
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
        report_md=REPORTS_DIR / "performance_challenger.md",
        report_png=REPORTS_DIR / "performance_challenger.png",
    )


_BOTS = {"champion": champion_bot, "challenger": challenger_bot}


def get_bot(name: str) -> BotConfig:
    if name not in _BOTS:
        raise ValueError(f"unknown bot '{name}'; choose from {list(_BOTS)}")
    return _BOTS[name]()
