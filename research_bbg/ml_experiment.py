"""Walk-forward machine-learning experiment (pre-registered design).

Setup, fixed before any result was seen:
- Features: the full 90+ feature library (already point-in-time lagged).
- Target: forward 21-day return of the EUR asset.
- Models: (a) Ridge regression (median-imputed, standardized),
          (b) HistGradientBoostingRegressor (native NaN handling),
          (c) Logistic classification on the sign of the target.
- Protocol: expanding-window walk-forward. First fit after 2,520 bars (~10y).
  Refit every 252 bars. A 21-bar purge separates each training window from
  its prediction block (the target overlaps 21 days forward).
- Deployment mapping (fixed a priori): the reserve deploys on days where the
  model's prediction is positive (regression) or p>0.5 (classification),
  with the standard 63-bar time-stop; a stricter top-quartile variant
  (prediction above its trailing-1y 75th percentile, cap 21) is also run.
- Judgment: same simulator, same null (deploy on arrival), fee 0.5%.
  Results reported separately for the backfill era (pre 2013-09-16) and the
  real-fund era. Every prediction is out-of-sample by construction; the
  design itself was NOT tuned (one shot, all variants reported).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab  # noqa: E402
from features2 import build_features2  # noqa: E402

FWD = 21
FIRST_FIT = 2520
REFIT = 252
PURGE = 21


def walk_forward_predictions() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    asset, feats = build_features2()
    names = sorted(feats)
    X = np.column_stack([feats[k] for k in names])
    close = asset["close"].to_numpy(dtype=float)
    y = np.full(len(close), np.nan)
    y[:-FWD] = close[FWD:] / close[:-FWD] - 1
    n = len(close)

    preds = {m: np.full(n, np.nan) for m in ("ridge", "gbm", "logit")}
    for start in range(FIRST_FIT, n, REFIT):
        tr_end = start - PURGE
        tr = slice(0, tr_end)
        te = slice(start, min(start + REFIT, n))
        ytr = y[tr]
        ok = np.isfinite(ytr) & (np.isfinite(X[tr]).sum(axis=1) > 20)
        Xtr, ytr2 = X[tr][ok], ytr[ok]
        if len(ytr2) < 500:
            continue
        ridge = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0))
        ridge.fit(Xtr, ytr2)
        preds["ridge"][te] = ridge.predict(X[te])
        gbm = HistGradientBoostingRegressor(
            max_iter=200, max_depth=3, learning_rate=0.05, random_state=0
        )
        gbm.fit(Xtr, ytr2)
        preds["gbm"][te] = gbm.predict(X[te])
        logit = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.1, max_iter=1000),
        )
        logit.fit(Xtr, (ytr2 > 0).astype(int))
        preds["logit"][te] = logit.predict_proba(X[te])[:, 1]
    return asset, {"y": y, **preds}


def main() -> None:
    asset, p = walk_forward_predictions()
    n = len(asset)
    y = p["y"]
    cut = asset.index.searchsorted(pd.Timestamp(lab.IS_END), side="right")
    segs = {"backfill_era": slice(0, cut), "real_fund_era": slice(cut, n)}
    ref = {s: lab.simulate(asset, np.ones(n, bool), 0.0, sl)["final"] for s, sl in segs.items()}

    out = []
    for m in ("ridge", "gbm", "logit"):
        pr = p[m]
        ok = np.isfinite(pr) & np.isfinite(y)
        oos_r2 = (
            1 - np.nansum((y[ok] - pr[ok]) ** 2) / np.nansum((y[ok] - np.nanmean(y[ok])) ** 2)
            if m != "logit"
            else float("nan")
        )
        thr_pos = 0.0 if m != "logit" else 0.5
        rules = {
            f"{m}_pos": (np.where(np.isfinite(pr), pr > thr_pos, False), 63),
        }
        q = pd.Series(pr).rolling(252, min_periods=126).quantile(0.75).to_numpy()
        rules[f"{m}_topq_cap21"] = (np.where(np.isfinite(pr) & np.isfinite(q), pr > q, False), 21)
        for rname, (fired, cap) in rules.items():
            row = {
                "name": rname,
                "oos_r2": round(float(oos_r2), 5) if np.isfinite(oos_r2) else None,
            }
            for s, sl in segs.items():
                r = lab.simulate(asset, fired, 0.0, sl, max_hold=cap)
                r["vs_now"] = round(r["final"] / ref[s] - 1, 5)
                row[s] = r
            out.append(row)
            print(
                f"{rname:20s} R2 {row['oos_r2']}  backfill {row['backfill_era']['vs_now']:+.4f}  "
                f"realfund {row['real_fund_era']['vs_now']:+.4f}"
            )
    json.dump(
        out, open(Path(__file__).parent.parent / "research_bbg" / "results_ml.json", "w"), indent=1
    )


if __name__ == "__main__":
    main()
