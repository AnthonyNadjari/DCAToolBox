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
