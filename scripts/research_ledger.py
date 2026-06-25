"""CLI for the experiment ledger.

    python scripts/research_ledger.py list
    python scripts/research_ledger.py search momentum
    python scripts/research_ledger.py add --idea "soft regime curve" --decision deferred \
        --area regime --by claude --reason "evaluate on turnover not CAGR"
    python scripts/research_ledger.py export        # -> reports/experiment_ledger.md
    python scripts/research_ledger.py seed          # backfill history (only if empty)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse

from trader.config import REPORTS_DIR
from trader.research.ledger import Experiment, Ledger

EXPORT_PATH = REPORTS_DIR / "experiment_ledger.md"

# Backfill of every idea tried in the project so far. Dates approximate the
# project timeline; the point is the verdict, not the timestamp.
SEED = [
    # --- momentum "brain" (2026-06-09) ---
    Experiment("Rank buffer (hold past top_n)", "shipped", "momentum", "claude",
               "same excess return, turnover/costs ~-32%", "cheap win", date="2026-06-09"),
    Experiment("Top-k parameter ensemble", "shipped", "portfolio", "claude",
               "Sharpe 0.97->1.03, drawdown -36%->-32%", "free stability", date="2026-06-09"),
    Experiment("Vol-adjusted momentum ranking", "flag", "momentum", "claude",
               "cost 3-7%/yr excess OOS", "dilutes momentum in small universe", date="2026-06-09"),
    Experiment("Inverse-vol position weights", "flag", "sizing", "claude",
               "cost 3-7%/yr excess OOS", "tilts to low-vol names", date="2026-06-09"),
    # --- operations (2026-06-10/11) ---
    Experiment("T-bill yield on idle cash (BIL)", "shipped", "cash", "claude",
               "OOS excess slightly up; ~0.5-1%/yr at current rates", "free", date="2026-06-10"),
    Experiment("Live paper loop + decision journal", "shipped", "infra", "claude",
               "deployed", "foundation", date="2026-06-10"),
    Experiment("Param-level champion/challenger gate", "shipped", "infra", "claude",
               "deployed", "promote only if beats incumbent OOS", date="2026-06-11"),
    Experiment("Daily report + monthly refresh (cloud)", "shipped", "infra", "claude",
               "deployed via GitHub Actions", "autonomy", date="2026-06-11"),
    # --- challenger bot (2026-06-18) ---
    Experiment("Mean-reversion sleeve", "shipped", "strategy", "chatgpt",
               "part of challenger", "diversifies momentum", date="2026-06-18"),
    Experiment("Volatility targeting (12%)", "shipped", "portfolio", "chatgpt",
               "challenger vol hits 12% target", "risk control", date="2026-06-18"),
    Experiment("3-state regime model", "shipped", "regime", "chatgpt",
               "part of challenger", "replaces binary SPY>200DMA", date="2026-06-18"),
    Experiment("Challenger bot (multi-sleeve)", "shipped", "strategy", "chatgpt+claude",
               "OOS 11.6% CAGR, Sharpe 0.98, beta 0.34", "diversifier, 2nd live bot", date="2026-06-18"),
    # --- v2 review (2026-06-19) ---
    Experiment("Longer covariance lookback (60/90)", "flag", "vol-targeting", "chatgpt",
               "20 won: 11.7% vs 10.5-10.7% CAGR OOS", "short window adapts faster", date="2026-06-19"),
    Experiment("Market breadth in regime", "flag", "regime", "chatgpt",
               "~0.4%/yr drag, no DD benefit OOS", "no edge", date="2026-06-19"),
    Experiment("Unit tests + CI", "shipped", "infra", "chatgpt",
               "34 tests incl. no-look-ahead", "regression guard", date="2026-06-19"),
    Experiment("Expanded reporting (rolling/exposure/attribution)", "shipped", "reporting", "chatgpt",
               "diagnostics shipped", "observability", date="2026-06-19"),
    # --- universe + cadence (2026-06-23) ---
    Experiment("Point-in-time universe framework", "shipped", "data", "chatgpt",
               "framework only", "needs delisted prices to complete survivorship fix", date="2026-06-23"),
    Experiment("Weekly mean-reversion cadence", "flag", "mean-reversion", "chatgpt+claude",
               "CAGR 11.7->8.6%, Sharpe 0.99->0.80, turnover 2x", "turnover ate the signal", date="2026-06-23"),
    # --- beta + multi-asset (2026-06-24) ---
    Experiment("Beta-stability reporting", "shipped", "reporting", "chatgpt",
               "down-beta 0.18<static 0.29; per-fold beta unstable 0-1.4", "validates diversifier claim", date="2026-06-24"),
    Experiment("Multi-asset trend sleeve (design B)", "prototype", "multi-asset", "chatgpt+claude",
               "OOS 9.1% CAGR/Sharpe 0.97/-13% maxDD; +8.7% in 2008; 0.48 corr to challenger", "first new non-rejected idea; not yet live", date="2026-06-24"),
    # --- discussed, not yet tested ---
    Experiment("Operational risk controls (extra)", "deferred", "risk", "chatgpt",
               "", "mostly redundant with existing guards", date="2026-06-24"),
    Experiment("Execution alpha (close/open, stagger, limits)", "deferred", "execution", "chatgpt+claude",
               "", "expected <0.2%/yr; do sensitivity study first", date="2026-06-24"),
    Experiment("Continuous/soft regime curve", "deferred", "regime", "chatgpt+claude",
               "", "judge on turnover/whipsaw not CAGR", date="2026-06-24"),
    Experiment("Larger / point-in-time equity universe", "deferred", "data", "claude",
               "", "biggest honesty upgrade; needs delisted price data", date="2026-06-24"),
]


def cmd_add(args, ledger: Ledger):
    exp = Experiment(idea=args.idea, decision=args.decision, area=args.area or "",
                     proposed_by=args.by or "", result=args.result or "",
                     reason=args.reason or "", ref=args.ref or "", date=args.date or "")
    new_id = ledger.add(exp)
    print(f"added #{new_id}: {exp.idea} [{exp.decision}]")


def cmd_list(args, ledger: Ledger):
    df = ledger.all()
    if df.empty:
        print("ledger is empty — run `seed` to backfill history.")
        return
    for _, r in df.iterrows():
        print(f"  {r['date']}  {r['decision']:<9} {r['idea']}  ({r['proposed_by']})")
    print(f"\n{len(df)} experiments.")


def cmd_search(args, ledger: Ledger):
    df = ledger.search(args.term)
    if df.empty:
        print(f"no experiments match '{args.term}'.")
        return
    for _, r in df.iterrows():
        print(f"  {r['date']}  {r['decision']:<9} {r['idea']}")
        if r["result"]:
            print(f"            result: {r['result']}")
        if r["reason"]:
            print(f"            reason: {r['reason']}")


def cmd_export(args, ledger: Ledger):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(ledger.to_markdown(), encoding="utf-8")
    print(f"wrote {EXPORT_PATH} ({ledger.count()} experiments)")


def cmd_seed(args, ledger: Ledger):
    if ledger.count() > 0 and not args.force:
        print(f"ledger already has {ledger.count()} entries; use --force to add the seed anyway.")
        return
    for exp in SEED:
        ledger.add(exp)
    print(f"seeded {len(SEED)} experiments.")


def main():
    parser = argparse.ArgumentParser(description="Experiment ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--idea", required=True)
    p_add.add_argument("--decision", required=True)
    p_add.add_argument("--area")
    p_add.add_argument("--by")
    p_add.add_argument("--result")
    p_add.add_argument("--reason")
    p_add.add_argument("--ref")
    p_add.add_argument("--date")

    sub.add_parser("list")

    p_search = sub.add_parser("search")
    p_search.add_argument("term")

    sub.add_parser("export")

    p_seed = sub.add_parser("seed")
    p_seed.add_argument("--force", action="store_true")

    args = parser.parse_args()
    ledger = Ledger()
    {"add": cmd_add, "list": cmd_list, "search": cmd_search,
     "export": cmd_export, "seed": cmd_seed}[args.cmd](args, ledger)


if __name__ == "__main__":
    main()
