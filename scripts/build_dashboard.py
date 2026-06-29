"""Build a single self-contained dashboard (docs/index.html) for GitHub Pages.

Two sections:
  1. LIVE paper trading (from the bots' journals): stat cards + growth chart +
     a current market-regime indicator.
  2. STRATEGY CHARACTER (from the backtest, 2005-2026, clearly labelled): a
     risk-return scatter, annual-returns heatmap, correlation heatmap, and an
     underwater drawdown chart — the standard quant "tearsheet" views.

Regenerated daily by the multi-asset workflow (which runs last). The live
section uses real paper data; the tearsheet uses the backtest because that's
where there's enough history to be meaningful (the live record is only days
old). Both are labelled so they're never confused.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from trader.backtest.engine import buy_and_hold, run_backtest
from trader.backtest.metrics import annual_vol, cagr, max_drawdown, sharpe
from trader.bots import champion_bot, challenger_bot, multiasset_bot
from trader.config import BENCHMARK, COST_BPS, INITIAL_CAPITAL, PROJECT_ROOT
from trader.data.loader import load_prices
from trader.live.journal import Journal
from trader.strategies.regime import NEUTRAL, RISK_OFF, RISK_ON, RegimeModel

DOCS = PROJECT_ROOT / "docs"
BT_START = "2005-01-01"
LABELS = {"champion": "Champion", "challenger": "Challenger", "multiasset": "Multi-asset"}
COLORS = {"champion": "#378ADD", "challenger": "#7F77DD", "multiasset": "#1D9E75", "SPY": "#D85A30"}


def latest_targets(db: Path):
    if not Path(db).exists():
        return None, []
    c = sqlite3.connect(str(db))
    row = c.execute("SELECT MAX(date) FROM targets").fetchone()[0]
    if not row:
        return None, []
    rows = c.execute("SELECT symbol, weight FROM targets WHERE date=? AND weight>0.0005 "
                     "ORDER BY weight DESC", (row,)).fetchall()
    return row, [(s, float(w)) for s, w in rows]


def ret_color(v: float) -> str:
    a = min(1.0, abs(v) / 0.30) * 0.8
    return f"rgba(29,158,117,{a:.2f})" if v >= 0 else f"rgba(216,90,48,{a:.2f})"


def corr_color(c: float) -> str:
    if c >= 0:
        return f"rgba(216,90,48,{min(1.0, c) * 0.8:.2f})"
    return f"rgba(55,138,221,{min(1.0, -c) * 0.8:.2f})"


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    bots = [champion_bot(), challenger_bot(), multiasset_bot()]

    # ---------- LIVE section (journals) ----------
    bot_live, all_dates = [], set()
    for bot in bots:
        df = Journal(bot.journal_db).equity_history()
        if df.empty:
            continue
        df = df.sort_values("date")
        df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        growth = (df["equity"] / df["equity"].iloc[0] * 100).round(2)
        series = dict(zip(df["d"], growth))
        all_dates.update(series)
        reb, targets = latest_targets(bot.journal_db)
        bot_live.append({
            "key": bot.name, "label": LABELS[bot.name], "color": COLORS[bot.name],
            "equity": float(df["equity"].iloc[-1]),
            "ret": float(df["equity"].iloc[-1] / df["equity"].iloc[0] - 1),
            "maxdd": max_drawdown(df["equity"]),
            "days": int((pd.to_datetime(df["date"].iloc[-1]) - pd.to_datetime(df["date"].iloc[0])).days),
            "start": df["d"].iloc[0], "series": series, "last_rebalance": reb, "targets": targets,
        })

    spy_live, spy_ret = {}, 0.0
    if all_dates:
        spy = load_prices([BENCHMARK], start=min(all_dates), refresh=True)[BENCHMARK].dropna()
        spy.index = spy.index.strftime("%Y-%m-%d")
        if len(spy):
            spy_live = {d: round(float(v / spy.iloc[0] * 100), 2) for d, v in spy.items()}
            all_dates.update(spy_live)
            common = [d for d in sorted(all_dates) if d in spy_live]
            spy_ret = spy_live[common[-1]] / 100 - 1 if common else 0.0
    labels = sorted(all_dates)

    # ---------- BACKTEST tearsheet ----------
    daily = {}
    for bot in bots:
        prices = load_prices(bot.data_tickers, start=BT_START)
        res = run_backtest(prices, bot.strategy().generate_weights(prices),
                           cost_bps=COST_BPS, initial_capital=INITIAL_CAPITAL)
        daily[bot.name] = res.equity
        if bot.name == "champion":
            spy_eq = buy_and_hold(prices[BENCHMARK].loc[res.equity.index[0]:],
                                  initial_capital=INITIAL_CAPITAL).equity
            regime_state = RegimeModel().classify(prices).iloc[-1]
            spy = prices[BENCHMARK]
            above = bool(spy.iloc[-1] > spy.rolling(200).mean().iloc[-1])
            rvol = float(spy.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252))
    daily["SPY"] = spy_eq
    order = ["champion", "challenger", "multiasset", "SPY"]

    # scatter stats
    scatter = []
    for k in order:
        eq = daily[k]
        r = eq.pct_change().fillna(0)
        scatter.append({"label": LABELS.get(k, "SPY"), "color": COLORS[k],
                        "cagr": round(cagr(eq) * 100, 1), "vol": round(annual_vol(r) * 100, 1),
                        "sharpe": round(sharpe(r), 2)})

    # annual returns heatmap
    years = sorted({d.year for d in daily["champion"].index})
    annual = []
    for y in years:
        cells = []
        for k in order:
            ann = daily[k].resample("YE").last().pct_change()
            ann.index = ann.index.year
            v = ann.get(y, float("nan"))
            cells.append(None if v != v else round(float(v), 4))
        annual.append({"year": y, "cells": cells})

    # correlation (monthly returns)
    monthly = pd.DataFrame({k: daily[k].pct_change() for k in order}).resample("ME").apply(
        lambda x: (1 + x).prod() - 1).dropna()
    corr = monthly.corr().round(2).values.tolist()

    # underwater (monthly drawdown)
    uw_labels = [d.strftime("%Y-%m") for d in daily["champion"].resample("ME").last().index]
    underwater = {}
    for k in order:
        m = daily[k].resample("ME").last()
        dd = (m / m.cummax() - 1).round(4)
        underwater[k] = [round(float(v), 4) for v in dd.values]

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "labels": labels,
        "spy_live": [spy_live.get(d) for d in labels], "spy_ret": spy_ret,
        "bots": [{**b, "aligned": [b["series"].get(d) for d in labels]} for b in bot_live],
        "regime": {"state": regime_state, "above_200dma": above, "vol": round(rvol * 100, 1)},
        "scatter": scatter, "order": order, "labelmap": {**LABELS, "SPY": "SPY"},
        "annual": annual, "corr": corr, "uw_labels": uw_labels, "underwater": underwater,
        "colors": COLORS,
    }
    (DOCS / "index.html").write_text(_render(payload), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("")
    print(f"Wrote {DOCS/'index.html'} ({len(bot_live)} live bots, regime={regime_state})")


def _render(p: dict) -> str:
    # live cards
    cards = ""
    for b in p["bots"]:
        excess = b["ret"] - p["spy_ret"]
        alloc = "".join(f"<tr><td>{s}</td><td style='text-align:right'>{w:.0%}</td></tr>"
                        for s, w in b["targets"][:12]) or \
            "<tr><td colspan='2' style='color:#999'>in cash</td></tr>"
        cards += f"""<div class="card"><div class="dot" style="background:{b['color']}"></div>
          <h3>{b['label']}</h3><div class="big">${b['equity']:,.0f}</div>
          <div class="sub">{b['ret']:+.2%} since {b['start']} · {b['days']}d</div>
          <div class="r"><span>vs SPY</span><b style="color:{'#1a8a4a' if excess>=0 else '#c0392b'}">{excess:+.2%}</b></div>
          <div class="r"><span>max drawdown</span><b>{b['maxdd']:.2%}</b></div>
          <div class="r"><span>last rebalance</span><b>{b['last_rebalance'] or '—'}</b></div>
          <table class="al"><thead><tr><th>holdings</th><th></th></tr></thead><tbody>{alloc}</tbody></table></div>"""

    # regime light
    reg = p["regime"]["state"]
    rc = {"RISK_ON": "#1a8a4a", "NEUTRAL": "#e0a800", "RISK_OFF": "#c0392b"}[reg]
    rtext = {"RISK_ON": "Full exposure — uptrend, calm",
             "NEUTRAL": "Reduced exposure — elevated volatility",
             "RISK_OFF": "Defensive — downtrend or stress"}[reg]
    lights = "".join(
        f"<span class='bulb' style='background:{rc if s==reg else '#3a3a3a'};opacity:{1 if s==reg else .25}'></span>"
        for s in (RISK_ON, NEUTRAL, RISK_OFF))

    # scatter datasets
    sc = ",".join(f"{{label:'{d['label']}',data:[{{x:{d['vol']},y:{d['cagr']},r:{max(6,d['sharpe']*16):.0f}}}],"
                  f"backgroundColor:'{d['color']}cc',borderColor:'{d['color']}',borderWidth:1.5}}"
                  for d in p["scatter"])

    # annual heatmap
    head = "".join(f"<th>{p['labelmap'][k]}</th>" for k in p["order"])
    arows = ""
    for row in p["annual"]:
        tds = ""
        for v in row["cells"]:
            if v is None:
                tds += "<td></td>"
            else:
                tds += f"<td style='background:{ret_color(v)}'>{v*100:+.0f}%</td>"
        arows += f"<tr><th>{row['year']}</th>{tds}</tr>"

    # correlation heatmap
    chead = "".join(f"<th>{p['labelmap'][k]}</th>" for k in p["order"])
    crows = ""
    for i, k in enumerate(p["order"]):
        tds = ""
        for j in range(len(p["order"])):
            c = p["corr"][i][j]
            bg = "#e8e8e8" if i == j else corr_color(c)
            tds += f"<td style='background:{bg}'>{c:.2f}</td>"
        crows += f"<tr><th>{p['labelmap'][k]}</th>{tds}</tr>"

    uw = ",".join(f"{{label:'{p['labelmap'][k]}',data:{json.dumps(p['underwater'][k])},"
                  f"borderColor:'{p['colors'][k]}',backgroundColor:'{p['colors'][k]}22',"
                  f"borderWidth:1.5,pointRadius:0,fill:true,tension:0.1}}" for k in p["order"])

    growth = ",".join(f"{{label:'{b['label']}',data:{json.dumps(b['aligned'])},borderColor:'{b['color']}',"
                      f"backgroundColor:'{b['color']}',borderWidth:2,pointRadius:0,spanGaps:true,tension:0.1}}"
                      for b in p["bots"])
    growth += f",{{label:'SPY',data:{json.dumps(p['spy_live'])},borderColor:'#D85A30',backgroundColor:'#D85A30',borderWidth:2,borderDash:[6,4],pointRadius:0,spanGaps:true,tension:0.1}}"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Trading bots dashboard</title>
<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;max-width:1040px;margin:0 auto;padding:1.5rem 1rem;color:#1a1a1a;background:#fafafa}}
 h1{{font-weight:600;margin:0 0 .2rem}} h2{{font-weight:600;font-size:1.05rem;margin:2rem 0 .3rem}}
 .upd,.lbl{{color:#777;font-size:.82rem}} .lbl{{margin-bottom:.8rem}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}}
 .card{{background:#fff;border:1px solid #e7e7e7;border-radius:12px;padding:1rem;position:relative}}
 .dot{{width:10px;height:10px;border-radius:50%;position:absolute;top:1.1rem;right:1rem}}
 .card h3{{font-size:.9rem;margin:0 0 .4rem;color:#444}} .big{{font-size:1.6rem;font-weight:600}}
 .sub{{color:#777;font-size:.78rem;margin-bottom:.5rem}}
 .r{{display:flex;justify-content:space-between;font-size:.83rem;padding:.12rem 0;color:#555}}
 .al{{width:100%;border-collapse:collapse;margin-top:.5rem;font-size:.78rem}}
 .al th{{text-align:left;color:#999;font-weight:500;border-bottom:1px solid #eee}} .al td{{padding:.1rem 0;color:#444}}
 .panel{{background:#fff;border:1px solid #e7e7e7;border-radius:12px;padding:1rem}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}} @media(max-width:760px){{.grid2{{grid-template-columns:1fr}}}}
 .regime{{display:flex;align-items:center;gap:1rem;background:#fff;border:1px solid #e7e7e7;border-radius:12px;padding:1rem}}
 .bulb{{width:22px;height:22px;border-radius:50%;display:inline-block;margin-right:6px}}
 .hm{{width:100%;border-collapse:collapse;font-size:.72rem;text-align:center}}
 .hm th{{color:#888;font-weight:500;padding:3px}} .hm td{{padding:4px 3px;color:#222;border:1px solid #fff}}
 .hm tbody th{{text-align:right;padding-right:6px;color:#666}}
 .chart{{height:300px;position:relative}} .note{{color:#888;font-size:.78rem;margin-top:.6rem;line-height:1.5}}
</style></head><body>
<h1>Trading bots — live dashboard</h1><div class="upd">Auto-updated {p['updated']} · paper trading on Alpaca</div>

<h2>Live paper trading</h2><div class="lbl">Real paper-money results since each bot went live.</div>
<div class="cards">{cards}</div>
<div class="panel" style="margin-top:1rem"><div class="chart"><canvas id="growth"></canvas></div></div>

<h2>Current market regime</h2><div class="lbl">What the Challenger's regime model sees right now (live).</div>
<div class="regime"><div>{lights}</div><div><b style="color:{rc}">{reg.replace('_',' ')}</b><br>
  <span style="color:#666;font-size:.85rem">{rtext}</span><br>
  <span style="color:#999;font-size:.78rem">SPY {'above' if p['regime']['above_200dma'] else 'below'} 200-day avg · realized vol {p['regime']['vol']}%</span></div></div>

<h2>Strategy character — backtest 2005–2026</h2>
<div class="lbl">Backtested (after costs), survivor-biased universe → read relative, not absolute.</div>
<div class="grid2">
  <div class="panel"><b style="font-size:.9rem">Risk vs return</b><div class="note" style="margin:.2rem 0 .5rem">↖ up-left is better · bubble = Sharpe</div><div class="chart"><canvas id="scatter"></canvas></div></div>
  <div class="panel"><b style="font-size:.9rem">Strategy correlation</b><div class="note" style="margin:.2rem 0 .5rem">monthly returns · red = move together, blue = diversifying</div>
    <table class="hm"><thead><tr><th></th>{chead}</tr></thead><tbody>{crows}</tbody></table></div>
</div>
<div class="panel" style="margin-top:1rem"><b style="font-size:.9rem">Underwater — drawdown from peak</b>
  <div class="note" style="margin:.2rem 0 .5rem">how deep / how long below the high-water mark</div>
  <div class="chart"><canvas id="uw"></canvas></div></div>
<div class="panel" style="margin-top:1rem"><b style="font-size:.9rem">Annual returns</b>
  <div class="note" style="margin:.2rem 0 .5rem">green up, red down · note 2008 &amp; 2022</div>
  <table class="hm"><thead><tr><th>year</th>{head}</tr></thead><tbody>{arows}</tbody></table></div>

<p class="note">Live results judge the bots; the backtest describes their character. Falling less in
crashes (the −16% to −28% drawdowns vs SPY's −55%) is the edge to watch, more than raw return.</p>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const baseLine = (id, datasets, extra) => new Chart(document.getElementById(id), {{type:'line',
  data:{{labels:{json.dumps(p['labels'])},datasets:datasets}},
  options:Object.assign({{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
   plugins:{{legend:{{position:'top',labels:{{boxWidth:12,usePointStyle:true,font:{{size:11}}}}}}}}}}, extra||{{}})}});
baseLine('growth', [{growth}], {{scales:{{y:{{title:{{display:true,text:'Growth of 100'}}}}}}}});
new Chart(document.getElementById('uw'), {{type:'line',
  data:{{labels:{json.dumps(p['uw_labels'])},datasets:[{uw}]}},
  options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},
   plugins:{{legend:{{position:'top',labels:{{boxWidth:12,usePointStyle:true,font:{{size:11}}}}}}}},
   scales:{{y:{{ticks:{{callback:v=>(v*100).toFixed(0)+'%'}}}},x:{{ticks:{{maxTicksLimit:10,maxRotation:0}}}}}}}}}});
new Chart(document.getElementById('scatter'), {{type:'bubble',
  data:{{datasets:[{sc}]}},
  options:{{responsive:true,maintainAspectRatio:false,
   plugins:{{legend:{{position:'top',labels:{{boxWidth:12,usePointStyle:true,font:{{size:11}}}}}},
    tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+c.parsed.y+'% return, '+c.parsed.x+'% vol'}}}}}},
   scales:{{x:{{title:{{display:true,text:'volatility →'}}}},y:{{title:{{display:true,text:'annual return →'}}}}}}}}}});
</script></body></html>"""


if __name__ == "__main__":
    main()
