# Bloomberg data export request — DCA research program, phase 2

> Paste this whole document into the Bloomberg terminal AI assistant.
> Companion piece: docs/INVESTIGATION_VERDICT.md (why these families were chosen).

---

## Your role

You are assisting with a personal quantitative research project. I need to export historical
data from my Bloomberg terminal to CSV files for offline backtesting. For every series listed
below, give me the **exact, ready-to-paste method**: Excel BDH formulas (preferred) or Desktop
API `IntradayBarRequest` parameters for the intraday blocks. Resolve every ticker or field
mnemonic marked **(guess)** or **(likely)** to the exact one on my terminal (use FLDS/DES/SECF
as needed), and tell me when a series needs an entitlement I may not have (flag it, propose the
closest entitled substitute).

## Global export rules

1. One CSV per series. OHLCV series: columns `date,open,high,low,close,volume`. Single-value
   series: `date,value`. ISO dates, daily frequency unless stated, **maximum available history**.
2. Non-trading days omitted (no fill), currency = the security's native currency.
3. Pin the adjustment settings explicitly in each BDH so my personal DPDF defaults cannot
   silently change an export: splits ON, **dividend adjustment OFF for price series** (total
   return comes from the dedicated TR fields, never from adjusted prices).
4. For total-return series use `TOT_RETURN_INDEX_GROSS_DVDS` (gross). Where a net-TR sibling
   exists, list it too — I want both bounds.
5. For each block below, produce: (a) the resolved ticker list, (b) one sample BDH formula I can
   copy for the whole block, (c) any entitlement warnings.

Priority: **P0 first** (blocks A, B, C, F, H). P1 next. P2 only if trivial.

---

## BLOCK A — Core re-validation (P0)

Purpose: re-run an existing 33-year backtest harness on Bloomberg data to close the
data-quality question permanently.

| Series | Ticker | Fields | History |
|---|---|---|---|
| SPY ETF OHLCV | `SPY US Equity` | PX_OPEN, PX_HIGH, PX_LOW, PX_LAST, PX_VOLUME | 1993– |
| SPY total return | `SPY US Equity` | TOT_RETURN_INDEX_GROSS_DVDS | 1993– |
| QQQ ETF OHLCV + TR | `QQQ US Equity` | same two exports | 1999– (check continuity across the QQQQ→QQQ 2011 rename) |
| S&P 500 price index | `SPX Index` | PX_OPEN, PX_HIGH, PX_LOW, PX_LAST | 1980– (PX_OPEN unreliable before ~1982 — confirm) |
| S&P 500 gross TR | `SPXT Index` (or `SPTR Index` — tell me which resolves) | PX_LAST | 1988– |
| S&P 500 net TR | `SPTR500N Index` (likely) | PX_LAST | max |
| Nasdaq-100 price | `NDX Index` | PX_OPEN, PX_HIGH, PX_LOW, PX_LAST | 1985– |
| Nasdaq-100 gross TR | `XNDX Index` | PX_LAST | 1999– |
| Nasdaq-100 net TR | `XNDXNNR Index` (likely) | PX_LAST | max |

## BLOCK B — Options & variance risk premium (P0 — the flagship)

Purpose: backtest cash-secured put selling (monthly ATM and 5–10% OTM) against immediate
deployment. Full option-chain history is not BDH-exportable, so the plan is: (1) the official
Cboe strategy benchmarks as ground truth, (2) Bloomberg's fitted implied-vol surface fields as
the pricing input for synthetic replication, (3) SKEW-calibrated extension further back.

Cboe strategy benchmark indices (all `PX_LAST`, daily, full history — most are backfilled to
1986–88, note the live-calculation start date for each in your answer):

`PUT Index`, `BXM Index`, `BXY Index`, `BXMD Index` (likely), `CMBO Index` (likely),
`WPUT Index` (likely), `PPUT Index` (likely), `CLL Index` (likely).

Vol / surface inputs:

| Series | Ticker | Fields | History |
|---|---|---|---|
| VIX OHLC | `VIX Index` | PX_OPEN, PX_HIGH, PX_LOW, PX_LAST | 1990– |
| SKEW | `SKEW Index` | PX_LAST | 1990– |
| VIX9D | `VIX9D Index` | PX_LAST | max (ex-VXST — confirm history is stitched) |
| VVIX | `VVIX Index` | PX_LAST | max |
| SPX 1M ATM fitted IV | `SPX Index` | `30DAY_IMPVOL_100.0%MNY_DF` — confirm exact spelling via FLDS, and give me the 66DAY/3MTH tenor variants | ~2005– (tell me the true start) |
| SPX 1M 95% mny IV | `SPX Index` | `30DAY_IMPVOL_95.0%MNY_DF` | ~2005– |
| SPX 1M 90% mny IV | `SPX Index` | `30DAY_IMPVOL_90.0%MNY_DF` | ~2005– |
| SPX 25-delta put IV | `SPX Index` | resolve: is there a BDH-able delta-based IV field, or is the surface only via VOL_SURF_MID / BVOL? | max |
| SPX trailing div yield | `SPX Index` | EQY_DVD_YLD_12M | 1985– |
| US 3M bill (collateral leg) | `USGG3M Index` | PX_LAST | 1985– |

