"""The OFF-position dial: how much leverage to KEEP when the gate says off.

gate_lab.py showed the design axis that matters is not the gate condition
(trend beats slope/credit combos) but the destination. This sweeps it:
when SPX < 200dma at the monthly check, keep x of the pot in the levered
70/30 CL2/LQQ sleeve and park 1-x in cash, x in {0..1}.

Scored on both eras (premium era 2009-07..2026-08 real funds; payout era
2002-06..2013-09 synthetic 2x), plus rolling 5y DCA windows vs holding ESE.
Mechanism sanity: vol drag scales with exposure squared, so halving exposure
in the high-vol regime removes ~3/4 of the drag while keeping half the beta;
the dial is smooth and monotone in x - nothing to overfit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from gate_lab import ZERO, add_signals, run
from post2009 import build_inputs_real
from rolling import build_inputs, rolling_dca


def price(df: pd.DataFrame, x: float) -> pd.Series:
    wl = lambda d: x + (1 - x) * d["g_trend"].shift(1)  # noqa: E731
    return (1 + run(df, wl, ZERO)).cumprod()


def main() -> None:
    real = add_signals(build_inputs_real())
    real["r_lev"] = real["r_mix_lev"]
    pay = add_signals(build_inputs()).loc["2002-06-01":"2013-09-15"]

    rows = []
    for x in (0.0, 0.25, 0.4, 0.5, 0.6, 0.75, 1.0):
        row = {"off_lev": x}
        for label, df in (("premium", real), ("payout", pay)):
            p = price(df, x)
            yrs = (df.index[-1] - df.index[0]).days / 365.25
            null = (1 + df["r_base"]).cumprod()
            row[label] = {
                "cagr": round(float(p.iloc[-1] ** (1 / yrs) - 1), 4),
                "maxdd": round(float((p / p.cummax() - 1).min()), 3),
                "roll5y": rolling_dca(p, null, 5),
            }
        rows.append(row)
    json.dump(rows, open(Path(__file__).parent / "results_off_dose.json", "w"), indent=1)

    print(f"{'off keeps':>9} | {'09+ cagr':>8} {'dd':>5} {'5y win':>6} {'5y p5':>7} | {'02-13 cagr':>10} {'dd':>5} {'5y win':>6} {'5y p5':>7}")
    for r in rows:
        a, b = r["premium"], r["payout"]
        print(
            f"{r['off_lev']:>9.0%} | {a['cagr']:>8.1%} {a['maxdd']:>5.0%} "
            f"{a['roll5y']['win_rate']:>6.0%} {a['roll5y']['p5']:>+7.1%} | "
            f"{b['cagr']:>10.1%} {b['maxdd']:>5.0%} "
            f"{b['roll5y']['win_rate']:>6.0%} {b['roll5y']['p5']:>+7.1%}"
        )


if __name__ == "__main__":
    main()
