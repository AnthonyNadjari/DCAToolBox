# Build prompt — Bloomberg research lab (Python + Streamlit)

> Paste this into the coding AI that will write the scripts. It has terminal access to
> Bloomberg via the Desktop API (`xbbg` preferred, raw `blpapi` fallback).

---

You are building a small, rigorous quant research lab: a Python data pipeline pulling
Bloomberg data through the Desktop API, plus a Streamlit app to run pre-specified backtests
and export compact result bundles that will be reviewed by an external analyst. Correctness
and reproducibility beat features. Build exactly what is specified — no extra strategies, no
extra parameters.

## 0. Engineering rules

- Python 3.11+, `xbbg` for pulls (`blp.bdh`, `blp.bdib`) with raw `blpapi` fallback where
  xbbg can't express something. `pandas`, `numpy`, `scipy`, `plotly`, `streamlit`.
- Every pull is cached to `data/csv/<series_id>.csv` (`date,open,high,low,close,volume` for
  OHLCV, `date,value` otherwise, ISO dates) plus `data/manifest.json`: one entry per series
  {series_id, ticker, fields, first_date, last_date, rows, last_pull, sha256}. Incremental
  refresh: re-pull only from last_date-5d.
- **No look-ahead anywhere**: any signal used on day t may only use data through day t-1;
  fills happen at day t's open when OHLC exists, else at day t's close, and this convention
  is stated in each result output.
- Default costs: fee 10bp + slippage 5bp per equity order, parameterizable. Options get
  their own cost model (§4).
- Every backtest writes `exports/<test>_<timestamp>/` containing `config.json` (ALL
  parameters + data manifest hashes), `results.json` (all tables, stable schema), and PNGs.
  A global "zip all exports" button produces one file to send to the analyst.
- A `README.md` explaining setup (Bloomberg terminal running + API entitlement), the pull
  order, and the 140-day intraday warning below.

## 1. Data manifest (resolved on the terminal — use verbatim)

