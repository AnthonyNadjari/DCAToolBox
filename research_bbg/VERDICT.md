# Direct-Bloomberg re-run: full verdict (2026-08-23)

The signal program was re-run from scratch with a live Bloomberg terminal
connection (blpapi/xbbg, port 8194), on the instrument the investor actually
buys: **ESE FP** (BNP Paribas Easy S&P 500 UCITS, EUR, Euronext), at the real
cost of **0.50%/trade** and nothing else.

## What was new vs the 2026-07 campaigns

- **Direct API pulls** of 43 daily series (1975→2026 where available) — no
  more manual exports: instrument bid/ask/NAV, real VIX futures generics
  (UX1-3), CDX HY, MOVE, SKEW, VVIX, V2X, AAII, put/call, A/D line, NFCI,
  Citi surprise indices (USD & EUR), EURUSD implied vol and risk reversals,
  ES futures basis, Bund spread, commodities.
- **EUR investor frame** — never tested before (all prior work was USD/SPY).
  Asset = real ESE from inception 2013-09-16, backfilled 1989→2013 with
  SPXT/EURUSD minus TER; splice validated (26 bps/yr CAGR gap vs real fund).
  IS = backfill era, OOS = the real fund's lifetime.
- **New signal families**: FX/EUR (EURUSD momentum/level/vol/risk-reversals),
  EU-vs-US fear (V2X−VIX), EU-vs-US macro surprise, and the overnight gap
  (late-US move after the Euronext close, absorbed at the next ESE open).
- **Intraday microstructure** on the real order book (127 days × ~470 bars of
  trade/bid/ask).

## Campaign 1 — 594 pre-registered specs (commit 974a800 before any result)

90 specs from six blind agent families + 504 mechanical single-condition
quantile specs over all 64 features.

- IS-positive: **15/594** (best +0.26% lifetime).
- Positive on both sides: **4/594**, all turn-of-month calendar variants at
  +0.02%…+0.09% *lifetime* (13y OOS) — noise level; killed by neighborhood
  instability (the q95 neighbor flips to −0.27% OOS) and contradicted by the
  day-26 control itself (−0.90% OOS vs immediate).
- Fee sensitivity 0.25%→1.00%: results unchanged (same order count as the
  null — fees cancel).
- Every Bloomberg-exclusive feature (ux_roll, vix_basis, cdx_hy, es_basis,
  fx_rr25, v2x_vix, cesi_*, us_after_eu_close): negative OOS.

**The 2026-07 verdict stands on the real instrument, in EUR, with terminal
data: no timing signal beats deploying each month's cash immediately.**

## Intraday (the data Bloomberg actually adds): execution, not signals

Bloomberg keeps only ~6 months of intraday bars — 6 monthly decisions, so
intraday *signals* are untestable and stay closed. But 60,186 bid/ask bars
answer the execution question with certainty:

| Window (Paris) | Median spread | P90 | Note |
|---|---|---|---|
| 09:30–14:00 | **3.3–3.4 bp** | 4.4 bp | tightest; price ≈ day VWAP |
| 15:30–17:00 (US open) | 4.1–4.3 bp | 5.2–6.4 bp | vol spillover |
| 17:30 closing auction | **11 bp** | **28 bp** | worst; 14% of volume trades here |

Daily close spreads since 2013 confirm the regime: median 8.7 bp, p90 29 bp,
crisis days 2–7% (2015-08, 2013 illiquid era).

**Execution rule (certain, forecast-free): buy late morning Paris time with a
limit at mid; never the closing auction; skip the day if the spread exceeds
25 bp.** Worth ~5–10 bp/order with certainty — small next to the 0.5% fee,
but free.

## Leverage — the one dial that moved wealth (real fund data, 2013–2026)

1000 EUR/month at 0.5% fee, common window 2013-09→2026-08:

| Flow | Final wealth | Multiple of contributions | Max fund DD |
|---|---|---|---|
| 100% ESE (1×) | 437k | 2.8× | −34% |
| 75/25 ESE/CL2 | 554k | 3.5× | — |
| 50/50 ESE/CL2 | 670k | 4.3× | — |
| 100% CL2 (2× USA) | 904k | 5.8× | −60% |
| 100% LQQ (2× NDX) | 1,528k | 9.8× | −61% |

CL2's realized beta vs ESE: 2.02 — the daily-reset mechanics delivered clean
2× over this window. Honesty requirements: this window is one uninterrupted
bull market; a 2000-2009 decade inflicts the volatility drag with none of the
drift, and −60% is a *fund* drawdown the investor must hold through. This is
a pre-registered RISK choice (Kelly headroom: full investment ≈ 0.3–0.45
fractional Kelly), not alpha.

## Standing production policy (unchanged by ~600 further backtests)

Buy the day the cash arrives. Everything. Late morning, limit at mid, skip
if spread > 25 bp. The only decisions that moved the outcome are structural:
the fee (0.5% is high — halving it beats every signal ever tested here),
the leverage dose, and never selling.

---

# Addendum (2026-08-23 evening): the online-deep-dive + BASK campaign

