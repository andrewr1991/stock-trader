"""Walk-forward validation — the honest way to pick strategy parameters.

For each fold, parameters are chosen using ONLY the training window, then
evaluated on the following test window the optimizer never saw. The stitched
test-window returns are the out-of-sample track record: the closest thing a
backtest can give you to "how would this have done if I'd been running it."

`ensemble_k` controls how many of the top training-window parameter sets
share capital in the test window. k=1 is winner-take-all; k=3 splits capital
across the top 3, which damps the noise in crowning a single winner.

This is also the system's "continual learning" mechanism: re-run it on a
schedule, and the most recent fold's winning parameters become the live
candidate (subject to champion/challenger promotion rules).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import pandas as pd

from trader.backtest.engine import run_backtest
from trader.backtest.metrics import sharpe


@dataclass
class Fold:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_end: pd.Timestamp
    top_params: list[dict]  # the k parameter sets sharing capital, best first
    train_sharpe: float  # of the single best combo
    test_returns: pd.Series


@dataclass
class WalkForwardResult:
    folds: list[Fold]
    equity: pd.Series  # stitched out-of-sample equity curve

    def params_by_fold(self) -> pd.DataFrame:
        rows = [
            {
                "train_end": f.train_end.date(),
                "test_end": f.test_end.date(),
                "train_sharpe": round(f.train_sharpe, 2),
                "chosen (best first)": "  |  ".join(
                    "/".join(str(v) for v in p.values()) for p in f.top_params
                ),
            }
            for f in self.folds
        ]
        return pd.DataFrame(rows)


def expand_grid(param_grid: dict[str, list]) -> list[dict]:
    keys = list(param_grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*param_grid.values())]


def walk_forward(
    prices: pd.DataFrame,
    strategy_factory,
    param_grid: dict[str, list],
    train_years: int = 5,
    test_years: int = 1,
    cost_bps: float = 10.0,
    initial_capital: float = 100_000.0,
    ensemble_k: int = 1,
) -> WalkForwardResult:
    """`strategy_factory(**params)` must return a Strategy.

    Signals are causal (weights at date D use only data up to D), so each
    parameter set is backtested once over the full history and folds simply
    slice its daily return series. Training windows roll forward by
    `test_years` each fold.
    """
    combos = expand_grid(param_grid)

    # Pre-compute full-history daily returns per parameter combo.
    returns_by_combo: list[pd.Series] = []
    for params in combos:
        strategy = strategy_factory(**params)
        weights = strategy.generate_weights(prices)
        result = run_backtest(prices, weights, cost_bps=cost_bps, initial_capital=initial_capital)
        returns_by_combo.append(result.returns)

    start = prices.index[0]
    end = prices.index[-1]
    folds: list[Fold] = []
    test_chunks: list[pd.Series] = []

    train_start = start
    while True:
        train_end = train_start + pd.DateOffset(years=train_years)
        test_end = train_end + pd.DateOffset(years=test_years)
        if train_end >= end:
            break

        scored = []
        for idx, returns in enumerate(returns_by_combo):
            s = sharpe(returns.loc[train_start:train_end])
            if pd.notna(s):
                scored.append((s, idx))
        if not scored:
            break
        scored.sort(reverse=True)
        top = scored[: max(1, ensemble_k)]

        test_slice = slice(train_end + pd.Timedelta(days=1), min(test_end, end))
        # Equal capital across the top-k sleeves -> average of their returns.
        sleeve_returns = pd.concat(
            [returns_by_combo[idx].loc[test_slice] for _, idx in top], axis=1
        )
        test_returns = sleeve_returns.mean(axis=1)

        folds.append(
            Fold(
                train_start=train_start,
                train_end=train_end,
                test_end=min(test_end, end),
                top_params=[combos[idx] for _, idx in top],
                train_sharpe=top[0][0],
                test_returns=test_returns,
            )
        )
        test_chunks.append(test_returns)
        train_start = train_start + pd.DateOffset(years=test_years)

    oos_returns = pd.concat(test_chunks) if test_chunks else pd.Series(dtype=float)
    equity = initial_capital * (1 + oos_returns).cumprod()
    return WalkForwardResult(folds=folds, equity=equity)
