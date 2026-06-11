"""Daily live paper-trading loop. Schedule this once per trading day.

Usage:
    python scripts/run_daily.py                # normal daily run
    python scripts/run_daily.py --dry-run      # show intended orders, trade nothing
    python scripts/run_daily.py --force        # rebalance even if not month-end
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from trader.live.runner import run_daily

    run_daily(dry_run=args.dry_run, force_rebalance=args.force)


if __name__ == "__main__":
    main()
