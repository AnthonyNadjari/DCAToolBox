# Build prompt — add ONE research page to an existing Streamlit app

You are adding a single new page to an EXISTING multi-page Streamlit project. Integration
rules come first, they are non-negotiable:

- **One new page file** (e.g. `pages/90_Research_Lab.py`) + **one new package**
  `research_lab/` (data.py, engines.py, plots.py). Touch NOTHING else: no edits to existing
  pages, no changes to global config/theme/session_state keys (namespace everything
  `rlab_*`), no new top-level dependencies beyond `xbbg` (and `blpapi`) if not already
  present — the rest must use what the project already has (pandas/numpy/plotly assumed).
- All data cached under `research_lab_data/` (CSV + `manifest.json`), gitignored. All
  outputs under `research_lab_exports/`. The page must run even with zero data pulled:
  every section states which series is missing and which button pulls it.
- Bloomberg pulls via `xbbg` `blp.bdh` / `blp.bdib`. Incremental refresh (re-pull from
  last stored date − 5 days). One retry then a clear error — never crash the app.
- **No look-ahead in any backtest**: signals on day t use data through t−1. State fill
  conventions in every output. Default costs: 10bp fee + 5bp slippage per equity order.
- Build EXACTLY what is below. No optimizers, no grid searches, no extra strategies, no
  extra parameters. Few tests, done exactly, exportable.

The page is `st.tabs` with 5 tabs.

## Data manifest (tickers/fields already resolved on the terminal — use verbatim)

```python
SERIES = {
  # Core total-return + supports
  "SPTR":     ("SPTR Index",     ["PX_LAST"]),                       # S&P 500 gross TR, 1988-01-04
  "XNDX":     ("XNDX Index",     ["PX_LAST"]),                       # Nasdaq-100 gross TR, 1999-03-04
  "SPX":      ("SPX Index",      ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST"]),
  "SPY_TR":   ("SPY US Equity",  ["TOT_RETURN_INDEX_GROSS_DVDS"]),   # validation only, 1993-01-29
  "USGG3M":   ("USGG3M Index",   ["PX_LAST"]),                       # percent
  "VIX":      ("VIX Index",      ["PX_LAST"]),                       # 1990-
  "SPX_DVD":  ("SPX Index",      ["EQY_DVD_YLD_12M"]),
  # Cboe option-strategy benchmarks (PX_LAST each)
  "PUT": ("PUT Index",["PX_LAST"]), "BXM": ("BXM Index",["PX_LAST"]),
  "BXY": ("BXY Index",["PX_LAST"]), "BXMD": ("BXMD Index",["PX_LAST"]),
  "CMBO": ("CMBO Index",["PX_LAST"]), "WPUT": ("WPUT Index",["PX_LAST"]),  # WPUT starts 2006-01-31
  # SPX fitted IV surface (probe start 2002-01-01; realistically ~2005)
  "IV_ATM": ("SPX Index", ["30DAY_IMPVOL_100.0%MNY_DF"]),
  "IV_95":  ("SPX Index", ["30DAY_IMPVOL_95.0%MNY_DF"]),
  "IV_90":  ("SPX Index", ["30DAY_IMPVOL_90.0%MNY_DF"]),
  # French wrappers (daily)
  **{k: (t, ["PX_LAST","PX_BID","PX_ASK","PX_OFFICIAL_CLOSE"])
     for k, t in [("ESE","ESE FP Equity"),("PUST","PUST FP Equity"),
                  ("CL2","CL2 FP Equity"),("LQQ","LQQ FP Equity")]},
  **{f"{k}_NAV": (t, ["FUND_NET_ASSET_VAL"])
     for k, t in [("ESE","ESE FP Equity"),("PUST","PUST FP Equity"),
                  ("CL2","CL2 FP Equity"),("LQQ","LQQ FP Equity")]},
  "M00UUS02": ("M00UUS02 Index", ["PX_LAST"]),   # CL2 benchmark (2x MSCI USA daily net)
  "XNDXNNRL": ("XNDXNNRL Index", ["PX_LAST"]),   # LQQ benchmark; verify via DES
  "NDDUUS":   ("NDDUUS Index",   ["PX_LAST"]),
  "EURUSD":   ("EURUSD Curncy",  ["PX_LAST"]),   # source BGN
}

INTRADAY = {  # 1-min bars, eventTypes TRADE + BID + ASK. API retains only ~140 days —
              # pull on first run, append-only archive, warn if newest bar > 7 days old.
  "ESE_IB": "ESE FP Equity", "PUST_IB": "PUST FP Equity", "SPY_IB": "SPY US Equity",
  "IESE_IB": "IESE Index", "PUSTIV_IB": "PUSTIV Index",   # official iNAVs of ESE / PUST
}
```