```python
DAILY_SERIES = {
  # --- Block A: core (P0) ---
  "SPY":       ("SPY US Equity",  ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST","PX_VOLUME"]),
  "SPY_TR":    ("SPY US Equity",  ["TOT_RETURN_INDEX_GROSS_DVDS"]),          # 1993-01-29
  "QQQ":       ("QQQ US Equity",  ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST","PX_VOLUME"]),
  "QQQ_TR":    ("QQQ US Equity",  ["TOT_RETURN_INDEX_GROSS_DVDS"]),          # 1999-03-10
  "SPX":       ("SPX Index",      ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST"]), # open unreliable pre-1982
  "SPTR":      ("SPTR Index",     ["PX_LAST"]),                              # 1988-01-04 gross TR
  "SPTR500N":  ("SPTR500N Index", ["PX_LAST"]),                              # 1989-12-29 net TR
  "NDX":       ("NDX Index",      ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST"]), # 1985-02-04
  "XNDX":      ("XNDX Index",     ["PX_LAST"]),                              # 1999-03-04 gross TR
  "XNDXNNRL":  ("XNDXNNRL Index", ["PX_LAST"]),                              # net TR; verify via DES first
  # --- Block B: options / VRP (P0) ---
  "PUT":  ("PUT Index",  ["PX_LAST"]),   # 1986-06-30
  "BXM":  ("BXM Index",  ["PX_LAST"]),   # 1986-06-30
  "BXY":  ("BXY Index",  ["PX_LAST"]),   # 1988-06-01
  "BXMD": ("BXMD Index", ["PX_LAST"]),   # 1986-06-20
  "CMBO": ("CMBO Index", ["PX_LAST"]),   # 1986-06-30
  "WPUT": ("WPUT Index", ["PX_LAST"]),   # 2006-01-31
  "PPUT": ("PPUT Index", ["PX_LAST"]),   # 1986-06-30
  "CLL":  ("CLL Index",  ["PX_LAST"]),   # 1986-06-23
  "VIX":  ("VIX Index",  ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST"]),  # PX_LAST 1990-; OHL only 2000-
  "SKEW": ("SKEW Index", ["PX_LAST"]),   # 2011-01-03 ONLY (BBG has no 1990 backfill)
  "VIX9D":("VIX9D Index",["PX_LAST"]),   # 2011-01-03
  "VVIX": ("VVIX Index", ["PX_LAST"]),   # 2006-03-06
  "SPX_IV_ATM_30D": ("SPX Index", ["30DAY_IMPVOL_100.0%MNY_DF"]),   # probe start 2002-01-01
  "SPX_IV_95_30D":  ("SPX Index", ["30DAY_IMPVOL_95.0%MNY_DF"]),
  "SPX_IV_90_30D":  ("SPX Index", ["30DAY_IMPVOL_90.0%MNY_DF"]),
  "SPX_IV_ATM_3M":  ("SPX Index", ["3MTH_IMPVOL_100.0%MNY_DF"]),    # verify mnemonic via FLDS
  "SPX_IV_25DP_30D":("SPX Index", ["30DAY_IMPVOL_25.0%DELTA_PUT_DF"]),  # verify via FLDS
  "SPX_DVD_YLD": ("SPX Index", ["EQY_DVD_YLD_12M"]),                # probe start 1985
  "SPX_EARN_YLD":("SPX Index", ["EARN_YLD"]),                       # as-revised, NOT point-in-time
  "USGG3M": ("USGG3M Index", ["PX_LAST"]),                          # percent; probe start 1981
  # BEst (point-in-time), from 2006-07-20; monthly gap 2006-2016 to probe:
  "SPX_BEST_EPS": ("SPX Index", ["BEST_EPS"]),      # override BEST_FPERIOD_OVERRIDE="1BF"
  "SPX_BEST_PE":  ("SPX Index", ["BEST_PE_RATIO"]), # override BEST_FPERIOD_OVERRIDE="1BF"
  # --- Block C: VIX futures (P0/P1) ---
  # UX1..UX4 P0, UX5..UX8 P2. Pull UNADJUSTED generics; constant-maturity is built in code.
  **{f"UX{i}": (f"UX{i} Index",
      ["PX_SETTLE","PX_LAST","PX_OPEN","PX_HIGH","PX_LOW","PX_VOLUME","OPEN_INT","FUT_ACT_DAYS_EXP"])
      for i in range(1, 9)},                                        # start 2004-03-26; PX_SETTLE authoritative
  "VIX3M": ("VIX3M Index", ["PX_LAST"]),   # 2002-01-02 (VXV stitched)
  "VIX6M": ("VIX6M Index", ["PX_LAST"]),   # 2008-01-02
  "VXN":   ("VXN Index",   ["PX_LAST"]),   # 2001-02-02
  "SPVXSP":("SPVXSP Index",["PX_LAST"]),   # 2005-12-20 ER
  "SPVXSTR":("SPVXSTR Index",["PX_LAST"]), # 2005-12-20 TR
  "VPD": ("VPD Index", ["PX_LAST"]),       # 2004-06-15
  "VPN": ("VPN Index", ["PX_LAST"]),       # 2004-06-15
  # --- Block D: credit / macro (P1) ---
  "HY_OAS": ("LF98OAS Index", ["PX_LAST"]),   # PERCENT -> x100 = bp; probe start 1992-1994
  "IG_OAS": ("LUACOAS Index", ["PX_LAST"]),   # PERCENT; <=1990
  "USGG2YR": ("USGG2YR Index", ["PX_LAST"]),
  "USGG10YR":("USGG10YR Index",["PX_LAST"]),
  "MOVE": ("MOVE Index", ["PX_LAST"]),        # probe 1988-1989
  "BAA":  ("MOODCBAA Index", ["PX_LAST"]),    # probe 1919
  "AAA":  ("MOODCAAA Index", ["PX_LAST"]),
  "BFCIUS": ("BFCIUS Index", ["PX_LAST"]),    # probe 1994-1999 (GSUSFCI NOT entitled)
  "USGGBE10": ("USGGBE10 Index", ["PX_LAST"]),# probe 2003
  # --- Block E: breadth / sentiment (P1) ---
  "NYAD": ("NYAD Index", ["PX_LAST"]),        # probe 1960
  "NYHI": ("NWHLNYHI Index", ["PX_LAST"]),
  "NYLO": ("NWHLNYLO Index", ["PX_LAST"]),
  "AAII_BULL": ("AAIIBULL Index", ["PX_LAST"]),  # weekly, Thursday release -> lag to Thursday close
  "AAII_BEAR": ("AAIIBEAR Index", ["PX_LAST"]),
  "MARGDEBT": ("MARGDEBT Index", ["PX_LAST"]),   # monthly, ~6-week lag -> lag accordingly
  # --- Block F: French wrappers + leverage (P0) ---
  # For each: OHLCV + PX_BID/PX_ASK + PX_OFFICIAL_CLOSE daily; TR; NAV.
  **{name: (tkr, ["PX_OPEN","PX_HIGH","PX_LOW","PX_LAST","PX_VOLUME","PX_BID","PX_ASK","PX_OFFICIAL_CLOSE"])
     for name, tkr in [("ESE","ESE FP Equity"),("PUST","PUST FP Equity"),("PE500","PE500 FP Equity"),
                       ("CW8","CW8 FP Equity"),("CL2","CL2 FP Equity"),("LQQ","LQQ FP Equity")]},
  **{f"{name}_TR": (tkr, ["TOT_RETURN_INDEX_GROSS_DVDS"])
     for name, tkr in [("ESE","ESE FP Equity"),("PUST","PUST FP Equity"),("PE500","PE500 FP Equity"),
                       ("CW8","CW8 FP Equity"),("CL2","CL2 FP Equity"),("LQQ","LQQ FP Equity")]},
  **{f"{name}_NAV": (tkr, ["FUND_NET_ASSET_VAL"])
     for name, tkr in [("ESE","ESE FP Equity"),("PUST","PUST FP Equity"),
                       ("CL2","CL2 FP Equity"),("LQQ","LQQ FP Equity")]},
  "M00UUS02": ("M00UUS02 Index", ["PX_LAST"]),  # CL2 benchmark (2x MSCI USA daily net) — probe history
  "NDDUUS": ("NDDUUS Index", ["PX_LAST"]),      # probe 1994
  "EURUSD": ("EURUSD Curncy", ["PX_LAST"]),     # PRICING_SOURCE=BGN explicitly
  "FEDL01": ("FEDL01 Index", ["PX_LAST"]),      # 1954-07-01
  "EONIA":  ("EONIA Index",  ["PX_LAST"]),      # 1999-01-04 -> 2022-01-03
  "ESTRON": ("ESTRON Index", ["PX_LAST"]),      # 2019-10-01; splice EONIA = ESTR + 8.5bp
  "SPY_BIDASK": ("SPY US Equity", ["PX_BID","PX_ASK"]),  # from 2000-01-31, pull in yearly chunks
}

# Try-and-log (unresolved on terminal — attempt BDH, log failures, do not crash):
CANDIDATES = {
  "S5TH":  [("S5TH Index",  ["PX_LAST"])],
  "S5FI":  [("S5FI Index",  ["PX_LAST"])],
  "PC_EQUITY": [("CPCE Index", ["PX_LAST"]), ("PCCE Index", ["PX_LAST"])],
  "PC_TOTAL":  [("PCRATIO Index", ["PX_LAST"]), ("CPCETOT Index", ["PX_LAST"])],
  "COT_ES": [("CFNMESSP Index", ["PX_LAST"])],
  "VXX": [("VXX US Equity", ["PX_LAST","TOT_RETURN_INDEX_GROSS_DVDS"])],   # 2019 ETN splice caveat
  "SVXY": [("SVXY US Equity", ["PX_LAST","TOT_RETURN_INDEX_GROSS_DVDS"])], # Feb-2018 -1x -> -0.5x break
}

INTRADAY = {  # 1-min bars, eventTypes TRADE + BID + ASK; API keeps only ~140 days!
  "ESE_IB":  "ESE FP Equity", "PUST_IB": "PUST FP Equity", "SPY_IB": "SPY US Equity",
  "ES_IB":   "<front ES contract, resolve at runtime>", "EURUSD_IB": "EURUSD Curncy",
  "IESE_IB": "IESE Index", "PUSTIV_IB": "PUSTIV Index",   # official iNAVs of ESE / PUST
}
```

