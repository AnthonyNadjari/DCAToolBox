"""Short-horizon rolling-window study of risk-mitigated leverage policies.

The published verdict compares three all-or-nothing policies over 5- and
10-year windows. Two things were missing for a savings mandate: shorter
horizons (1, 2, 3 years — the ones a saver actually feels) and the middle
ground between "no leverage" and "100% 2x".

Every policy here is expressed at the level of the MONTHLY FLOW over the four
realised sleeves recovered by ``sleeves.py`` (1x S&P, 1x 70/30 mix, 2x 70/30
ungated, 2x 70/30 trend-gated). Splitting the monthly contribution across
sleeves is exact — each sleeve is its own account compounding at its own
realised return, nothing is ever sold, so no policy pays a switching cost the
source paths did not already pay.

Metrics are savings metrics, not wealth-maximisation metrics: every window is
scored as a MULTIPLE OF THE MONEY PUT IN, the probability of ending below
contributions is reported, and the drawdown is the drawdown of the
ACCUMULATING portfolio (what the investor sees on his statement), not of the
fund.

Caveats printed with the results: rolling windows overlap (384 five-year
windows are ~7 independent ones), 1989-2013 is a backfill of the leveraged
sleeves, drawdowns are month-end and understate intramonth pain, and the
policy menu was chosen after seeing this data.

Usage::

    python research_bbg/horizons.py [--out research_bbg/results_horizons.json]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

SRC = Path("research_bbg/sleeves.json")
FEE = 0.005
CONTRIB = 1000.0
HORIZONS_Y = (1, 2, 3, 5, 7, 10)

# Sleeve keys in the recovered dataset.
ONE_X = "ese"
MIX = "mix7030"
LEV = "lev_nogate"
GATED = "strategy"

Weights = dict[str, float]
Policy = Callable[[dict[str, float], int], Weights]


def _fixed(weights: Weights) -> Policy:
    """A constant split of the monthly flow across sleeves."""

    def policy(_wealth: dict[str, float], _month: int) -> Weights:
        return weights

    return policy


def _capped(sleeve: str, cap: float, base: str = MIX) -> Policy:
    """Flow-only cap: send new money to `sleeve` only while it sits below
    `cap` of total wealth, otherwise to `base`. Never sells."""

    def policy(wealth: dict[str, float], _month: int) -> Weights:
        total = sum(wealth.values())
        if total <= 0:
            return {sleeve: 1.0}
        return {sleeve: 1.0} if wealth.get(sleeve, 0.0) / total < cap else {base: 1.0}

    return policy


def _glide(sleeve: str, start: float, end: float, months: int, base: str = MIX) -> Policy:
    """Leveraged share of the flow declining linearly over `months`."""

    def policy(_wealth: dict[str, float], month: int) -> Weights:
        t = min(1.0, month / months) if months else 1.0
        share = start + (end - start) * t
        return {sleeve: share, base: 1.0 - share}

    return policy


POLICIES: dict[str, Policy] = {
    # --- baselines ---
    "1x S&P": _fixed({ONE_X: 1.0}),
    "1x 70/30": _fixed({MIX: 1.0}),
    # --- partial leverage, never gated, never sold ---
    "25% 2x": _fixed({LEV: 0.25, MIX: 0.75}),
    "50% 2x": _fixed({LEV: 0.50, MIX: 0.50}),
    "75% 2x": _fixed({LEV: 0.75, MIX: 0.25}),
    "100% 2x": _fixed({LEV: 1.0}),
    # --- partial leverage, trend-gated sleeve ---
    "25% 2x gated": _fixed({GATED: 0.25, MIX: 0.75}),
    "50% 2x gated": _fixed({GATED: 0.50, MIX: 0.50}),
    "75% 2x gated": _fixed({GATED: 0.75, MIX: 0.25}),
    "100% 2x gated": _fixed({GATED: 1.0}),
    # --- structural mitigations ---
    "cap 2x at 30%": _capped(LEV, 0.30),
    "cap 2x at 50%": _capped(LEV, 0.50),
    "cap gated at 50%": _capped(GATED, 0.50),
    "glide 100->0% (10y)": _glide(LEV, 1.0, 0.0, 120),
    "glide 50->0% (5y)": _glide(LEV, 0.5, 0.0, 60),
}


def simulate(
    rets: dict[str, np.ndarray], policy: Policy, start: int, months: int
) -> tuple[float, float, float]:
    """Run one DCA window: returns (final wealth, contributions, max drawdown)."""
    wealth: dict[str, float] = {}
    contributed = 0.0
    path = np.empty(months)
    for k in range(months):
        i = start + k
        weights = policy(wealth, k)
        cash_in = CONTRIB * (1 - FEE)
        contributed += CONTRIB
        for sleeve, share in weights.items():
            if share > 0:
                wealth[sleeve] = wealth.get(sleeve, 0.0) + cash_in * share
        for sleeve in list(wealth):
            wealth[sleeve] *= 1.0 + rets[sleeve][i]
        path[k] = sum(wealth.values())
    peak = np.maximum.accumulate(path)
    mdd = float(np.min(path / peak - 1.0))
    return float(path[-1]), contributed, mdd


def _score(name: str, mults: np.ndarray, mdds: np.ndarray, base: np.ndarray) -> dict:
    """Savings-oriented summary of one policy over one set of windows."""
    return {
        "policy": name,
        "windows": int(mults.size),
        "median_mult": round(float(np.median(mults)), 4),
        "p5_mult": round(float(np.percentile(mults, 5)), 4),
        "worst_mult": round(float(mults.min()), 4),
        "best_mult": round(float(mults.max()), 4),
        "p_below_contrib": round(float((mults < 1.0).mean()), 4),
        "median_mdd": round(float(np.median(mdds)), 4),
        "worst_mdd": round(float(mdds.min()), 4),
        "win_vs_1x": round(float((mults > base).mean()), 4),
        "median_excess_vs_1x": round(float(np.median(mults - base)), 4),
    }


def study(data: dict) -> dict:
    """Score every policy over every rolling window at every horizon.

    Windows are also split by era: those starting before 2009 (the leveraged
    sleeves are a backfill there, and the era contains the two multi-year
    bears) and those starting after (real fund data, V-shaped crashes only).
    """
    rets = {k: np.asarray(v, dtype=float) for k, v in data["returns"].items()}
    dates = np.asarray(data["dates"])
    n = len(dates)
    real_era = np.asarray([d >= "2009-01-01" for d in dates])
    out: dict[str, dict] = {}
    for years in HORIZONS_Y:
        months = years * 12
        starts = np.arange(0, n - months + 1)
        modern = real_era[starts]
        raw: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for name, policy in POLICIES.items():
            scored = [simulate(rets, policy, int(s), months) for s in starts]
            raw[name] = (
                np.asarray([f / c for f, c, _ in scored]),
                np.asarray([d for _, _, d in scored]),
            )
        base_all = raw["1x S&P"][0]
        out[f"{years}y"] = {
            "all": [_score(k, m, d, base_all) for k, (m, d) in raw.items()],
            "backfill_era": [
                _score(k, m[~modern], d[~modern], base_all[~modern]) for k, (m, d) in raw.items()
            ],
            "real_era": [
                _score(k, m[modern], d[modern], base_all[modern]) for k, (m, d) in raw.items()
            ],
        }
    return out


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research_bbg/results_horizons.json")
    args = ap.parse_args()
    data = json.loads(SRC.read_text())
    results = study(data)
    payload = {
        "source": data["generated_from"],
        "months": len(data["dates"]),
        "span": [data["dates"][0], data["dates"][-1]],
        "fee": FEE,
        "contribution": CONTRIB,
        "horizons": results,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1))

    for years in HORIZONS_Y:
        for era in ("all", "backfill_era", "real_era"):
            rows = results[f"{years}y"][era]
            if not rows[0]["windows"]:
                continue
            print(
                f"\n=== {years}y / {era} (n={rows[0]['windows']}) — multiple of contributions ==="
            )
            print(
                f"{'policy':22s} {'median':>7} {'p5':>7} {'worst':>7} "
                f"{'P<1x':>6} {'medDD':>7} {'wDD':>7} {'win1x':>6}"
            )
            for r in rows:
                print(
                    f"{r['policy']:22s} {r['median_mult']:7.2f} {r['p5_mult']:7.2f} "
                    f"{r['worst_mult']:7.2f} {100 * r['p_below_contrib']:5.0f}% "
                    f"{100 * r['median_mdd']:6.0f}% {100 * r['worst_mdd']:6.0f}% "
                    f"{100 * r['win_vs_1x']:5.0f}%"
                )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
