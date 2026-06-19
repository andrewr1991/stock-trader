"""Performance metrics. All annualization assumes 252 trading days."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def cagr(equity: pd.Series) -> float:
    equity = equity.dropna()
    years = len(equity) / TRADING_DAYS
    if years <= 0 or equity.iloc[0] <= 0:
        return float("nan")
    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1


def annual_vol(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(TRADING_DAYS))


def sharpe(returns: pd.Series, rf_annual: float = 0.0) -> float:
    excess = returns - rf_annual / TRADING_DAYS
    vol = excess.std()
    if vol == 0:
        return float("nan")
    return float(excess.mean() / vol * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf_annual: float = 0.0) -> float:
    """Like Sharpe, but penalizes only downside volatility."""
    excess = returns - rf_annual / TRADING_DAYS
    downside = excess[excess < 0]
    dd = downside.std()
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    return float((equity / running_max - 1.0).min())


def win_rate(equity: pd.Series, freq: str = "ME") -> float:
    """Fraction of periods (default monthly) with a positive return."""
    periodic = equity.resample(freq).last().pct_change().dropna()
    if periodic.empty:
        return float("nan")
    return float((periodic > 0).mean())


def annual_turnover(turnover: pd.Series | None) -> float:
    """One-way traded fraction per year, from the engine's per-rebalance series."""
    if turnover is None:
        return float("nan")
    nonzero = turnover[turnover > 0]
    if nonzero.empty:
        return 0.0
    years = (turnover.index[-1] - turnover.index[0]).days / 365.25
    return float(nonzero.sum() / years) if years > 0 else float("nan")


def beta_alpha(returns: pd.Series, bench_returns: pd.Series) -> tuple[float, float]:
    """OLS beta and annualized alpha vs. the benchmark."""
    df = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if len(df) < 2:
        return float("nan"), float("nan")
    r, b = df.iloc[:, 0], df.iloc[:, 1]
    var = b.var()
    beta = float(r.cov(b) / var) if var > 0 else float("nan")
    alpha_daily = r.mean() - beta * b.mean()
    return beta, float(alpha_daily * TRADING_DAYS)


def summary(equity: pd.Series, bench_equity: pd.Series | None = None) -> dict:
    returns = equity.pct_change().fillna(0.0)
    out = {
        "CAGR": cagr(equity),
        "Volatility": annual_vol(returns),
        "Sharpe": sharpe(returns),
        "Max Drawdown": max_drawdown(equity),
    }
    if bench_equity is not None:
        bench_returns = bench_equity.pct_change().fillna(0.0)
        beta, alpha = beta_alpha(returns, bench_returns)
        out["Benchmark CAGR"] = cagr(bench_equity)
        out["Excess CAGR"] = out["CAGR"] - out["Benchmark CAGR"]
        out["Beta"] = beta
        out["Alpha (ann.)"] = alpha
    return out


def format_summary(stats: dict) -> str:
    lines = []
    for key, value in stats.items():
        if key in ("Sharpe", "Beta"):
            lines.append(f"  {key:<16} {value:>8.2f}")
        else:
            lines.append(f"  {key:<16} {value:>8.1%}")
    return "\n".join(lines)