**Critical**: the intraday window slides (≈140 days retained). The pipeline must pull all
INTRADAY series on FIRST run, append-only, and nag on app start if the newest stored bar is
older than 7 days. This archive becomes irreplaceable.

## 2. Streamlit app — pages

**Page 0 — Data Manager.** Pull buttons per block, incremental refresh, manifest health
table (series, start, end, rows, staleness). Hard validation panel (must all pass green):
SPY TR calendar-year total returns within 0.2pt of {2008: −36.8%, 2013: +32.3%, 2020: +18.4%,
2022: −18.2%}; VIX PX_LAST 2008-11-20 = 80.86 and 2020-03-16 = 82.69; HY_OAS unit sanity
(values in %, ~2–20 range); PUT and SPTR both present back to 1988.

**Page 1 — Benchmarks.** Growth of 1 (log scale), max drawdown, and rolling 5-year relative
return vs SPTR for: PUT, BXM, BXY, BXMD, CMBO, WPUT, PPUT, CLL. Table: full-period CAGR, vol,
Sharpe, MDD, worst 5y vs SPTR. Split every stat pre/post the index's live date (backfill vs
live): PUT live 2007, BXMD live 2015, etc. — hardcode a LIVE_DATES dict I can edit.

**Page 2 — DCA Lab.** Monthly budget B (default 1000) deployed immediately at each month's
first available close into a weighted mix of any TR series (weights UI; default 70% SPTR /
30% XNDX). Controls: 100% SPTR, and day-26 deployment variant. Fees applied per order.
Outputs: final wealth, money-weighted IRR (XIRR), MDD of the accumulating portfolio, and
per-calendar-5y-block relative performance vs the 100% SPTR control. This must reproduce a
known result: 70/30 beats 100% SPX in roughly 5 of 6 blocks 2000–2026 — if not, suspect the
engine, not the conclusion.

