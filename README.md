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

## Scoreboard

The latest **[performance report](reports/performance.md)** (robot vs SPY
since inception) is regenerated and committed by every daily run.

## Live loop behavior

`run_daily.py` marks equity to the SQLite journal (`data/journal.db`) and
checks the kill switch every run; on the last trading day of each month it
recomputes targets with the parameter ensemble in `data/live_params.json`
(written by `run_walkforward.py --save-live-params`), applies risk limits,
and trades the difference. Idle cash is parked in BIL (T-bills), matching
the backtest.

Charts land in `reports/`.

## Champion vs Challenger (two independent bots)

The system runs two bots over one shared codebase. They share **all**
infrastructure (data, backtest engine, walk-forward, risk layer, runner,
journal, broker) and differ only in strategy, Alpaca account, and file paths
— a single `BotConfig` ([`src/trader/bots.py`](src/trader/bots.py)) carries
those differences.

| | Champion | Challenger |
|---|---|---|
| Strategy | momentum ensemble (unchanged) | momentum + mean-reversion sleeves, regime model, 12% vol target |
| Alpaca keys | `ALPACA_API_KEY/SECRET` | `CHALLENGER_ALPACA_KEY/SECRET` |
| Journal | `data/journal.db` | `data/journal_challenger.db` |
| Live params | `data/live_params.json` | `data/live_params_challenger.json` |
| Report | `reports/performance.md` | `reports/performance_challenger.md` |
| Workflows | `daily.yml`, `monthly-refresh.yml` | `daily-challenger.yml`, `monthly-refresh-challenger.yml` |

Run either bot by passing `--bot`:

```powershell
.venv\Scripts\python scripts\run_daily.py --bot challenger --dry-run
.venv\Scripts\python scripts\run_walkforward.py --bot challenger --start 2000-01-01 --save-live-params
.venv\Scripts\python scripts\run_compare.py          # champion vs challenger, full metrics
```

`run_compare.py` writes [`reports/champion_vs_challenger.html`](reports/champion_vs_challenger.html)
and `.csv` (CAGR, annual return, Sharpe, Sortino, vol, max drawdown, win rate,
turnover) plus an equity chart.

Two distinct "champion/challenger" mechanisms exist, don't confuse them:
- **Bot-level** (this section): two *different strategies* on two *separate
  paper accounts*, compared live. You decide if/when to crown a new champion.
- **Parameter-level** (`run_monthly_refresh.py`): within *one* bot, a freshly
  re-fit parameter set is promoted only if it beats the incumbent out-of-sample.

### The challenger's design (per the build spec)

1. **Mean-reversion sleeve** ([`mean_reversion.py`](src/trader/strategies/mean_reversion.py)) —
   buys oversold names (negative z-score) that are still in a longer uptrend.
2. **Volatility targeting** — scales the risk book to a 12% annualized target
   using causal ex-ante covariance; capped at fully-invested (no leverage).
3. **Regime model** ([`regime.py`](src/trader/strategies/regime.py)) — replaces
   the binary SPY>200DMA switch with RISK_ON / NEUTRAL / RISK_OFF (SPY trend +
   realized vol), scaling exposure 1.0 / 0.5 / 0.0.
4. **Ensemble construction** ([`challenger.py`](src/trader/strategies/challenger.py)) —
   blends momentum 60% / mean-reversion 40% (configurable), then applies regime
   and vol-target scaling, remainder to T-bills.
5. **Same safeguards** — position caps, gross-exposure cap, kill switch,
   order throttle, no-margin budget all apply unchanged (shared risk layer).

## Architecture

| Layer | Where | Job |
|---|---|---|
| Data | `src/trader/data/` | Adjusted daily prices (yfinance for history, cached locally) |
| Strategy | `src/trader/strategies/` | Prices in, target weights out (causal). Momentum, mean-reversion, regime, ensemble, challenger. |
| Bots | `src/trader/bots.py` | `BotConfig` registry: champion + challenger over shared infra |
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
- [x] Cloud automation via GitHub Actions (daily loop, no local machine needed)
- [x] Daily evaluation report vs SPY (`reports/performance.md`)
- [x] Monthly learning refresh + champion/challenger promotion gate
      (`scripts/run_monthly_refresh.py`, runs the 1st of each month)
- [x] Second strategy family (mean reversion) + Challenger bot
- [x] Champion vs Challenger framework (two bots, shared infra, comparison report)
- [ ] Point-in-time universe (survivorship fix)
- [ ] Second Alpaca paper account for the challenger (user step — see deployment guide)
