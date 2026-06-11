"""Verify the Alpaca paper trading connection.

Usage:
    python scripts/verify_alpaca.py               # check account + market clock
    python scripts/verify_alpaca.py --test-order  # also place & cancel a tiny limit order
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-order", action="store_true")
    args = parser.parse_args()

    from trader.execution.broker import AlpacaBroker

    broker = AlpacaBroker()
    account = broker.account()
    clock = broker.clock()

    mode = "PAPER" if broker.paper else "*** LIVE ***"
    print(f"Connected to Alpaca ({mode})")
    print(f"  Account status : {account.status}")
    print(f"  Equity         : ${float(account.equity):,.2f}")
    print(f"  Buying power   : ${float(account.buying_power):,.2f}")
    print(f"  Market open    : {clock.is_open}")
    print(f"  Next open      : {clock.next_open}")
    print(f"  Next close     : {clock.next_close}")

    if args.test_order:
        if not broker.paper:
            print("\nRefusing to place a test order on a LIVE account.")
            return
        # Deep out-of-the-money limit buy: it will rest unfilled, proving the
        # order path works, then we cancel it.
        print("\nPlacing test order: limit buy 1 AAPL @ $1.00 ...")
        order = broker.submit_limit_order("AAPL", 1, "buy", 1.00)
        print(f"  Order accepted, id={order.id}, status={order.status}")
        broker.cancel_all_orders()
        print("  Cancelled all open orders. Order path verified.")


if __name__ == "__main__":
    main()
