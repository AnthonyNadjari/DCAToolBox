"""Signal lab: mass-evaluate agent-invented deployment signals, honestly.

Agents propose signals as JSON specs — one or two ANDed conditions over a
fixed feature library — and this lab evaluates every spec with the same
reserve-release deployment mechanics used throughout the repo: cash arrives
monthly, waits, and deploys entirely the day the signal fires (or after a
63-bar time-stop). Features are computed strictly on data through the PREVIOUS
close; fills happen at the current open. Fees 0.1% + 0.05% slippage
(deliberately favorable to active signals).

Controls: `dca` (buy on day 26) and `now` (deploy on arrival) — every signal's
job is to beat `now`, the structural null.

Spec format (JSON list)::

    [{"name": "vix_spike_dip",
      "conds": [{"feature": "vix_pctl", "op": ">", "thr": 0.9},
                {"feature": "dd_63", "op": "<", "thr": -0.05}],
      "base_deploy": 0.0}, ...]

Usage::

    PYTHONPATH=. python scripts/signal_lab.py --specs specs.json --out results.json
    PYTHONPATH=. python scripts/signal_lab.py --features   # list the library
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data_real")
BUDGET = 1000.0
MAX_HOLD = 63
IS_END = "2010-12-31"  # IS: 1993-02 -> 2010-12 | OOS: 2011-01 -> 2026-07


def _load(ticker: str) -> pd.DataFrame:
    raw = json.loads((DATA / f"{ticker}.json").read_text())
    idx = pd.DatetimeIndex(pd.to_datetime(raw["dates"]), name="date")
    cols = {k: raw[k] for k in ("open", "high", "low", "close") if k in raw}
    if "volume" in raw:
        cols["volume"] = raw["volume"]
    return pd.DataFrame(cols, index=idx)


def build_features() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """SPY frame + the feature library (values as of each day's own close)."""
    spy = _load("SPY")
    vix = _load("^VIX")["close"].reindex(spy.index).ffill()
    irx = _load("^IRX")["close"].reindex(spy.index).ffill()
    c, v = spy["close"], spy["volume"].astype(float)
    f: dict[str, pd.Series] = {}

    for n in (5, 21, 63, 126, 252):
        f[f"ret_{n}"] = c.pct_change(n)
    for n in (20, 50, 100, 200):
        f[f"sma_ratio_{n}"] = c / c.rolling(n).mean() - 1
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
    f["rsi_14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rets = c.pct_change()
    for n in (21, 63):
        f[f"rvol_{n}"] = rets.rolling(n).std() * np.sqrt(252)
    f["rvol_pctl"] = f["rvol_21"].rolling(1260, min_periods=252).rank(pct=True)
    for n in (63, 252):
        f[f"dd_{n}"] = c / c.rolling(n).max() - 1
    f["vix"] = vix
    f["vix_pctl"] = vix.rolling(1260, min_periods=252).rank(pct=True)
    f["vix_chg_21"] = vix.diff(21)
    f["irx_chg_63"] = irx.diff(63)
    f["irx_pctl"] = irx.rolling(1260, min_periods=252).rank(pct=True)
    f["vol_ratio_63"] = v / v.rolling(63).mean()
    obv = (np.sign(rets.fillna(0)) * v).cumsum()
    f["obv_dev"] = (obv - obv.rolling(126).mean()) / v.rolling(126).mean()
    f["down_streak"] = (rets < 0).astype(int).groupby((rets >= 0).cumsum()).cumsum().astype(float)
    f["day_of_month"] = pd.Series(spy.index.day.astype(float), index=spy.index)
    f["month"] = pd.Series(spy.index.month.astype(float), index=spy.index)
    f["ret_1"] = rets

    # Signals may only use data through the PREVIOUS close: lag everything by 1.
    feats = {k: s.shift(1).to_numpy(dtype=float) for k, s in f.items()}
    return spy, feats


def _fired(spec: dict, feats: dict[str, np.ndarray], n: int) -> np.ndarray:
    out = np.ones(n, dtype=bool)
    for cond in spec["conds"]:
        x = feats[cond["feature"]]
        thr = float(cond["thr"])
        ok = x > thr if cond["op"] == ">" else x < thr
        out &= np.where(np.isfinite(x), ok, False)
    return out


def simulate(
    spy: pd.DataFrame,
    fired: np.ndarray,
    base_deploy: float,
    seg: slice,
    fee: float = 0.001,
    slip: float = 0.0005,
) -> dict:
    """Reserve-release accumulation over one segment (cold start)."""
    dates = spy.index[seg]
    op = spy["open"].to_numpy(dtype=float)[seg]
    cl = spy["close"].to_numpy(dtype=float)[seg]
    fr = fired[seg]
    month = dates.to_period("M")
    is_deposit = np.r_[True, month[1:] != month[:-1]]
    cash = shares = 0.0
    waiting = 0
    orders = 0
    for i in range(len(dates)):
        if is_deposit[i]:
            inflow = BUDGET
            cash += inflow
            if base_deploy > 0:
                spend = inflow * base_deploy
                shares += spend * (1 - fee) / (op[i] * (1 + slip))
                cash -= spend
                orders += 1
        if cash > 1.0:
            waiting += 1
            if fr[i] or waiting >= MAX_HOLD:
                shares += cash * (1 - fee) / (op[i] * (1 + slip))
                cash = 0.0
                orders += 1
                waiting = 0
        else:
            waiting = 0
    return {"final": round(shares * cl[-1] + cash, 0), "orders": orders}


def evaluate(specs: list[dict], fee: float = 0.001, slip: float = 0.0005) -> list[dict]:
    """Run every spec (plus the two controls) over IS and OOS."""
    spy, feats = build_features()
    n = len(spy)
    is_end = spy.index.searchsorted(pd.Timestamp(IS_END), side="right")
    segs = {"is": slice(0, is_end), "oos": slice(is_end, n)}
    always = np.ones(n, dtype=bool)
    never = np.zeros(n, dtype=bool)
    day26 = spy.index.day >= 26  # first bar >= 26 handled by waiting mechanics

    out = []
    controls = [
        ("now", always, 0.0),
        ("dca26", np.asarray(day26), 0.0),
    ]
    for name, arr, base in controls:
        out.append(
            {
                "name": f"CONTROL_{name}",
                "conds": [],
                **{s: simulate(spy, arr, base, sl, fee, slip) for s, sl in segs.items()},
            }
        )
    for spec in specs:
        fired = _fired(spec, feats, n) if spec["conds"] else never
        out.append(
            {
                "name": spec["name"],
                "conds": spec["conds"],
                "base_deploy": spec.get("base_deploy", 0.0),
                **{
                    s: simulate(spy, fired, spec.get("base_deploy", 0.0), sl, fee, slip)
                    for s, sl in segs.items()
                },
            }
        )
    return out


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--fee", type=float, default=0.001)
    ap.add_argument("--slippage", type=float, default=0.0005)
    ap.add_argument("--features", action="store_true")
    args = ap.parse_args()
    if args.features:
        _, feats = build_features()
        print("\n".join(sorted(feats)))
        return
    specs = json.loads(Path(args.specs).read_text())
    results = evaluate(specs, fee=args.fee, slip=args.slippage)
    payload = json.dumps(results, indent=1)
    if args.out:
        Path(args.out).write_text(payload)
        print(f"wrote {args.out} ({len(results)} rows)")
    else:
        print(payload)


if __name__ == "__main__":
    main()
