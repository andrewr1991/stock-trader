"""Daily live paper-trading loop. Schedule this once per trading day.

Usage:
    python scripts/run_daily.py                      # champion, normal run
    python scripts/run_daily.py --bot challenger     # the challenger bot
    python scripts/run_daily.py --dry-run            # show orders, trade nothing
    python scripts/run_daily.py --force              # rebalance even if not month-end
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse


def main():
    from trader.bots import BOT_NAMES, get_bot
    from trader.live.runner import run_daily

    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="champion", choices=BOT_NAMES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    run_daily(get_bot(args.bot), dry_run=args.dry_run, force_rebalance=args.force)


if __name__ == "__main__":
    main()
