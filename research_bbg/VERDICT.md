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
