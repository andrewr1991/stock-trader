"""Thin wrapper around Alpaca's trading API.

Everything broker-specific lives here so the rest of the system never
imports alpaca directly. Paper vs. live is controlled by ALPACA_PAPER in
.env — leave it true until the system has earned trust.
"""
from __future__ import annotations

from datetime import date

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import (
    GetCalendarRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)

from trader.config import ALPACA_API_KEY, ALPACA_PAPER, ALPACA_SECRET_KEY


class AlpacaBroker:
    def __init__(self, api_key: str | None = None, secret_key: str | None = None,
                 paper: bool | None = None):
        """Credentials default to the champion's (.env globals); the challenger
        bot passes its own. Passing nothing reproduces the original behavior."""
        api_key = api_key if api_key is not None else ALPACA_API_KEY
        secret_key = secret_key if secret_key is not None else ALPACA_SECRET_KEY
        paper = ALPACA_PAPER if paper is None else paper
        if not api_key or not secret_key:
            raise RuntimeError(
                "Alpaca keys missing. Copy .env.example to .env and fill in "
                "your paper trading API keys."
            )
        self.client = TradingClient(api_key, secret_key, paper=paper)
        self.paper = paper

    def account(self):
        return self.client.get_account()

    def clock(self):
        return self.client.get_clock()

    def equity(self) -> float:
        return float(self.client.get_account().equity)

    def positions(self) -> dict[str, float]:
        """Current holdings as {symbol: market_value}."""
        return {p.symbol: float(p.market_value) for p in self.client.get_all_positions()}

    def submit_notional_order(self, symbol: str, notional: float, side: str):
        """Dollar-sized market order (fractional shares)."""
        order = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order)

    def close_position(self, symbol: str):
        return self.client.close_position(symbol)

    def close_all_positions(self):
        return self.client.close_all_positions(cancel_orders=True)

    def trading_days(self, start: date, end: date) -> list[date]:
        cal = self.client.get_calendar(GetCalendarRequest(start=start, end=end))
        return [c.date for c in cal]

    def submit_market_order(self, symbol: str, qty: float, side: str):
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order)

    def submit_limit_order(self, symbol: str, qty: float, side: str, limit_price: float):
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
        )
        return self.client.submit_order(order)

    def cancel_all_orders(self):
        return self.client.cancel_orders()
