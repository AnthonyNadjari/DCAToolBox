# Adversarial investigation request: "nothing beats immediate DCA" — really?

You are a senior quantitative researcher hired to adversarially audit a research program and either
break its conclusion or confirm it. Be rigorous, quantitative and specific. Do not be polite; be right.

## 1. The objective

A French retail investor receives a fixed budget every month (resets on the 26th; unspent cash
carries over). He can place orders any day, any amount, any frequency, in real time. Universe:
a small set of liquid index ETFs (S&P 500, Nasdaq-100; PEA tax wrapper in France; no leverage,
no shorting; selling allowed but taxed outside the wrapper). Goal: **maximize final wealth versus
the benchmark "invest the whole budget on day 26 into the S&P 500"** — i.e., beat plain DCA using
data, timing, allocation, or any systematic rule.

## 2. The infrastructure (what the results were produced with)

- Python backtest engine (open-source style: strategy plug-ins, simulated broker with proportional
  fees + slippage, no minimum fee), plus a JavaScript twin engine kept bit-identical via 21 golden
  parity tests.
- Data: Yahoo daily OHLCV, **total-return adjusted** (dividends reinvested). SPY 1993–2026 (8 420
  bars, real volume), QQQ 1999–, GLD/TLT/EEM 2002-04–, FEZ (Euro Stoxx 50) 2002–, VT (MSCI World)
  2008–, ^VIX 1990–, ^IRX (3M T-bill) 1970–, French UCITS (ESE.PA, PUST.PA, CW8.PA, PAEEM.PA,
  PCEU.PA, OBLI.PA) 2009-19–. Hourly SPY bars: 3 years (5 079 bars).
  **Data validated externally**: SPY total-return annual returns match the public record to ≤0.1pt
  for 2008/2013/2018/2020/2022/2023; VIX crisis closes exact to the cent (80.86 on 2008-11-20;
  82.69 on 2020-03-16).
- Costs: 0.5% fee + 0.05% slippage per order in early campaigns; 0.1% + 0.05% in later ones
  (deliberately favorable to active strategies). Fees are proportional (no minimum).
