# Build prompt — Tab "Signaux BBG" (pre-registered, final signal campaign)

Add ONE tab to the existing Research Lab page. Same engineering rules as before (namespaced
`rlab_*`, cache in `research_lab_data/`, text-only bundles, no look-ahead). This is a
PRE-REGISTERED experiment: the 12 candidates below are FINAL — no grids, no added variants,
no threshold tuning, ever. Context: the public-proxy version of this campaign (Baa−10Y,
Baa−Aaa, 10Y−3M, MOVE, NFCI — 13 candidates) just went 0/13, all losing −0.5% to −2.5% vs
immediate deployment IS and OOS. These 12 use series only Bloomberg has.

## New pulls

| series_id | ticker | fields | notes |
|---|---|---|---|
| HY_OAS | `LF98OAS Index` | PX_LAST | PERCENT units (5.43 = 543bp), daily ~1994-. ffill onto equity calendar, lag 1bd. |
| IG_OAS | `LUACOAS Index` | PX_LAST | PERCENT, ~1989-. Only used inside HY−IG. Lag 1bd. |
| NYAD | `NYAD Index` | PX_LAST | Log whether it is daily net advances or the cumulative A/D line. Also try-and-log `ADVN Index` / `DECLN Index` (separate adv/dec counts, needed for Zweig). Log first dates. |
| NYHI / NYLO | `NWHLNYHI` / `NWHLNYLO Index` | PX_LAST | NYSE 52w highs/lows counts. |
| AAII_BULL / AAII_BEAR | `AAIIBULL` / `AAIIBEAR Index` | PX_LAST | Weekly; survey closes Wed, released Thu → lag 2bd from the release. Log Bloomberg's timestamp convention. |
| MARGDEBT | `MARGDEBT Index` | PX_LAST | Monthly, ~6-week publication lag → a month's value is usable only 30bd after month-end. NYSE→FINRA splice ~2010: use YoY only. |
| S5TH | `S5TH Index` | PX_LAST | TRY-AND-LOG. If it does not resolve, drop candidate 12 and say so — do NOT hunt substitutes. |
| UX1–UX4 | `UX1`–`UX4 Index` | PX_SETTLE, FUT_ACT_DAYS_EXP | UNADJUSTED generics, roll on expiry, adjustment NONE (levels are interpolated; any back-adjustment corrupts them). PX_LAST only as missing-settle flag. From 2004-03-26, dense from ~2006-10. |
| VIX (have), VIX3M | `VIX3M Index` | PX_LAST | VIX3M = diagnostic only, no candidate on it (spot ratio already failed 0/3). |

**Constant-maturity construction (fixed):** for target tenor T days, each date, find the
adjacent generic pair (UXi, UXi+1) with d_i = FUT_ACT_DAYS_EXP_i ≤ T ≤ d_{i+1}; CM_T =
linear interpolation of PX_SETTLE in calendar days. CM30 uses (UX1,UX2); CM90 uses the
straddling pair among UX2–UX4; days with no straddling pair → signal off.

## Engine (identical mechanics to everything prior)

1000/month arrives at the first trading day and WAITS in reserve; when a candidate fires
(all features lagged as specified), the ENTIRE reserve deploys at the next close into
70% SPTR / 30% XNDX; 63-bar time-stop force-deploys; fees 10bp + slippage 5bp per order.
Controls: CONTROL_now (deploy on arrival — the null every candidate must beat) and
CONTROL_dca26. Split: IS ends 2012-12-31, OOS 2013 → today, computed once. Stress: rerun
all at fees ×2. Read-out rule (print it in the bundle): a candidate must beat CONTROL_now
IS to be read OOS; a positive finding must beat it IS AND OOS and survive fees ×2.

## The 12 pre-registered candidates (verbatim — implement exactly)

Credit (window pctl_5y = rolling 1260-bar rank, min_periods 252; z_3y = 756-bar z-score):

1. `hyig_decomp_p90` — pctl_5y(HY_OAS − IG_OAS) > 0.90. Usable 1995-, full window 1999-.
   Note: May-2005 GM/Ford fallen-angel wave and post-2015 BB-drift are known composition
   breaks — flag fires near them.
2. `hy_oas_800` — HY_OAS > 8.00 (absolute 800bp, default-compensation breakeven). Usable
   1994-. Fires ~8–10% of bars (1998, 2000-02, 2008-09, 2011, 2016, 2020).
3. `hy_peak_retreat` — (pctl_5y(HY_OAS) > 0.80) AND (HY_OAS − HY_OAS[t−21] < −0.50):
   top-quintile spreads already ≥50bp off their monthly peak — the post-panic repair phase.

Breadth / sentiment / positioning:

4. `zweig_thrust` — EMA10(ADV/(ADV+DEC)) crosses from <0.40 to >0.615 within ≤10 trading
   days (requires ADV/DEC counts; if only NYAD resolves, drop and log). Lag 1bd.
5. `nl_washout` — NYLO/(NYHI+NYLO) ≥ 0.90 AND NYLO ≥ 100 (absolute floor kills quiet-day
   noise). Lag 1bd.
6. `aaii_spread_panic` — (AAII_BULL − AAII_BEAR) ≤ −20pt at the latest Thursday release.
   Lag 2bd from release.
7. `aaii_bear_extreme` — AAII_BEAR ≥ 50. Lag 2bd.
8. `margin_deleveraging` — margin-debt YoY growth ≤ −10%, using the latest month published
   ≥30bd after its month-end (publication-lagged, no peeking).
9. `pct200_washout` — S5TH < 15 (if the ticker resolves; else dropped, logged).

Real VIX futures curve (from 2004-03-26; flag that IS is short — effectively 2007-2012):

10. `ux_cm30_spot_bwd` — CM30 / VIX_close < 1.00 (futures curve below spot: stress big
    enough to erase the entire contango risk premium). Zero fitted parameters. Lag 1bd.
11. `ux_ryield_deep_bwd` — RY = ln(UX1_settle/UX2_settle) × 365/(d2−d1) > +0.25
    (deep positive annualized roll yield = deep backwardation). Lag 1bd.
12. `ux_cm_slope_3090_bwd` — CM30 / CM90 > 1.00 (mid-curve inversion). Days with CM90
    NaN → signal off. Lag 1bd.

## Bundle

One bundle `bbg_signals`: `tables.results` = [candidate, n_fires_is, n_fires_oos,
final_is, rel_is_vs_now_%, final_oos, rel_oos_vs_now_%, rel_is_feex2_%, rel_oos_feex2_%],
plus `tables.controls` (now, dca26) and `tables.dropped` (unresolved series with reason).
`headline` = "X/12 beat immediate deployment IS; Y read OOS; Z survived". No `series`.
Standard 25k budget, checksum.