Six parallel deep-research agents swept the academic and practitioner
literature (60+ sources: JF/JFE/RFS/JFQA, AQR, Elm, Quantpedia, NY Fed,
QuantSeeker replications); BASK supplied terminal tickers for every
Bloomberg-native family it could name (CFTC IMM0ENCN, NAAIM, JCJ/COR1M
implied correlation, SPY short interest, FUND_FLOW incl. leveraged pairs,
BEst revisions, FOMC calendar workflow). The FOMC statement calendar
1994-2026 was compiled from federalreserve.gov (263 scheduled meetings).

## Campaign 2 — 47 pre-registered literature/BASK delay rules (commit before results)

Pre-FOMC drift (Lucca-Moench incl. VIX-gated & close-fill), announcement-eve
NFP/CPI (Savor-Wilson), FOMC even weeks (Cieslak et al.), turn-of-month T-4/
T-2 (Etula dash-for-cash), OpEx entry/avoidance, Connors RSI(2) with 5/10-day
caps, Bansal-Stivers VIX>P80, first-day backwardation, bear-killer vol-crush,
CFTC contrarian, NAAIM capitulation, short-interest, flow capitulation,
revision momentum, Fed model, implied-correlation spikes, and five combos.

Result: 2/47 IS-positive; 1/47 both sides — lit_tom_window at +0.05%/+0.02%
LIFETIME (the same turn-of-month noise cluster campaign 1 already killed).
The overnight/MOC execution anomaly does not transfer either: ESE's Euronext
open already sits after the US overnight session (open-fill null = close-fill
null to within 3bp lifetime).

## Campaign 2b — 11 pre-registered specs on the last untested grade-A candidates

VRP (Bollerslev-Tauchen-Zhou), MOVE-VIX divergence (IRFA 2026), Davies
leveraged-ETF speculation sentiment. Result: the VRP and MOVE-VIX variants
are IS-positive (+0.04..+0.12%) and ALL flip negative OOS on the real fund
era. Speculation sentiment negative on both sides. 0/11.

## Session tally and the unchanged conclusion

652 pre-registered specs this session (594 + 47 + 11) across every family
the literature, the terminal, and BASK could produce — on the real
instrument, in EUR, at the investor's true 0.5% fee. Survivors: none. The
literature's own meta-finding matched our measurements exactly: the credible
post-publication estimate for the entire day-picking game is ~10-25bp/yr,
and the anomalies carrying it (TOM, pre-FOMC) measurably decayed post-2015.

What Bloomberg access genuinely bought: (1) the certain execution rule
(late morning, limit at mid, never the closing auction, skip if spread
> 25bp — worth ~5-10bp per order); (2) the leverage-dial numbers on real
funds (CL2 5.8x vs ESE 2.8x, maxDD -60% vs -34%); (3) closure at a far
higher evidentiary standard: the timing branch is not merely unexploited,
it is now measured to be empty at ±10bp resolution over 37 years.

## Addendum 2 (2026-08-23 night): MMF cash gauge and machine learning

