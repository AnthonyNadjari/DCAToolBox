# Adversarial investigation: final verdict

Closing record of the external adversarial audit requested in
`INVESTIGATION_PROMPT.md`. An independent AI investigator was given the full
research record (10 campaigns, ~6 000 backtests) and a mandate to break the
conclusion. This documents the exchange and its outcome.

## The exchange

1. **Round 1 — the audit.** The investigator produced a full methodology audit,
   hypothesis-space review, theory attack and counter-experiment. It contained
   two valid criticisms and three factual errors.

   *Valid*: (a) the all-in reserve-release sizing had never been varied against
   proportional/continuous sizing; (b) the VIX futures term structure (spot vs
   3-month) was the one volatility family never tested.

   *Errors*: (1) it read the deposit calendar backwards (claimed the day-26
   benchmark was "structurally favored" by +0.7% — inverted: cash arrives at
   month start, so the +0.7% lifetime drift favors the immediate-deployment
   null, making the null HARDER to beat); (2) it attributed the −41% mean OOS
   switching loss to tax friction and built its constraint-sensitivity verdict
   on removing a tax the simulations never charged (the loss is whipsaw +
   forfeited beta, measured tax-free); (3) its deflated-Sharpe arithmetic
   confused monthly with annualized volatility, and it reused the +1.06%
   dip-wait figure — a measured COST of waiting — as a prospective benefit.

2. **Round 2 — the counter-experiment.** Its strongest challenger was run
   exactly as specified, pre-registered by dated commit before any result
   (`scripts/vix_ts_experiment.py`, commit b1bfb3b). Data: CBOE ^VIX3M daily
   since 2006-07 (~20y), validated at the crises (VIX/VIX3M = 1.17 on
   2008-11-20, 1.22 on 2020-03-16). IS 2006–2016, OOS 2017–2026. Three fixed
   candidates including the monotone proportional sizing the audit demanded.

   | Candidate                                   | IS vs immediate | OOS vs immediate |
   |---------------------------------------------|-----------------|------------------|
   | DCA day-26 (control)                        | −0.30%          | −0.83%           |
   | Backwardation p90 percentile (audit's spec) | −0.38%          | −1.42%           |
   | Absolute backwardation VIX>VIX3M (0 params) | −0.94%          | −1.83%           |
   | Monotone proportional sizing                | −0.82%          | −0.62%           |

   0/3 beat immediate deployment even in-sample; identical under fees ×2.
   Mechanism: backwardation fires during crises, but prices climbed while the
   cash waited to get there — the ~2.8bp/day carry eats the discount, the same
   arithmetic that killed spot-VIX timing.

3. **Round 3 — the concession.** The investigator accepted all three
   corrections, conceded the conclusion for this investor profile, declared
   "no further experiments" (naming another candidate would be multiplicity
   farming), and withdrew its "longer time-stop" objection: extending the
   63-bar horizon doubles the idle-cash drag and only helps if negative drift
   is predictable — a capability no tested signal has.

## The standing verdict (now audited)

For a French retail investor with monthly cash flow, liquid index ETFs, no
leverage and no shorting: **no rule expressible over public daily/hourly
price, volume, VIX and rates data beats immediately deploying each month's
cash into a fixed allocation.** Hierarchy of what matters: broker fees
(~+0.35%/contribution, certain) > equity beta dose (each 10pts of QQQ ≈ +8%
full-period wealth — a risk choice, not skill) > immediate-vs-day-26
deployment (~+0.7% lifetime) > all timing (bounded by the +0.63%
perfect-foresight ceiling over 33 years). Zero fitted parameters. Never sell.

## Addendum (2026-07-20): the Bloomberg campaigns — the signal branch is closed

Two further pre-registered campaigns were run after the user gained Bloomberg access,
covering every data family the original program lacked:

1. **Public-proxy macro campaign** (`scripts/macro_signals_experiment.py`, 13 fixed
   candidates on Baa−10Y credit, Baa−Aaa quality, 10Y−3M curve, MOVE, NFCI, publication
   lags modeled): **0/13** — every candidate lost to immediate deployment both IS
   (1993–2012) and OOS (2013–2026), −0.5% to −2.5%, unchanged at fees ×2. NFCI loses
   despite its revised-history look-ahead advantage.
2. **Bloomberg-exclusive campaign** (Streamlit lab, Bloomberg terminal data, 12 fixed
   candidates, 2 dropped on unresolved tickers): HY−IG decompression percentile, absolute
   HY OAS > 800bp, post-panic peak-retreat, new-lows washout, AAII panic spread and bear
   extreme, margin-debt deleveraging, and three REAL VIX-futures-curve backwardation
   measures (constant-maturity CM30 < spot, deep roll yield, mid-curve inversion):
   **0/10 beat immediate deployment IS; 0 read OOS; 0 survived** (−0.7% to −2.1% both
   sides of the 2012-12-31 cut, fees ×2 identical). Even the cycle-position signal
   designed specifically to dodge the waiting cost (deploy after the OAS peak) lost.

3. **Signal Factory** (Streamlit lab, all pulled Bloomberg data, 46 features incl. the IV
   surface, real UX curve, OAS, breadth, AAII, margin debt): Layer A — 1/1,380 candidates
   positive on both sides of the 2012 cut (chance level); Layer B — the top-20 selected
   in-sample went 0/20 out-of-sample; Layer C — the ADAPTIVE version (walk-forward
   re-selection of the top-10 signals every two years, zero hindsight, 2005→2026) ended
   at **−9.19% vs immediate deployment**, identical at 10bp and 50bp fees. The
   "hedge-fund-style" adaptive selector was implemented and it lost: adaptation cannot
   rescue signals whose edge is zero, it only compounds their waiting costs.

Cumulative tally across the whole program: ~6,000 grid backtests, 147 agent-invented
signals, 4,986 exhaustive signals, 24 pre-registered fear-timing/money-market candidates,
3 VIX-term-structure proxies, 13 macro proxies, 10 Bloomberg-exclusive candidates —
**zero timing signals beat immediate deployment out of sample.** The branch "use any
public or terminal data to time purchases" is closed. What remains open is structural
only: the leverage dial (CL2/LQQ, PEA-eligible) and execution-cost minimization.

## The one open dial: leverage (a risk choice, stated honestly)

The audit's corrected constraint-sensitivity verdict — which survives
scrutiny — is that the only relaxation with quantitative support is modest
leverage: Kelly/Merton puts f*≈2.2–3.7, so full investment is only ~0.3–0.45
fractional Kelly, and a 1.25× exposure adds ~+0.18%/month of expected drift
before costs, an order of magnitude above any timing effect ever measured.
Caveats that keep this a risk dial and not alpha: PEA-eligible leverage means
daily-reset leveraged UCITS (path-dependent volatility drag, not Merton
leverage), higher fund fees, and materially deeper drawdowns. It is the same
kind of decision as the QQQ dose — more beta, not more skill.
