"""The daily live loop, shared by every bot.

Run once per trading day (ideally ~15:30-15:45 ET, so signals use
near-final prices and orders fill before the close; orders placed after
hours queue for the next open, which is also fine).

Every run:    mark equity to the bot's journal, check the kill switch.
Month-end:    recompute target weights with the bot's strategy, apply the
              shared risk limits, and trade the difference.

The only things that differ between bots are the strategy, the Alpaca
credentials, and the file paths — all carried by the BotConfig. Decisions
mirror the backtest exactly: same strategy code, same monthly cadence, same
risk layer. The only difference is who executes the trades.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from trader.bots import BotConfig, champion_bot
from trader.config import (
    BENCHMARK,
    CASH_ETF,
    GROSS_EXPOSURE_CAP,
    INITIAL_CAPITAL,
    KILL_SWITCH_DRAWDOWN,
    MAX_ORDERS_PER_RUN,
    MAX_POSITION_WEIGHT,
    SUSPECT_EQUITY_FRACTION,
    UNIVERSE,
)
from trader.data.loader import load_prices
from trader.live.journal import Journal
from trader.risk.manager import RiskManager

MIN_TRADE_NOTIONAL = 25.0  # ignore dust-sized rebalance deltas


def is_suspect_equity(equity: float, last: float | None,
                      fraction: float = SUSPECT_EQUITY_FRACTION) -> bool:
    """True if `equity` is implausibly far below the previous mark — a likely
    transient bad read (settlement lag / API glitch) rather than a real loss."""
    return last is not None and last > 0 and equity < fraction * last


def compute_target_weights(bot: BotConfig) -> pd.Series:
    """Latest rebalance row from the bot's strategy, freshly downloaded data."""
    tickers = sorted(set(UNIVERSE) | {BENCHMARK, CASH_ETF})
    start = (pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d")
    prices = load_prices(tickers, start=start, refresh=True)
    weights = bot.strategy().generate_weights(prices).iloc[-1]
    return weights[weights > 0.0001]


def is_month_end_session(broker) -> bool:
    today = dt.date.today()
    month_end = (pd.Timestamp(today) + pd.offsets.MonthEnd(0)).date()
    if broker is not None:
        sessions = broker.trading_days(today.replace(day=1), month_end)
        return bool(sessions) and today == max(sessions)
    bdays = pd.bdate_range(today.replace(day=1), month_end)
    return bool(len(bdays)) and pd.Timestamp(today) == bdays[-1]


def run_daily(bot: BotConfig | None = None, dry_run: bool = False,
              force_rebalance: bool = False) -> None:
    bot = bot or champion_bot()
    tag = f"[{bot.name}]"
    journal = Journal(bot.journal_db)
    today = dt.date.today().isoformat()

    broker = None
    if bot.has_credentials():
        try:
            from trader.execution.broker import AlpacaBroker

            broker = AlpacaBroker(api_key=bot.api_key, secret_key=bot.secret_key,
                                  paper=bot.paper)
        except Exception as exc:
            if not dry_run:
                raise
            print(f"{tag} (dry run without broker: {exc})")
    elif not dry_run:
        # No keys configured (e.g. challenger before a second Alpaca account
        # is set up). No-op cleanly instead of failing the scheduled run.
        print(f"{tag} no Alpaca credentials configured; skipping live run.")
        return

    if broker is not None:
        equity = broker.equity()
        positions = broker.positions()
        # Guard: a transient bad equity read (settlement lag, API glitch) must
        # neither poison the journal nor trip the kill switch into liquidating a
        # real book. Skip the run; the next read confirms the true state.
        if is_suspect_equity(equity, journal.last_equity()):
            journal.log_event("SUSPECT_EQUITY",
                              f"read ${equity:,.2f} vs last ${journal.last_equity():,.2f}; skipped")
            print(f"{tag} SUSPECT equity ${equity:,.2f} vs last "
                  f"${journal.last_equity():,.2f} — skipping run, no action taken.")
            return
    else:
        equity = INITIAL_CAPITAL
        positions = {}

    peak = max(journal.peak_equity() or equity, equity)
    drawdown = equity / peak - 1.0
    journal.log_equity(today, equity, drawdown)
    print(f"{tag} Equity ${equity:,.2f} | peak ${peak:,.2f} | drawdown {drawdown:.1%}")

    risk = RiskManager(
        max_position_weight=MAX_POSITION_WEIGHT,
        max_gross_exposure=GROSS_EXPOSURE_CAP,
        kill_switch_drawdown=KILL_SWITCH_DRAWDOWN,
    )

    if drawdown <= -KILL_SWITCH_DRAWDOWN:
        journal.log_event("KILL_SWITCH", f"drawdown {drawdown:.1%}; liquidating everything")
        print(f"{tag} KILL SWITCH: drawdown {drawdown:.1%} breaches -{KILL_SWITCH_DRAWDOWN:.0%}. Liquidating.")
        if broker is not None and not dry_run:
            broker.cancel_all_orders()
            broker.close_all_positions()
        return

    if not (force_rebalance or is_month_end_session(broker)):
        print(f"{tag} Not a rebalance day (month-end). Equity logged; nothing to trade.")
        return

    # Guard: never rebalance twice in one day (e.g. the script run twice by
    # accident, or a scheduler retry) — that would double-buy.
    if journal.last_event_date("REBALANCE") == today and not dry_run:
        journal.log_event("SKIP", "rebalance already executed today")
        print(f"{tag} Rebalance already executed today; refusing to trade again.")
        return

    print(f"{tag} Rebalance day. Computing targets ...")
    weights = compute_target_weights(bot)
    weights = risk.apply(weights, drawdown)
    targets = {sym: float(w) * equity for sym, w in weights.items()}
    journal.log_targets(today, {s: float(w) for s, w in weights.items()}, targets)

    deltas = []
    for sym in sorted(set(targets) | set(positions)):
        delta = targets.get(sym, 0.0) - positions.get(sym, 0.0)
        if abs(delta) >= MIN_TRADE_NOTIONAL:
            deltas.append((sym, delta))
    sells = [(s, d) for s, d in deltas if d < 0]
    buys = [(s, d) for s, d in deltas if d > 0]

    # Guard: runaway-order circuit breaker. A correct rebalance of this
    # strategy is a few dozen orders at most; more means a bug somewhere.
    if len(deltas) > MAX_ORDERS_PER_RUN:
        journal.log_event("ABORT", f"{len(deltas)} orders requested > {MAX_ORDERS_PER_RUN} cap")
        print(f"{tag} ABORT: {len(deltas)} orders requested (cap {MAX_ORDERS_PER_RUN}). Nothing traded.")
        return

    # Guard: total buys can never exceed total equity (sanity backstop).
    total_buys = sum(d for _, d in buys)
    if total_buys > equity:
        journal.log_event("ABORT", f"buys ${total_buys:,.0f} exceed equity ${equity:,.0f}")
        print(f"{tag} ABORT: buy total exceeds account equity. Nothing traded.")
        return

    # Guard: spend only what we actually have — current cash plus sale
    # proceeds (haircut 1% for price movement), never margin. If the budget
    # comes up short, every buy is scaled down proportionally.
    cash_on_hand = max(0.0, equity - sum(positions.values()))
    budget = cash_on_hand + sum(abs(d) for _, d in sells) * 0.99
    if total_buys > budget and total_buys > 0:
        scale = budget / total_buys
        buys = [(s, d * scale) for s, d in buys]
        buys = [(s, d) for s, d in buys if d >= MIN_TRADE_NOTIONAL]
        journal.log_event(
            "BUY_THROTTLE",
            f"buys ${total_buys:,.0f} > budget ${budget:,.0f}; scaled by {scale:.3f}",
        )
        print(f"{tag} Buys throttled to budget ${budget:,.0f} (no margin, ever).")

    print(f"{tag} Targets: { {s: f'{w:.1%}' for s, w in weights.items()} }")
    print(f"{tag} Orders: {len(sells)} sells, {len(buys)} buys")

    for sym, delta in sells + buys:  # sells first to free cash
        side = "sell" if delta < 0 else "buy"
        full_exit = side == "sell" and targets.get(sym, 0.0) == 0.0
        label = "close" if full_exit else side
        if dry_run:
            print(f"{tag}   [dry run] {label:>5} {sym:<6} ${abs(delta):>12,.2f}")
            journal.log_order(sym, label, abs(delta), "dry_run")
            continue
        try:
            if full_exit:
                order = broker.close_position(sym)
            else:
                order = broker.submit_notional_order(sym, abs(delta), side)
            journal.log_order(sym, label, abs(delta), "submitted", str(getattr(order, "id", "")))
            print(f"{tag}   {label:>5} {sym:<6} ${abs(delta):>12,.2f}  submitted")
        except Exception as exc:
            journal.log_order(sym, label, abs(delta), "error", detail=str(exc))
            print(f"{tag}   {label:>5} {sym:<6} ${abs(delta):>12,.2f}  ERROR: {exc}")

    journal.log_event("REBALANCE", f"{len(sells)} sells, {len(buys)} buys, equity ${equity:,.0f}")
    print(f"{tag} Done. All decisions journaled.")
