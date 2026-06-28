# Experiment ledger

_26 experiments · shipped: 16  ·  flag: 5  ·  deferred: 4  ·  prototype: 1_

_By proposer: claude: 10  ·  chatgpt: 10  ·  chatgpt+claude: 5  ·  user: 1_

| Date | Idea | Area | By | Decision | Result | Reason |
|---|---|---|---|---|---|---|
| 2026-06-09 | Rank buffer (hold past top_n) | momentum | claude | shipped | same excess return, turnover/costs ~-32% | cheap win |
| 2026-06-09 | Top-k parameter ensemble | portfolio | claude | shipped | Sharpe 0.97->1.03, drawdown -36%->-32% | free stability |
| 2026-06-09 | Vol-adjusted momentum ranking | momentum | claude | flag | cost 3-7%/yr excess OOS | dilutes momentum in small universe |
| 2026-06-09 | Inverse-vol position weights | sizing | claude | flag | cost 3-7%/yr excess OOS | tilts to low-vol names |
| 2026-06-10 | T-bill yield on idle cash (BIL) | cash | claude | shipped | OOS excess slightly up; ~0.5-1%/yr at current rates | free |
| 2026-06-10 | Live paper loop + decision journal | infra | claude | shipped | deployed | foundation |
| 2026-06-11 | Param-level champion/challenger gate | infra | claude | shipped | deployed | promote only if beats incumbent OOS |
| 2026-06-11 | Daily report + monthly refresh (cloud) | infra | claude | shipped | deployed via GitHub Actions | autonomy |
| 2026-06-18 | Mean-reversion sleeve | strategy | chatgpt | shipped | part of challenger | diversifies momentum |
| 2026-06-18 | Volatility targeting (12%) | portfolio | chatgpt | shipped | challenger vol hits 12% target | risk control |
| 2026-06-18 | 3-state regime model | regime | chatgpt | shipped | part of challenger | replaces binary SPY>200DMA |
| 2026-06-18 | Challenger bot (multi-sleeve) | strategy | chatgpt+claude | shipped | OOS 11.6% CAGR, Sharpe 0.98, beta 0.34 | diversifier, 2nd live bot |
| 2026-06-19 | Longer covariance lookback (60/90) | vol-targeting | chatgpt | flag | 20 won: 11.7% vs 10.5-10.7% CAGR OOS | short window adapts faster |
| 2026-06-19 | Market breadth in regime | regime | chatgpt | flag | ~0.4%/yr drag, no DD benefit OOS | no edge |
| 2026-06-19 | Unit tests + CI | infra | chatgpt | shipped | 34 tests incl. no-look-ahead | regression guard |
| 2026-06-19 | Expanded reporting (rolling/exposure/attribution) | reporting | chatgpt | shipped | diagnostics shipped | observability |
| 2026-06-23 | Point-in-time universe framework | data | chatgpt | shipped | framework only | needs delisted prices to complete survivorship fix |
| 2026-06-23 | Weekly mean-reversion cadence | mean-reversion | chatgpt+claude | flag | CAGR 11.7->8.6%, Sharpe 0.99->0.80, turnover 2x | turnover ate the signal |
| 2026-06-24 | Beta-stability reporting | reporting | chatgpt | shipped | down-beta 0.18<static 0.29; per-fold beta unstable 0-1.4 | validates diversifier claim |
| 2026-06-24 | Multi-asset trend sleeve (design B) | multi-asset | chatgpt+claude | prototype | OOS 9.1% CAGR/Sharpe 0.97/-13% maxDD; +8.7% in 2008; 0.48 corr to challenger | first new non-rejected idea; not yet live |
| 2026-06-24 | Operational risk controls (extra) | risk | chatgpt | deferred |  | mostly redundant with existing guards |
| 2026-06-24 | Execution alpha (close/open, stagger, limits) | execution | chatgpt+claude | deferred |  | expected <0.2%/yr; do sensitivity study first |
| 2026-06-24 | Continuous/soft regime curve | regime | chatgpt+claude | deferred |  | judge on turnover/whipsaw not CAGR |
| 2026-06-24 | Larger / point-in-time equity universe | data | claude | deferred |  | biggest honesty upgrade; needs delisted price data |
| 2026-06-27 | Suspect-equity guard (bad-read protection) | risk | claude | shipped | fixed challenger phantom -99% drawdown; blocks glitch-triggered kill switch | a transient read must never liquidate a real book |
| 2026-06-27 | Multi-asset trend bot (3rd live bot) | multi-asset | user | shipped | live on 3rd Alpaca paper account; opening book SPY/EFA/TLT/BIL | crisis-resilient diversifier, promoted from prototype |
