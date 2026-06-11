# Stock Trader

An automated US equity trading system, paper-trading on Alpaca. Goal: a
rigorous pipeline that finds out *honestly* whether a strategy beats SPY —
and refuses to fool us when it doesn't.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then paste your Alpaca PAPER keys into .env
```

## Quick start

```powershell
# 1. Verify the Alpaca paper connection (and optionally the order path)
.venv\Scripts\python scripts\verify_alpaca.py --test-order

# 2. Backtest momentum vs SPY since 2007
.venv\Scripts\python scripts\run_backtest.py

# 3. The honest version: walk-forward, parameters chosen out-of-sample
.venv\Scripts\python scripts\run_walkforward.py

# 4. Ablation: every brain refinement must earn its place out-of-sample
.venv\Scripts\python scripts\run_ablation.py

# 5. The live paper-trading loop (run once per trading day, ~15:30-15:45 ET)
.venv\Scripts\python scripts\run_daily.py --dry-run   # preview orders, trade nothing
.venv\Scripts\python scripts\run_daily.py             # the real (paper) thing
```

## Live loop behavior

`run_daily.py` marks equity to the SQLite journal (`data/journal.db`) and
checks the kill switch every run; on the last trading day of each month it
recomputes targets with the parameter ensemble in `data/live_params.json`
(written by `run_walkforward.py --save-live-params`), applies risk limits,
and trades the difference. Idle cash is parked in BIL (T-bills), matching
the backtest.

Charts land in `reports/`.

## Architecture

| Layer | Where | Job |
|---|---|---|
| Data | `src/trader/data/` | Adjusted daily prices (yfinance for history, cached locally) |
| Strategy | `src/trader/strategies/` | Prices in, target weights out. Signals must be causal. |
| Backtest | `src/trader/backtest/` | Share-based simulator, metrics, walk-forward validation |
| Risk | `src/trader/risk/` | Position caps, exposure cap, drawdown kill switch — veto power over any strategy |
| Execution | `src/trader/execution/` | Alpaca wrapper; the only file that talks to the broker |

## Ground rules (read before believing any backtest)

1. **Survivorship bias** — the universe in `config.py` is today's large caps,
   so backtests over it are optimistic. Compare strategies against each other
   and against SPY *on the same data*; don't treat the CAGR as a forecast.
2. **The walk-forward number is the real number.** A full-history backtest
   with hand-picked parameters is an in-sample fit. `run_walkforward.py`
   re-picks parameters each year using only prior data — trust that curve.
3. **Costs are charged at 10 bps** of traded value (`COST_BPS`). Zero
   commission ≠ zero cost; slippage is real.
4. **Paper-trade 3–6 months before real money.** "Matches SPY with a smaller
   drawdown" is a success milestone, not a failure.

## "Continual learning" design

Deliberately *not* online learning on live ticks (daily markets don't have
enough independent samples; real-time adaptation learns noise). Instead:

- **Scheduled walk-forward refits** — re-run `run_walkforward.py`
  periodically; the latest fold's winning parameters become the live
  *candidate*.
- **Champion/challenger** (planned) — candidate parameters paper-trade
  alongside the incumbent and are promoted only after beating it
  out-of-sample for a sustained period.
- **Decision journal** (planned) — every signal, order, and fill logged to
  SQLite so retraining learns from a clean record.

## Roadmap

- [x] Data layer with caching
- [x] Momentum strategy + SPY trend filter
- [x] Backtest engine, metrics, walk-forward validation
- [x] Risk manager (caps + kill switch)
- [x] Alpaca broker wrapper + connection check
- [x] Live paper-trading loop (`scripts/run_daily.py`)
- [x] Trade/decision journal (SQLite, `data/journal.db`)
- [x] T-bill yield on idle cash (BIL)
- [ ] Schedule the daily run via Windows Task Scheduler
- [ ] Daily evaluation report vs SPY (equity, Sharpe, drawdown)
- [ ] Champion/challenger promotion
- [ ] Point-in-time universe (survivorship fix)
- [ ] Second strategy family (mean reversion) for diversification