**Page 3 — Cash-secured puts (the flagship).** Two engines:
(a) *Index-based*: portfolios mixing PUT/BXMD sleeves with SPTR (e.g. 30% PUT + 70% SPTR) run
through the Page-2 DCA engine, vs the 70/30 control.
(b) *Synthetic CSP engine*: monthly cycle on 3rd-Friday grid; sell one 30-day put at strike
K = S×m for m ∈ {1.00, 0.95, 0.90}; premium via Black-Scholes using the matching IV series
(ATM/95/90 fitted surface, from ~2005), spot = SPX close, r = USGG3M, q = SPX_DVD_YLD; the
cash collateral earns USGG3M; assignment if S_expiry < K (settle at intrinsic); costs: sell
premium at (1 − h) with haircut h default 5% + $1 per contract equivalent, parameterizable;
optional French CTO tax toggle: 30% flat on each positive net option P&L (no loss carry).
**Replication gate (must pass before ANY variant is interpreted)**: the m=1.00 synthetic run
2005–present must track the official PUT index within 1%/yr annualized tracking difference;
show the tracking chart and the annualized diff prominently.
Then and only then: OTM variants vs the immediate-deployment null (Page-2 engine as the
benchmark), with and without tax toggle, full period and per-5y-block.

**Page 4 — VIX curve (measurement only, no strategy).** Constant-maturity 30-day slope built
from UX1/UX2 settles + FUT_ACT_DAYS_EXP (weight by days-to-expiry — do NOT use Bloomberg
roll-adjusted series). Charts: slope vs VIX level, roll-yield distribution, SPVXSP cumulative
drag vs VIX spot. Table: contango frequency, mean roll yield by curve-state quintile.

**Page 5 — Fixed-horizon gates.** Rolling windows of T ∈ {12, 24, 36, 60} months, monthly
DCA into SPTR; strategies: always-in; glide (contribution equity share = months_left/T);
200dma gate on SPX (monthly check, whole pot to cash at USGG3M when below, back in when
above); HY-OAS gate (whole pot to cash when OAS z-score over trailing 3y > 1.5, pre-register
this single threshold — no threshold UI). Output per T: median / 5th percentile / worst /
%-below-contributed table, and the same table restricted to windows ending in drawdown years.

**Page 6 — Execution lab (French wrappers).** From the intraday archive: half-spread
(ask−bid)/2/mid by hour-of-day for ESE and PUST, vs SPY during the 15:30–17:30 Paris overlap;
premium/discount = ETF mid vs iNAV (IESE/PUSTIV) by hour; auction vs continuous: compare
PX_OFFICIAL_CLOSE fills vs 11:00 / 15:35 mid fills over the archive. Deliverable: a one-line
answer — "the cheapest time to place the monthly PEA order is ___, saving ___ bp vs ___".
Also: CL2/LQQ tracking analysis — daily fund NAV return vs 2× benchmark daily return
(M00UUS02 for CL2, XNDXNNRL for LQQ) and vs 2× NDDUUS + FX, to establish empirically whether
the exposure is hedged/quanto/unhedged, and measure the total cost drag per year.

## 3. Result bundle schema (stable — the analyst parses this)

`results.json`: {"test": str, "run_at": iso, "params": {...}, "data_ranges": {series: [start, end]},
"tables": {name: [{col: val}]}, "headline": str}. Everything the page shows must be in
`tables`; `headline` is the one-sentence takeaway. No screenshots-only results.

## 4. What NOT to build

No parameter optimizers, no grid searches, no ML, no signal mining pages, no strategies
beyond those specified. The point of this lab is few tests, done exactly, exportable. If a
page's data is missing, the page says which series and which pull button fixes it.
