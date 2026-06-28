"""Central configuration for the trading system."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
REPORTS_DIR = PROJECT_ROOT / "reports"

load_dotenv(PROJECT_ROOT / ".env")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() != "false"

BENCHMARK = "SPY"

# Where idle cash sits. BIL is a 1-3 month T-bill ETF: when the trend filter
# pulls the portfolio out of stocks, capital earns the T-bill yield instead
# of 0%. (Data begins May 2007; before that, backtest cash earns nothing.)
CASH_ETF = "BIL"

# Live trading state (CHAMPION bot — the original, unchanged)
LIVE_PARAMS_FILE = PROJECT_ROOT / "data" / "live_params.json"
JOURNAL_DB = PROJECT_ROOT / "data" / "journal.db"

# --- CHALLENGER bot ---------------------------------------------------------
# A second, independent paper-trading bot that runs the multi-sleeve
# ChallengerStrategy. It shares ALL infrastructure with the champion but keeps
# its own Alpaca account, journal, params, and reports. Create a SECOND Alpaca
# paper account for it and put its keys here (or as GitHub secrets). Until
# these are set, the challenger live loop simply no-ops — backtests and
# walk-forward still run without keys.
CHALLENGER_ALPACA_KEY = os.getenv("CHALLENGER_ALPACA_KEY", "")
CHALLENGER_ALPACA_SECRET = os.getenv("CHALLENGER_ALPACA_SECRET", "")
CHALLENGER_JOURNAL_DB = PROJECT_ROOT / "data" / "journal_challenger.db"
CHALLENGER_PARAMS_FILE = PROJECT_ROOT / "data" / "live_params_challenger.json"

# Challenger strategy knobs (all overridable per-instance; these are the
# central defaults). Kept deliberately few — every added free parameter is a
# new chance to overfit (see brain-ablation-findings).
CHALLENGER_VOL_TARGET = 0.12        # annualized portfolio volatility target
CHALLENGER_MOMENTUM_WEIGHT = 0.60   # sleeve blend: momentum
CHALLENGER_MR_WEIGHT = 0.40         # sleeve blend: mean reversion

# Risk limits enforced by the live loop (see trader/risk/manager.py).
# Position cap: top_n=5 equal weight means ~20% per name in normal operation,
# so the cap only binds when something is off.
# Kill switch: the strategy's worst historical drawdown is -32%, so the
# switch sits beyond it — it exists to catch "something is broken", not to
# stop normal volatility (a tighter stop would have fired during drawdowns
# the strategy recovered from, locking in the loss).
MAX_POSITION_WEIGHT = 0.25
KILL_SWITCH_DRAWDOWN = 0.40

# Spending guards for the live loop (see trader/live/runner.py):
# - never target more than this fraction of EQUITY (margin is untouchable
#   even though Alpaca offers it; the rest stays in cash)
GROSS_EXPOSURE_CAP = 0.98
# - a run that wants to place more orders than this is assumed buggy and aborts
MAX_ORDERS_PER_RUN = 60
# - a single-run equity reading below this fraction of the prior mark is treated
#   as a transient bad read (settlement lag / API glitch), not a real loss: the
#   run is skipped so it can neither poison the journal nor trip the kill switch.
#   No diversified large-cap book drops >50% in a day, so this only catches errors.
SUSPECT_EQUITY_FRACTION = 0.5

# Liquid US large caps used for backtesting and paper trading.
# CAVEAT: this is today's list of survivors, so backtests over it carry
# survivorship bias — treat absolute backtest numbers as optimistic and
# focus on relative comparisons between strategies/parameters.
UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "NFLX",
    "AMD", "MU", "INTC", "CSCO", "ORCL", "IBM", "QCOM", "TXN", "ADBE", "CRM",
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "USB", "V", "MA",
    "JNJ", "PFE", "MRK", "ABT", "LLY", "BMY", "AMGN", "GILD", "UNH",
    "XOM", "CVX", "COP", "SLB",
    "PG", "KO", "PEP", "WMT", "COST", "TGT", "HD", "LOW", "MCD", "SBUX", "NKE",
    "DIS", "CMCSA", "T", "VZ",
    "CAT", "DE", "BA", "HON", "GE", "MMM", "UNP", "FDX", "UPS",
    "NEE", "DUK", "SO",
]

# Transaction cost assumption, in basis points of traded value (round trip
# is charged on each side as turnover happens). 10 bps is conservative for
# liquid large caps; commissions at Alpaca are zero but slippage is not.
COST_BPS = 10.0

INITIAL_CAPITAL = 100_000.0