Also answer: what is the realistic way to pull **individual expired SPX/SPY option** daily
series (price/bid/ask/IV) on this terminal, and how far back do expired contracts remain
queryable? I only need ~20–30 exemplar contracts as spot-checks, not chains.

## BLOCK C — VIX futures term structure (P0/P1)

Purpose: real roll-yield and curve-slope measurement (the spot proxy VIX/VIX3M is already
tested; this is the clean version + the VRP-harvest benchmarks).

| Series | Ticker | Fields | Notes |
|---|---|---|---|
| Generic VIX futures 1–4 | `UX1 Index` … `UX4 Index` | PX_SETTLE, PX_LAST, PX_OPEN, PX_HIGH, PX_LOW, PX_VOLUME, OPEN_INT, FUT_ACT_DAYS_EXP | 2004–. Export BOTH unadjusted and **ratio-adjusted** continuous series (never difference-adjusted — tell me how to set the roll adjustment). State the generic roll convention my terminal uses. |
| Generic VIX futures 5–8 | `UX5`–`UX8 Index` | PX_SETTLE, PX_LAST, PX_VOLUME, OPEN_INT | P2, sparse before ~2008 |
| VIX3M | `VIX3M Index` | PX_LAST | confirm the VXV history is stitched under the new ticker |
| VIX6M | `VIX6M Index` | PX_LAST | ex-VXMT, same check |
| VXN | `VXN Index` | PX_LAST | 2001– |
| S&P VIX ST futures index ER + TR | `SPVXSP Index` / `SPVXSTR Index` (likely) | PX_LAST | pre-2009 is backfill — note it |
| Cboe VIX premium strategies | `VPD Index`, `VPN Index` (likely) | PX_LAST | confirm tickers |
| VIX ETPs (study only) | `VXX US Equity`, `SVXY US Equity`, `XIV US Equity` (dead) | PX_LAST adjusted, TOT_RETURN_INDEX_GROSS_DVDS | note the VXX 2019 note-maturity splice |

## BLOCK D — Credit, rates, macro (P1)

Purpose: (a) whole-pot de-risking gates for fixed-horizon goals (the higher-prior use),
(b) closing the entry-timing hypothesis space (low prior, pre-registered).

| Series | Ticker | Fields | History |
|---|---|---|---|
| US HY OAS | `LF98OAS Index` (likely; else INDEX_OAS_TSY_BP on `LF98TRUU Index`) | PX_LAST | 1994– ; confirm units bp vs % |
| US IG corp OAS | `LUACOAS Index` (likely) | PX_LAST | 1989– |
| 3M / 2Y / 10Y generic yields | `USGG3M`, `USGG2YR`, `USGG10YR Index` | PX_LAST | max each |
| MOVE | `MOVE Index` | PX_LAST | 1988– |
| Moody's Baa & Aaa yields | `MOODCBAA` / `MOODCAAA Index` (likely) | PX_LAST | max (long-history extension) |
| Bloomberg US FCI | `BFCIUS Index` (likely) | PX_LAST | max — note backfill/look-ahead caveat in your answer |
| GS US FCI | `GSUSFCI Index` (likely) | PX_LAST | check entitlement/redistribution |
| 10Y breakeven | `USGGBE10 Index` | PX_LAST | P2 |
| CDX HY & IG 5Y generic | resolve exact on-the-run generic tickers | PX_LAST | P2 — flag if CMA/ICE entitlement is missing |

## BLOCK E — Breadth, sentiment, positioning (P1/P2)

Purpose: closing the hypothesis space; breadth doubles as a gate candidate. Please state each
series' true history start on my terminal — several have shorter Bloomberg carriage than their
source history.

