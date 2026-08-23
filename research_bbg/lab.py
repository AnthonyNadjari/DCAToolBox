"""Evaluate deployment-signal specs on the EUR ESE frame, honestly.

Mechanics identical to the repo's established harness: 1000 EUR arrives on the
first bar of each month, waits in the reserve, and deploys entirely the day
the signal fires (or after a 63-bar time-stop). Features use data through the
previous close; fills at the current Euronext open. Fee: 0.50% per trade
(the user's actual all-in cost), no other frictions.

Controls: ``now`` (deploy on arrival — the structural null every signal must
beat) and ``dca26`` (buy on/after day 26).

IS: 1989-09 -> 2013-09-15 (synthetic backfill era)
OOS: 2013-09-16 -> now (the real fund's lifetime)

Spec format (JSON list)::

    [{"name": "...", "conds": [{"feature": "...", "op": ">", "thr": 0.9}, ...],
      "base_deploy": 0.0}]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from features import build_features

BUDGET = 1000.0
MAX_HOLD = 63
FEE = 0.005
IS_END = "2013-09-15"


def fired_mask(spec: dict, feats: dict[str, np.ndarray], n: int) -> np.ndarray:
    out = np.ones(n, dtype=bool)
    for cond in spec["conds"]:
        x = feats[cond["feature"]]
        thr = float(cond["thr"])
        ok = x > thr if cond["op"] == ">" else x < thr
        out &= np.where(np.isfinite(x), ok, False)
    return out


def simulate(asset: pd.DataFrame, fired: np.ndarray, base_deploy: float,
             seg: slice, fee: float = FEE, max_hold: int = MAX_HOLD) -> dict:
    dates = asset.index[seg]
    op = asset["open"].to_numpy(dtype=float)[seg]
    cl = asset["close"].to_numpy(dtype=float)[seg]
    fr = fired[seg]
    month = dates.to_period("M")
    is_deposit = np.r_[True, month[1:] != month[:-1]]
    cash = shares = 0.0
    waiting = orders = 0
    for i in range(len(dates)):
        if is_deposit[i]:
            cash += BUDGET
            if base_deploy > 0:
                spend = BUDGET * base_deploy
                shares += spend * (1 - fee) / op[i]
                cash -= spend
                orders += 1
        if cash > 1.0:
            waiting += 1
            if fr[i] or waiting >= max_hold:
                shares += cash * (1 - fee) / op[i]
                cash = 0.0
                orders += 1
                waiting = 0
        else:
            waiting = 0
    return {"final": round(shares * cl[-1] + cash, 0), "orders": orders}


def evaluate(specs: list[dict], fee: float = FEE) -> list[dict]:
    asset, feats = build_features()
    n = len(asset)
    cut = asset.index.searchsorted(pd.Timestamp(IS_END), side="right")
    segs = {"is": slice(0, cut), "oos": slice(cut, n)}
    day26 = np.asarray(asset.index.day >= 26)
    out = []
    for name, arr, base in [("now", np.ones(n, bool), 0.0), ("dca26", day26, 0.0)]:
        out.append({"name": f"CONTROL_{name}", "conds": [],
                    **{s: simulate(asset, arr, base, sl, fee) for s, sl in segs.items()}})
    ref = {s: out[0][s]["final"] for s in segs}
    for spec in specs:
        fired = fired_mask(spec, feats, n) if spec["conds"] else np.zeros(n, bool)
        row = {"name": spec["name"], "conds": spec["conds"],
               "base_deploy": spec.get("base_deploy", 0.0),
               **{s: simulate(asset, fired, spec.get("base_deploy", 0.0), sl, fee,
                              int(spec.get("max_hold", MAX_HOLD)))
                  for s, sl in segs.items()}}
        for s in segs:
            row[s]["vs_now"] = round(row[s]["final"] / ref[s] - 1, 5)
        out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--fee", type=float, default=FEE)
    ap.add_argument("--features", action="store_true")
    args = ap.parse_args()
    if args.features:
        _, feats = build_features()
        print("\n".join(sorted(feats)))
        return
    specs = json.loads(Path(args.specs).read_text())
    results = evaluate(specs, fee=args.fee)
    payload = json.dumps(results, indent=1)
    if args.out:
        Path(args.out).write_text(payload)
        print(f"wrote {args.out} ({len(results)} rows)")
    else:
        print(payload)
if __name__ == "__main__":
    main()
