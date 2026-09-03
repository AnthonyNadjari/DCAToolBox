"""Check-day robustness of the production gate: does the *day of the month*
the 200dma signal is checked change the verdict?

The production rule checks SPX vs its 200dma once a month, on deposit day
(first bar of the month). sma_window.py swept the MA window and the check
FREQUENCY (daily vs monthly) but never the check DAY. If the premium/payout
profile of the 25%-off rule flips around depending on which trading day of
the month the check lands, the production rule is partly calendar luck.

Design: identical mechanics to gate_lab/off_dose (monthly weights, signal
from previous close, 0.5% fee per traded leg, EUR cash refuge), but the
monthly check lands on the k-th trading day of each month instead of the
first. Swept for k in {0, 5, 10, 15, 20} on both eras:

- premium era 2009-07 -> 2026-08, real 70/30 CL2/LQQ
- payout era 2002-06 -> 2013-09, synthetic 2x on the ESE frame

Controls: off=100% (no gate, check-day invariant by construction) and
off=0% (the old full-cash gate) alongside the production off=25%.

Usage::

    python research_bbg/checkday.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from gate_lab import add_signals
from post2009 import build_inputs_real
from rolling import FEE, build_inputs, rolling_dca


def check_mask(idx: pd.DatetimeIndex, k: int) -> np.ndarray:
    """True on the k-th trading day of each month (clamped to month length)."""
    s = pd.Series(idx, index=idx)
    pos = s.groupby(idx.to_period("M")).cumcount()  # 0-based position in month
    size = s.groupby(idx.to_period("M")).transform("size")
    day = np.minimum(k, size - 1)
    return (pos == day).to_numpy()


def run_gated(df: pd.DataFrame, off_keep: float, mask: np.ndarray) -> pd.Series:
    """Daily returns of the off=off_keep trend-gated lev sleeve, checks on mask."""
    wl_t = (off_keep + (1 - off_keep) * df["g_trend"].shift(1)).to_numpy()
    rl = df["r_lev"].to_numpy()
    rc = df["r_cash"].to_numpy()
    wl = 0.0
    out = np.zeros(len(df))
    for i in range(len(df)):
        cost = 0.0
        if mask[i] and np.isfinite(wl_t[i]):
            nl = float(np.clip(wl_t[i], 0, 1))
            cost = abs(nl - wl) * FEE
            wl = nl
        out[i] = wl * rl[i] + (1 - wl) * rc[i] - cost
    return pd.Series(out, index=df.index)


def main() -> None:
    real = add_signals(build_inputs_real())
    real["r_lev"] = real["r_mix_lev"]
    pay = add_signals(build_inputs()).loc["2002-06-01":"2013-09-15"]

    K = (0, 5, 10, 15, 20)
    OFFS = (0.0, 0.25, 1.0)
    rows = []
    for off in OFFS:
        for label, df in (("premium", real), ("payout", pay)):
            null = (1 + df["r_base"]).cumprod()
            yrs = (df.index[-1] - df.index[0]).days / 365.25
            for k in K:
                mask = check_mask(df.index, k)
                r = run_gated(df, off, mask)
                p = (1 + r).cumprod()
                rows.append(
                    {
                        "off": off,
                        "era": label,
                        "check_day": k,
                        "cagr": round(float(p.iloc[-1] ** (1 / yrs) - 1), 4),
                        "maxdd": round(float((p / p.cummax() - 1).min()), 3),
                        "roll5y": rolling_dca(p, null, 5),
                    }
                )
    json.dump(rows, open(Path(__file__).parent / "results_checkday.json", "w"), indent=1)

    for off in OFFS:
        print(f"\n=== off keeps {off:.0%} ===")
        print(f"{'era':8s} {'day':>4} {'cagr':>8} {'maxdd':>6} {'5y win':>7} {'5y med':>8} {'5y p5':>7}")
        for r in rows:
            if r["off"] != off:
                continue
            k5 = r["roll5y"]
            print(
                f"{r['era']:8s} {r['check_day']:4d} {r['cagr']:>8.1%} {r['maxdd']:>6.0%} "
                f"{k5['win_rate']:>7.0%} {k5['median']:>+8.1%} {k5['p5']:>+7.1%}"
            )


if __name__ == "__main__":
    main()