| Series | Ticker | Freq | Notes |
|---|---|---|---|
| S&P 500 % above 200dma | `S5TH Index` | daily | P0 of this block |
| % above 50dma / 20dma | `S5FI` / `S5TW Index` (likely) | daily | |
| NYSE advances / declines | resolve (`ADVN`/`DECLN Index`?) | daily | common-stock-only variant if it exists |
| NYSE new highs / lows | resolve | daily | P2 |
| CBOE equity-only P/C | resolve (`PCUSEQTR Index`?) | daily | 2003– only; note the 2007 + 0DTE-era breaks |
| CBOE total P/C | resolve | daily | 1995– |
| AAII % bull / % bear | `AAIIBULL` / `AAIIBEAR Index` (likely) | weekly | timestamp = Thursday release |
| COT e-mini S&P net non-commercial + OI | resolve via CFTC ticker family | weekly | Tuesday data, Friday release — I need the release-date convention |
| FINRA margin debt | `MARGDEBT Index` (likely) | monthly | NYSE→FINRA splice |
| EPFR equity flows | via FLOW <GO> | weekly | flag if not entitled (expected) |

## BLOCK F — French implementation & the leverage dial (P0)

Purpose: exact tracking, spread and cost measurement of the PEA-eligible wrappers, and the
2x daily-reset UCITS as the one structurally-open lever.

For each fund: OHLCV + `PX_BID`,`PX_ASK` (daily closing), `TOT_RETURN_INDEX_GROSS_DVDS`,
`FUND_NET_ASSET_VAL` (separate CSV), and current `FUND_EXPENSE_RATIO`, `FUND_TOTAL_ASSETS`,
`FUND_INCEPT_DT`, `FUND_BENCHMARK` (snapshot table, one row per fund).

`ESE FP Equity`, `PUST FP Equity` (confirm the current PEA Nasdaq-100 Paris line — PUST vs
PANX, and any ex-Lyxor predecessor ticker whose history must be stitched), `PE500 FP Equity`,
`CW8 FP Equity` (check splits + Amundi restructuring continuity), `CL2 FP Equity` (the 2x MSCI
USA quanto — also resolve its exact benchmark index ticker from FUND_BENCHMARK and tell me if
that leveraged index has backfilled history), `LQQ FP Equity` (confirm inception; hedged or
unhedged vs CL2).

Supporting series: `NDDUUS Index` (MSCI USA net TR) PX_LAST max; `EURUSD Curncy` PX_LAST
(state which closing source — BGN?); `FEDL01 Index` PX_LAST; `EONIA Index` + `ESTRON Index`
PX_LAST (I will splice with the official +8.5bp); `EUR003M Index` P2.

## BLOCK G — Fed model (P1, low prior, pre-registered)

`SPX Index`: `EARN_YLD` (trailing — note it is as-revised, not point-in-time),
`BEST_PE_RATIO` and `BEST_EPS` with `BEST_FPERIOD_OVERRIDE=1BF` (this one IS stored
point-in-time — confirm index-level BEst history entitlement and its true start date).

## BLOCK H — Execution & intraday cost calibration (P0, ~240-day window)

Purpose: replace an assumed 5bp slippage with measured spreads; find the cheapest hour and
venue for the monthly PEA buy. I understand intraday bars are limited to ~240 days (ticks
~140) — confirm the exact limits on my terminal.

1. **Intraday 1-minute bars, eventType TRADE + BID + ASK (3 separate requests each)** for:
   `ESE FP Equity`, `PUST FP Equity`, `SPY US Equity`, front-month e-mini (`ESU5 Index` or
   current — also generic `ES1 Index` daily), `EURUSD Curncy`. Give me the exact
   IntradayBarRequest parameters or the Excel BDH intraday syntax.
2. **iNAV**: resolve the intraday indicative-NAV ticker for ESE FP and PUST FP (from the DES/
   ETF page "INAV Ticker" field) and give me its intraday + daily export method.
3. **Auction data**: which fields on Euronext-listed ETFs carry the opening/closing auction
   price and volume (PX_OFFICIAL_CLOSE? CLOSING_AUCTION_*? are Euronext PX_OPEN/PX_LAST
   themselves auction prints?). Resolve via FLDS and give me what actually populates.
4. **Spread analytics**: does my terminal expose any historical average bid-ask spread field
   or BQL function (time-weighted spread, BTCA analytics) for these tickers with more than
   240 days of history? If yes, give the exact call; this is high value.
5. Daily closing `PX_BID`/`PX_ASK` history for SPY (2000s–) as the tight-spread floor.

---

## Final deliverable I want from you

For each block: (1) the resolved ticker/field list with corrections, (2) one paste-ready BDH
formula template + the per-series variations, (3) entitlement flags, (4) the true history
start dates you can see on this terminal for every series marked "max"/"confirm". Where a
requested series simply does not exist or cannot be exported, say so explicitly and propose
the nearest substitute — do not silently skip it.
