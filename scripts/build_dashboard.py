"""Build a single self-contained dashboard (docs/index.html) for GitHub Pages.

Reads all three bots' live journals + their latest target allocations, pulls
SPY for the same window, and renders one page: per-bot stat cards, a combined
growth-of-100 chart, and current allocations. Regenerated daily by the
multi-asset workflow (which runs last, after all three bots have logged), so
the page always reflects the freshest committed state.

Usage: python scripts/build_dashboard.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from trader.backtest.metrics import max_drawdown
from trader.bots import champion_bot, challenger_bot, multiasset_bot
from trader.config import BENCHMARK, PROJECT_ROOT
from trader.data.loader import load_prices
from trader.live.journal import Journal

DOCS = PROJECT_ROOT / "docs"
LABELS = {"champion": "Champion (momentum)",
          "challenger": "Challenger (multi-sleeve)",
          "multiasset": "Multi-asset (trend)"}
COLORS = {"champion": "#378ADD", "challenger": "#7F77DD", "multiasset": "#1D9E75"}


def latest_targets(db: Path) -> tuple[str | None, list[tuple[str, float]]]:
    if not Path(db).exists():
        return None, []
    c = sqlite3.connect(str(db))
    row = c.execute("SELECT MAX(date) FROM targets").fetchone()[0]
    if not row:
        return None, []
    rows = c.execute(
        "SELECT symbol, weight FROM targets WHERE date = ? AND weight > 0.0005 ORDER BY weight DESC",
        (row,),
    ).fetchall()
    return row, [(s, float(w)) for s, w in rows]


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    bots = [champion_bot(), challenger_bot(), multiasset_bot()]

    bot_data = []
    all_dates: set[str] = set()
    for bot in bots:
        df = Journal(bot.journal_db).equity_history()
        if df.empty:
            continue
        df = df.sort_values("date")
        df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        growth = (df["equity"] / df["equity"].iloc[0] * 100).round(2)
        series = dict(zip(df["d"], growth))
        all_dates.update(series)
        reb_date, targets = latest_targets(bot.journal_db)
        bot_data.append({
            "key": bot.name,
            "label": LABELS.get(bot.name, bot.name),
            "color": COLORS.get(bot.name, "#888"),
            "equity": float(df["equity"].iloc[-1]),
            "ret": float(df["equity"].iloc[-1] / df["equity"].iloc[0] - 1),
            "maxdd": max_drawdown(df["equity"]),
            "days": int((pd.to_datetime(df["date"].iloc[-1]) - pd.to_datetime(df["date"].iloc[0])).days),
            "start": df["d"].iloc[0],
            "series": series,
            "last_rebalance": reb_date,
            "targets": targets,
        })

    # SPY benchmark over the full span, normalized to 100 at the earliest date.
    spy_series: dict[str, float] = {}
    spy_ret = 0.0
    if all_dates:
        start = min(all_dates)
        spy = load_prices([BENCHMARK], start=start, refresh=True)[BENCHMARK].dropna()
        spy.index = spy.index.strftime("%Y-%m-%d")
        if len(spy):
            base = spy.iloc[0]
            spy_series = {d: round(float(v / base * 100), 2) for d, v in spy.items()}
            all_dates.update(spy_series)
            common = [d for d in sorted(all_dates) if d in spy_series]
            if common:
                spy_ret = spy_series[common[-1]] / 100 - 1

    labels = sorted(all_dates)

    def aligned(series: dict) -> list:
        return [series.get(d) for d in labels]

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "labels": labels,
        "spy": {"series": aligned(spy_series), "ret": spy_ret},
        "bots": [{**b, "aligned": aligned(b["series"])} for b in bot_data],
    }

    (DOCS / "index.html").write_text(_render(payload), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("")  # serve the raw file, skip Jekyll
    print(f"Wrote {DOCS / 'index.html'} ({len(bot_data)} bots, {len(labels)} dates)")


def _render(p: dict) -> str:
    cards = ""
    for b in p["bots"]:
        excess = b["ret"] - p["spy"]["ret"]
        alloc = "".join(
            f"<tr><td>{s}</td><td style='text-align:right'>{w:.0%}</td></tr>"
            for s, w in b["targets"][:12]
        ) or "<tr><td colspan='2' style='color:#888'>in cash / no positions</td></tr>"
        cards += f"""
        <div class="card">
          <div class="dot" style="background:{b['color']}"></div>
          <h2>{b['label']}</h2>
          <div class="big">${b['equity']:,.0f}</div>
          <div class="sub">{b['ret']:+.2%} since {b['start']} · {b['days']}d live</div>
          <div class="row"><span>vs SPY</span><b style="color:{'#1a8a4a' if excess>=0 else '#c0392b'}">{excess:+.2%}</b></div>
          <div class="row"><span>max drawdown</span><b>{b['maxdd']:.2%}</b></div>
          <div class="row"><span>last rebalance</span><b>{b['last_rebalance'] or '—'}</b></div>
          <table class="alloc"><thead><tr><th>current allocation</th><th></th></tr></thead><tbody>{alloc}</tbody></table>
        </div>"""

    datasets = []
    for b in p["bots"]:
        datasets.append(f"{{label:'{b['label']}',data:{json.dumps(b['aligned'])},"
                        f"borderColor:'{b['color']}',backgroundColor:'{b['color']}',"
                        f"borderWidth:2,pointRadius:0,spanGaps:true,tension:0.1}}")
    datasets.append(f"{{label:'SPY',data:{json.dumps(p['spy']['series'])},"
                    f"borderColor:'#D85A30',backgroundColor:'#D85A30',borderWidth:2,"
                    f"borderDash:[6,4],pointRadius:0,spanGaps:true,tension:0.1}}")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading bots dashboard</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;max-width:1000px;margin:0 auto;padding:1.5rem 1rem;color:#1a1a1a;background:#fafafa}}
 h1{{font-weight:600;margin:0 0 .25rem}} .upd{{color:#777;font-size:.85rem;margin-bottom:1.5rem}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;margin-bottom:1.5rem}}
 .card{{background:#fff;border:1px solid #e7e7e7;border-radius:12px;padding:1rem 1.1rem;position:relative}}
 .dot{{width:10px;height:10px;border-radius:50%;position:absolute;top:1.2rem;right:1.1rem}}
 .card h2{{font-size:.95rem;font-weight:600;margin:0 0 .5rem;color:#444}}
 .big{{font-size:1.7rem;font-weight:600}} .sub{{color:#777;font-size:.8rem;margin-bottom:.6rem}}
 .row{{display:flex;justify-content:space-between;font-size:.85rem;padding:.15rem 0;color:#555}}
 .alloc{{width:100%;border-collapse:collapse;margin-top:.6rem;font-size:.8rem}}
 .alloc th{{text-align:left;color:#999;font-weight:500;border-bottom:1px solid #eee;padding-bottom:.2rem}}
 .alloc td{{padding:.12rem 0;color:#444}}
 .chartwrap{{background:#fff;border:1px solid #e7e7e7;border-radius:12px;padding:1rem;height:420px}}
 .note{{color:#888;font-size:.8rem;margin-top:1rem;line-height:1.5}}
 a{{color:#378ADD}}
</style></head><body>
<h1>Trading bots — live paper dashboard</h1>
<div class="upd">Auto-updated {p['updated']} · paper trading on Alpaca</div>
<div class="cards">{cards}</div>
<div class="chartwrap"><canvas id="c"></canvas></div>
<p class="note">Growth of 100 since each bot's inception (paper money). Early days —
judge on months, not weeks. Bots fall less in crashes rather than rise faster in rallies;
the edge to watch is risk-adjusted, not raw return. SPY shown as the benchmark.</p>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('c'),{{type:'line',
 data:{{labels:{json.dumps(p['labels'])},datasets:[{','.join(datasets)}]}},
 options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
  plugins:{{legend:{{position:'top',labels:{{boxWidth:12,usePointStyle:true}}}}}},
  scales:{{y:{{title:{{display:true,text:'Growth of 100'}}}},
   x:{{ticks:{{maxTicksLimit:12,maxRotation:0}}}}}}}}}});
</script></body></html>"""


if __name__ == "__main__":
    main()