## Tab 1 — Données

Pull buttons (grouped: core / benchmarks / IV / wrappers / intraday), manifest health table
(series, start, end, rows, staleness). Validation panel, all must be green: SPY_TR
calendar-year returns within 0.2pt of {2008: −36.8%, 2013: +32.3%, 2020: +18.4%,
2022: −18.2%}; VIX 2008-11-20 = 80.86 and 2020-03-16 = 82.69; PUT and SPTR present back to
1988. Red banner if the intraday archive is stale (>7 days).

## Tab 2 — Benchmarks Cboe

Growth of 1 (log), max drawdown, rolling 5y relative return vs SPTR for PUT/BXM/BXY/BXMD/
CMBO/WPUT. Stats table (CAGR, vol, Sharpe, MDD, worst 5y vs SPTR) split pre/post each
index's LIVE date (backfill vs live) — hardcode `LIVE_DATES = {"PUT": "2007-06-01",
"BXM": "2002-04-01", "BXY": "2004-01-01", "BXMD": "2015-10-01", "CMBO": "2015-10-01",
"WPUT": "2015-01-01"}` as an editable dict.

## Tab 3 — DCA (the control engine)

Monthly budget B (default 1000) deployed immediately at each month's first close into a
weighted mix of TR series (default 70% SPTR / 30% XNDX; weights editable). Controls: 100%
SPTR and a day-26 variant. Outputs: final wealth, XIRR, portfolio MDD, per-5y-block relative
vs 100% SPTR. Sanity anchor: 70/30 must beat 100% SPTR in roughly 5 of 6 blocks 2000–2026 —
if not, the engine is wrong, fix it before anything else.

## Tab 4 — Puts cash-secured (the flagship test)

(a) Index-based: X% PUT + (100−X)% SPTR sleeves through the Tab-3 engine vs the 70/30
control (X ∈ {20, 30, 50}, fixed list).
(b) Synthetic engine: 3rd-Friday monthly cycle; sell one 30-day put at K = S×m,
m ∈ {1.00, 0.95, 0.90}; premium = Black-Scholes put with the matching IV series (IV_ATM/
IV_95/IV_90), S = SPX close, r = USGG3M, q = SPX_DVD; collateral earns USGG3M; assignment at
intrinsic if S_expiry < K; premium haircut h = 5% default (parameter); optional toggle
"fiscalité CTO 30%" applying 30% flat tax on each positive monthly net option P&L.
**REPLICATION GATE, displayed first**: the m = 1.00 run 2005–present must track the official
PUT index within 1%/yr annualized difference (chart + big green/red metric). While red, the
variant results below render greyed-out with a warning. When green: OTM variants vs the
immediate-deployment DCA null, with/without tax, full period + per-5y-block.

## Tab 5 — Exécution (wrappers français)

From the intraday archive: ESE/PUST half-spread (ask−bid)/2/mid by hour-of-day (Paris) vs
SPY over the 15:30–17:30 overlap; ETF mid vs iNAV premium by hour; PX_OFFICIAL_CLOSE vs
11:00 and 15:35 mid fills. Headline metric: "meilleure heure pour l'ordre mensuel: __,
économie __ bp vs __". Plus CL2/LQQ tracking: daily NAV return vs 2× benchmark (M00UUS02 /
XNDXNNRL) and vs 2× NDDUUS + EURUSD — regression table (beta, alpha bp/yr, R²) answering
hedged/quanto/unhedged and the annual cost drag.

## Exports (every tab)

An "Exporter" button per tab writing `research_lab_exports/<tab>_<timestamp>/` with
`config.json` (all params + manifest hashes), `results.json`
({"test", "run_at", "params", "data_ranges", "tables": {name: [rows]}, "headline"}) and the
PNGs. One global "tout zipper" button. Everything shown must be in `tables` — the bundle is
parsed by an external analyst, no screenshot-only results.