**Money-market-fund "cash on the sidelines" (trader's suggestion).** ICI
total MMF assets (MMFA Index, weekly, 1990-2026, publication lag modeled):
9 pre-registered specs — cash surges, cash-vs-equity z-scores/percentiles,
cash-rotation-out. 0/9: best +0.03% IS flips to -0.68% OOS. Mechanism: MMF
cash surges DURING selloffs, but the deployment reserve pays drift while
waiting for the surge to register; by the time sidelined cash peaks, the
price has recovered past the arrival-day level.

**Machine learning (pre-registered walk-forward, commit before results).**
Ridge, gradient boosting and logistic classification on the full 90+
feature library, 21-day forward target, expanding walk-forward with 21-bar
purge, yearly refits, fixed prediction-to-deployment mapping. Out-of-sample
R²: ridge -2.23, GBM -0.55 — the models predict WORSE than the
unconditional mean. All six deployment variants negative in both eras
(backfill -0.4..-1.4%, real fund -0.2..-0.7%). The conception document's
a-priori rejection of supervised ML at this data scale is now an empirical
result on this exact dataset.

**Final session tally: 667 pre-registered rule variants + 6 ML rules,
across price, calendar, FOMC/macro events, volatility complex incl. real
futures curve, credit, FX/EUR, sentiment surveys, positioning, short
interest, fund flows, earnings revisions, valuation, implied correlation,
money-market cash, and walk-forward ML — zero beat immediate deployment
out of sample.** Combined with the July program: ~7,300 tested rules, zero
survivors. The purchase-timing question for this instrument is answered.

---

# Addendum 3 (2026-08-23, late): Campaign 3 — the hedge-fund reframe (allocation + leverage)

Timing being closed, the question was changed to the two levers a fund
would actually pull: WHERE the monthly flow goes (8-asset EUR TR universe:
SPX, NDX, Stoxx 600, MSCI EM, Russell 2000, MSCI Japan, gold, EUR cash,
1999-2026) and HOW MUCH exposure (2x sleeve, synthetic validated vs real
CL2, corr 0.93; internal comparisons drag-neutral).

## 3A Flow allocation — momentum autopsy repeats on the richer universe

rel_mom_top1 looked like the first real survivor (+10.2% IS / +16.7% OOS
vs 100% SPX, all lookback neighbors positive). Matched-mix attribution
killed it: IS it LOSES 13.1% to the fixed mix of its own realized average
weights (the mix made +26.9%; the rotation kept +10.2% of it); OOS it adds
+2.6% over its mix (45% NDX + 30% gold — pure beta). Full period 1999-2026
the rotation trails 100% SPX outright (1.76M vs 2.12M), merely smoother
(-29% vs -40%). Per-asset trend gating: -24% OOS (cash drag). Conclusion
unchanged from July, now at 7 assets: switching subtracts value; the only
thing that "worked" was holding more Nasdaq and gold — a risk choice.

## 3B Leverage dial — state-dependence is conditional beta

Fixed-share frontier (monthly flow % to 2x): wealth rises monotonically
with the share in BOTH eras (IS 779k->819k, OOS 437k->1,019k) while max
portfolio drawdown deepens (-54%->-93% IS incl. 2000-09; -33%->-57% OOS).
Dynamic rules vs the frontier at their own realized average share:
drawdown-scaled +2.8/+3.1% IS but ~0 OOS (it de-levered through the whole
bull era); trend gate -5.0% IS / +2.2% OOS; vol-target 20% -0.3% IS /
+3.1% OOS; vol-target 25% +0.2% / +1.4% (noise, and its neighbor flips
sign). No state-dependent rule beats the fixed frontier on both eras.
**The leverage dial is a constant, chosen once by drawdown tolerance —
there is no rule for it.**

## The hedge-fund answer for this mandate

After ~7,400 rules across timing, allocation and leverage state-dependence:
the entire harvestable edge inventory is structural and certain —
(1) fee/TER/wrapper (largest, guaranteed), (2) the two beta dials (growth
tilt and a fixed leverage share, both pre-registered risk choices priced
off the frontier above), (3) execution (late morning, limit at mid, never
the closing auction, spread guard), (4) never selling. Every conditional
rule tested — on price, macro, positioning, flows, ML, cross-asset
allocation, and leverage state — was either noise or beta in costume.

---

# Addendum 4 (2026-08-23, night): realistic horizons, selling allowed, campaign 4

Reframe at the user's request: judgment over ALL rolling 5y/10y monthly-DCA
windows (384/324 windows, 1989-2026), selling allowed (tax-free inside PEA),
0.5% fee per weight change.

## Sell rules on the 1x sleeve: all dead
Every sell trigger on ESE — 200dma, Faber 10-month, 12-1 momentum, vol
targeting, VIX term-structure inversion, credit decompression, MMF cash
surge, trend+VIX combo — has NEGATIVE median 5y excess vs buy-and-hold and
win rates 21-41%. At 10y the trend variants reach ~52-56% wins with fat
left tails (p5 -15..-33%). Options-based and money-market sell signals are
the worst (-10% to -21% median 10y). Selling the unlevered sleeve is paying
whipsaw for insurance the horizon does not need.

## The one structure that survives every autopsy: TREND-GATED LEVERAGE
2x sleeve above the 200dma, cash below ("Leverage for the Long Run",
Gayed 2016 — the mechanism is vol-drag avoidance on daily-reset leverage,
i.e. monetizing the ONE predictable quantity (variance), which our July
verdict said was unmonetizable only because leverage was excluded):

- Full sample (incl. synthetic 2000-09): 10y windows 94% win, median
  +53.8%, p5 -1.9% vs holding ESE. 5y: 78% / +18.3% / -10.5%.
- Beats the CONSTANT-exposure benchmark at its own 1.71x average
  (head-to-head 68% win, +29.4% median 10y) — first candidate ever to
  pass matched-benchmark attribution.
- Robust: +300bp/yr extra drag still 76%/+34.9%; sma150/250 neighbors all
  positive, no sign flips.
- REAL CL2 2009-2026 (V-shaped-crash era only): trend keeps just +2.5%
  median vs ESE (59% win, 1.7 switches/yr) while plain hold-CL2 made +70%
  median and won 100% of windows. The filter's payoff is concentrated in
  multi-year bears; in V-recovery regimes it costs most of the leverage
  premium.

## The honest menu (5-10y horizon, per rolling-window distributions)

| Policy | 10y median vs ESE | 10y worst-5% | Character |
|---|---|---|---|
| 100% ESE | 0 | 0 | baseline |
| 100% CL2 (2x) | +64% (real era: +70%) | -39% (path DD to -57..-93%) | max wealth, must hold catastrophic DD |
| CL2 + 200dma trend gate | +54% full / +2.5% real era | -2% full / -11% real era | keeps leverage upside when long bears occur; pays whipsaw in V-regimes |

No timing alpha exists; this is risk ARCHITECTURE. The choice between the
three rows is a belief about future crash shape plus drawdown tolerance —
made once, pre-registered, never re-decided mid-drawdown.
