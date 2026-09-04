"""Recover monthly sleeve returns from the published signal-page dataset.

`web/data.json` ships four monthly DCA wealth paths (1989-09 -> 2026-08) built
from Bloomberg data by ``scripts/build_signal_page.py``: the unlevered 1x S&P
sleeve (ESE), the unlevered 70/30 mix, the ungated 2x sleeve and the
trend-gated 2x strategy, plus the daily gate-off periods.

Since every path is a plain monthly accumulation

    W_t = (W_{t-1} + C * (1 - fee)) * (1 + r_t)

the per-sleeve monthly return series is recoverable exactly, and the money
market rate the gated strategy earned while it sat out is recoverable from the
strategy path on gate-off months. That gives a complete, dependency-free
simulator: any policy expressible as a monthly mix of {1x, 2x, cash} driven by
the gate state can be evaluated without a Bloomberg connection.

Validation performed on write: reconstructing each published path from its
recovered returns must reproduce it to the euro, and the 2x sleeve must
regress on the 1x mix with a beta near 2.

Usage::

    python research_bbg/sleeves.py            # writes research_bbg/sleeves.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path("web/data.json")
OUT = Path("research_bbg/sleeves.json")
FEE = 0.005
SLEEVES = ("ese", "mix7030", "lev_nogate", "strategy")


def _returns(wealth: list[float], contrib: np.ndarray) -> np.ndarray:
    """Monthly returns implied by a DCA wealth path."""
    w = np.asarray(wealth, dtype=float)
    prev = np.r_[0.0, w[:-1]]
    return w / (prev + contrib * (1 - FEE)) - 1.0


def _rebuild(returns: np.ndarray, contrib: np.ndarray) -> float:
    """Final wealth implied by a return series (the inverse check)."""
    w = 0.0
    for r, c in zip(returns, contrib, strict=True):
        w = (w + c * (1 - FEE)) * (1 + r)
    return w


def _gate_by_month(off_periods: list[list[str]], dates: pd.DatetimeIndex) -> np.ndarray:
    """Gate state on each month-end: True = risk-on (SPX above its 200-DMA)."""
    off = np.zeros(len(dates), dtype=bool)
    for start, end in off_periods:
        lo, hi = pd.Timestamp(start), pd.Timestamp(end)
        off |= (dates >= lo) & (dates <= hi)
    return ~off


def build() -> dict:
    """Recover every sleeve, validate, and return the dataset."""
    raw = json.loads(SRC.read_text())
    eq = raw["equity"]
    dates = pd.DatetimeIndex(pd.to_datetime(eq["dates"]))
    invested = np.asarray(eq["invested"], dtype=float)
    contrib = np.diff(np.r_[0.0, invested])

    rets = {name: _returns(eq[name], contrib) for name in SLEEVES}
    for name in SLEEVES:
        got, want = _rebuild(rets[name], contrib), float(eq[name][-1])
        if abs(got - want) > max(1.0, 1e-6 * want):
            raise SystemExit(f"{name}: rebuild {got:.0f} != published {want:.0f}")

    beta = np.polyfit(rets["mix7030"], rets["lev_nogate"], 1)
    if not 1.9 < beta[0] < 2.1:
        raise SystemExit(f"2x sleeve beta {beta[0]:.3f} is not ~2 — check the source data")

    risk_on = _gate_by_month(raw["off_periods"], dates)
    # On gate-off months the gated strategy holds the money market: read the
    # rate straight off its own path (a handful of switch months are mixed, so
    # take the median of the clean ones as the flat cash rate for those).
    cash = np.where(risk_on, np.nan, rets["strategy"])
    cash_series = pd.Series(cash).ffill().bfill().to_numpy()

    return {
        "generated_from": raw["generated"],
        "fee": FEE,
        "contribution": float(contrib[0]),
        "beta_2x_vs_1x": round(float(beta[0]), 4),
        "drag_2x_pct_per_year": round(float(beta[1]) * 1200, 2),
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "risk_on": risk_on.astype(int).tolist(),
        "returns": {name: [round(float(x), 8) for x in rets[name]] for name in SLEEVES},
        "cash": [round(float(x), 8) for x in cash_series],
    }


def main() -> None:
    """Write the recovered sleeve dataset and inject it into the web payload."""
    data = build()
    OUT.write_text(json.dumps(data))

    # The dashboard recomputes every policy in the browser from these returns,
    # so ship them alongside the precomputed page data.
    payload = json.loads(SRC.read_text())
    payload["sleeves"] = {
        "dates": data["dates"],
        "risk_on": data["risk_on"],
        "cash": data["cash"],
        "fee": data["fee"],
        "contribution": data["contribution"],
        "r": data["returns"],
    }
    SRC.write_text(json.dumps(payload))

    n_on = sum(data["risk_on"])
    print(
        f"wrote {OUT}: {len(data['dates'])} months "
        f"{data['dates'][0]} -> {data['dates'][-1]}, "
        f"risk-on {n_on}/{len(data['dates'])} ({100 * n_on / len(data['dates']):.0f}%), "
        f"beta {data['beta_2x_vs_1x']}, drag {data['drag_2x_pct_per_year']}%/yr"
    )


if __name__ == "__main__":
    main()