- Anti-look-ahead convention: every signal uses data through the **previous close** only; orders
  fill at the current open. This convention exists because an adversarial audit CAUGHT a real
  same-bar look-ahead (signal on close(t), fill at open(t)) that had inflated momentum results;
  it was fixed and everything re-run. Verification method: the "bar-tripling test" (tripling the
  current bar's OHLC must not change any order).
- Protocol: candidates **pre-registered by dated git commit before any result is computed**;
  selection on in-sample (IS) only; out-of-sample (OOS) read once; attribution controls (see §4);
  cost stress (fees ×2) and IS/OOS boundary shifts (±18 months) on champions.

## 3. Everything that was tested (9 campaigns, ~6 000 backtests)

1. **Cross-asset momentum rotation** (SPY/QQQ and French pairs; lookbacks 63/126/252; dual-momentum
   cash guard). Initially showed +30% OOS vs DCA — destroyed by audit: part same-bar look-ahead,
   part disguised Nasdaq beta. After fixes: best-of-grid OOS Sharpe 0.76–0.78 vs a deflated-Sharpe
   hurdle ≈ 1.07 (106 variants, ~1.3 effective validation samples because the three test markets
   are correlated 0.94–0.97). Decisive test: momentum rotation **underperforms naive DCA-into-QQQ
   by −5.8% to −13.3% OOS in all three markets** — it converts a beta decision into fees/whipsaw.
2. **Adaptive momentum** (multi-horizon blend 21/63/126/252, walk-forward information-coefficient
   re-weighting, conviction thresholds, dip boosts, cadences daily/weekly/monthly; 54 variants × 3
   markets). IC re-weighting shown to be noise (overlapping windows). Daily/weekly cadence loses to
   monthly after costs.
3. **Smart deployment** (allocation schemes winner/softmax/inverse-vol/equal/fixed × trend gates ×
   vol targeting × deploy pacing 100%/20%-per-day × dip accelerators; 150 runs). Signal-free pacing
   controls exposed an attribution error: an apparent +19% "immediate deployment" edge decomposed
   into +19.2% basket-mix effect vs a mis-specified benchmark and −0.2% pure timing. Pure calendar
   timing ≈ +0.05%/yr (drift over ~17 idle days), confirmed by theory.
4. **Selling/rotation variants**: 84 buy-only vs switch twin pairs. Switching (selling losers)
   loses **mean −41% OOS wealth** (range −14% to −75%). Universal across universes.
5. **Widened universe** (SPY, QQQ, GLD gold, TLT long bonds, EEM emerging; 2004–2026, the GLD/TLT/
   EEM data untouched by all prior research; 16 pre-registered candidates incl. classic dual
   momentum with selling, risk parity, trend gates). **All 16 lose to plain DCA-SPX both IS and
   OOS.** Diversifying assets reduced returns 1–3 CAGR points without materially reducing
   drawdowns (correlated crashes). PEA-implementable mirror worse. Euro Stoxx 50 (FEZ) and MSCI
   World (VT) ladders: every euro moved from SPX/QQQ to SX5E/World destroyed wealth (SX5E alone:
   −51.5% vs DCA-SPX over 24y with a WORSE max drawdown).
6. **Fear-timing on SPX alone** (reserve-and-release mechanics: hold cash, deploy all when the
   signal fires, 63-bar time-stop; 33 years; 14 pre-registered: VIX percentile 70/80/90 and
   absolute 25/30, realized-vol percentiles, capitulation volume, drawdown depths, half-base
   variants). **0/14 beat immediate deployment OOS; nothing meaningful even IS** (best +0.5% total
   over 18 IS years that include the dot-com crash and 2008).
7. **Money-market vs equity regime** (3M T-bill yield trend over 63d BOTH directions, yield
   percentile both tails, OBV accumulation AND distribution; 10 pre-registered). **0/10 beat
   immediate deployment OOS.**
8. **Granularity and intraday**:
   - Daily-DCA vs monthly-DCA vs immediate, with and without fees: differences ±0.3% total over
     33y; ranking follows average idle cash exactly; identical gaps with fees removed (proportional
     fees cancel).
   - Hourly campaign (3y of real hourly bars, hour-level reactivity, 7 pre-registered dip/vol/
     volume signals, 0.1% fees): IS-selected champion → **−0.01% OOS vs immediate**.
   - Execution tactics on 33y of OHLC: open vs close fill ±0.02%; TWAP +0.01%; limit ladders at
     −0.2%/−0.5%/−1%/−2% below open with close fallback: ±0.03% (adverse selection eats the
     discount). **Perfect-timing ceiling: buying at the exact daily LOW on every one of 403
     monthly orders = +0.63% TOTAL over 33 years** (worst case, exact high: −0.58%).
9. **Mass signal search**:
   - 10 AI agent personas (trend, mean-reversion, vol, macro, flow, seasonality, contrarian,
     breakout, risk-manager, statistician) invented 147 signals over a 26-feature library
     (returns 1d–252d, SMA ratios 20–200, RSI, realized vol + percentile, drawdowns 63/252, VIX
     level/percentile/Δ21, T-bill Δ63/percentile, volume ratio, OBV deviation, down-streaks,
     day-of-month, month). Result: 4/147 beat immediate IS (best +0.49% total); **0/147 OOS**;
     top-20 IS → 0/20 hold OOS.
   - Exhaustive sweep: **4 986 signals** (every feature × 20 quantile thresholds × both directions
     + 4 000 random two-condition ANDs). IS winners 3.0%; OOS winners 7.8%; **both: 0.66%, best
     double-positive +0.08% IS / +0.09% OOS** (noise). IS↔OOS rank correlation +0.71 — driven by
     the *persistent waiting cost*, not persistent alpha.
   - Mechanical decomposition (why): waiting for "5% dip" → mean wait 33 days, **pays +1.06% MORE
     than immediate** (cheaper only 36% of the time); VIX>p90 → +1.41% more (33%); RSI<30 →
     +2.05% more (38%). Dips are discounts on prices that rose while you waited.
10. **Theory panel** (five specialist analyses + committee): Merton/Kelly arithmetic (monthly
    μ≈0.6–0.9%, σ≈4.5% → f\*≈2.2–3.7, so the no-leverage cap binds: full investment is already
    ~0.3–0.45-fractional Kelly; reserve has no sizing justification); waiting costs ≈2.8bp/day
    with no offsetting option value under near-martingale prices; effective sample N≈15–25 regime
    blocks in 25 years (SE of a 25y Sharpe ≈0.20; detecting a 1%/yr edge needs ~centuries);
    variance is predictable (HAR-RV R² 30–60%) but unmonetizable buy-only without leverage.

## 4. Attribution controls used (to kill false positives)

Every campaign included: day-26 DCA (N1), **immediate deployment into the same assets (N2 — the
structural null all signals must beat)**, static equal-weight mix (isolates diversification),
DCA-into-the-hindsight-best-asset (the beta bar). Champions were selected on IS only, then OOS
read once, then stressed (fees ×2, boundary ±18m).

## 5. The standing conclusion you must attack

> After real retail costs, on liquid index ETFs, **no rule expressible over public daily/hourly
> price, volume, VIX and rates data beats immediately deploying each month's cash into a fixed
> allocation** (e.g. 70/30 SPX/QQQ — the only positive dial is the QQQ dose, which is a risk
> choice, not skill). The realized hierarchy of gains: broker fees (~+0.35%/contribution,
> certain) > equity beta dose > immediate-vs-day-26 deployment (~+0.7% lifetime) > ALL timing
> (bounded by the +0.63% perfect-foresight ceiling). The optimal system has zero fitted
> parameters.

## 6. Your investigation mandate

Work through ALL of the following, quantitatively:

1. **Methodology audit.** Hunt for flaws that could FORCE the null result (a rigged game would
   also produce "nothing works"): the deposit calendar (cash deposited at month start, benchmark
   buys day 26 — who does this favor?); the 63-bar time-stop (does force-deploying at day 63
   systematically truncate signal patience? what would max_hold=∞ change and is it even coherent?);
   fills at open with previous-close signals (does this destroy genuinely fast signals — and is
   any such signal plausible at retail latency?); total-return prices (correct for accumulation?);
   the reserve-release mechanics (is "all-in on fire" the right monetization of a timing signal,
   vs proportional sizing?); percentile windows (5y rolling — regime bias?); the two-condition
   AND cap in the exhaustive sweep (what would OR / 3+ conditions / continuous sizing add,
   and would multiplicity swamp it?).
2. **Hypothesis-space gaps.** List signal families and data NOT covered that have credible
   peer-reviewed evidence at daily-to-monthly horizons for INDEX-level timing, with honest priors:
   credit spreads (HY-Treasury), yield-curve slope, VIX futures term structure (contango/
   backwardation — note spot VIX vs VIX3M was designed away, was that legitimate?), put/call
   ratios, breadth (% above 200dma), cross-asset lead-lag, earnings yield vs bill yield,
   seasonality interactions, machine learning with combinatorially purged CV. For each: expected
   effect size vs the ~55bp/order + 2.8bp/day hurdle, data availability for 20+ years, and whether
   it could plausibly clear a deflated-Sharpe hurdle of ~1.07 given ~1.3 effective validation
   samples.
3. **Theory attack.** Under what conditions does waiting have POSITIVE option value (predictable
   negative-drift regimes? vol-managed portfolios literature — Moreira & Muir — and why buy-only
   no-leverage cannot implement it? does the countercyclical-premium argument survive?). Is the
   +0.63% perfect-timing ceiling computed correctly, and does it really bound all intraday
   approaches (consider signals that CHANGE which day the order happens, not just the price within
   the day)?
4. **The strongest counter-experiment.** Specify the ONE pre-registrable experiment most likely to
   overturn the conclusion. It must be implementable in the described harness: JSON spec =
   {"name", "conds": [{"feature", "op": ">"|"<", "thr"}], "base_deploy"} over the feature library
   above, or a concrete new data series + mechanics with 20+ years of availability. State the
   minimum OOS excess (in % of final wealth AND annualized) it must achieve to be significant
   given the multiplicity already spent.
5. **Verdict.** Is the conclusion sound, overstated, or wrong? Separate: (a) what is proven for
   THIS investor (retail, monthly flow, ETF universe, no leverage/shorting), (b) what is NOT
   proven and merely suggested, (c) what a professional desk with different constraints could
   still do.

Rules: cite specific numbers from §3 when you use them; distinguish backtested facts from your
priors; quantify every claim (no "could potentially"); if you find no flaw, say so explicitly
rather than inventing soft objections.
