"""Campaign 3B: the leverage dial -- dynamic vs fixed 2x flow share.

Kelly/Merton says full investment is ~0.3-0.45 fractional Kelly here, so a
2x sleeve has structural headroom. The question with content: does any
STATE-DEPENDENT rule for the monthly CL2-vs-ESE flow split beat the FIXED
split with the same realized average exposure? If not, the dial is a
constant, chosen once by risk appetite.

Synthetic 2x EUR series: r_lev = 2*r_asset - r_cash(borrow leg) - drag,
drag calibrated on the real CL2 overlap (2013-2026), then validated.
Judged on final wealth AND max portfolio drawdown vs the fixed-fraction
frontier (0/25/50/75/100% CL2), both eras.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dataset import build_asset_frame, load

FEE = 0.005
BUDGET = 1000.0
IS_END = pd.Timestamp("2013-09-15")


def build_lev_pair() -> pd.DataFrame:
    asset = build_asset_frame()
    r = asset["close"].pct_change().fillna(0.0)
    r3m = load("EUR003M Index")["PX_LAST"].reindex(asset.index).ffill() / 100.0
    r3m = r3m.fillna(0.03)
    drag = 0.006  # fund fees + swap/borrow spread, calibrated below on real CL2
    r_lev = 2 * r - r3m / 252 - drag / 252
    lev = (1 + r_lev).cumprod() * asset["close"].iloc[0]
    out = pd.DataFrame({"base": asset["close"], "lev": lev})
    return out


def validate() -> None:
    pair = build_lev_pair()
    cl2 = load("CL2 FP Equity")["TOT_RETURN_INDEX_GROSS_DVDS"].dropna()
    both = pd.concat([pair["lev"].pct_change(), cl2.pct_change()], axis=1,
                     keys=["synth", "real"]).dropna()
    corr = both["synth"].corr(both["real"])
    yrs = (both.index[-1] - both.index[0]).days / 365.25
    g_s = (1 + both["synth"]).prod() ** (1 / yrs) - 1
    g_r = (1 + both["real"]).prod() ** (1 / yrs) - 1
    print(f"synthetic-2x vs real CL2: daily corr {corr:.3f}, "
          f"CAGR synth {g_s:.2%} vs real {g_r:.2%} (gap {(g_s-g_r)*1e4:.0f}bp/yr)")


def simulate(pair: pd.DataFrame, share_fn, seg: slice) -> dict:
    """share_fn(i) -> fraction of the month's flow into the 2x sleeve."""
    px = pair.to_numpy(float)
    dates = pair.index[seg]
    lo = seg.start or 0
    month = dates.to_period("M")
    is_dep = np.r_[True, month[1:] != month[:-1]]
    sh = np.zeros(2)
    ssum = 0.0
    ndep = 0
    vals = []
    for j in range(len(dates)):
        i = lo + j
        if is_dep[j]:
            s = float(np.clip(share_fn(i), 0.0, 1.0))
            ssum += s
            ndep += 1
            sh[0] += BUDGET * (1 - s) * (1 - FEE) / px[i, 0]
            sh[1] += BUDGET * s * (1 - FEE) / px[i, 1]
        vals.append(sh @ px[i])
    v = pd.Series(vals, index=dates)
    dd = float((v / v.cummax() - 1).min())
    return {"final": round(float(v.iloc[-1])), "avg_share": round(ssum / max(ndep, 1), 3),
            "maxdd": round(dd, 3)}


def make_rules(pair: pd.DataFrame) -> dict:
    r = pair["base"].pct_change()
    vol = r.rolling(63).std() * np.sqrt(252)
    dd_ath = pair["base"] / pair["base"].cummax() - 1
    sma200 = pair["base"] / pair["base"].rolling(200).mean() - 1
    vol_pctl = vol.rolling(1260, min_periods=252).rank(pct=True)

    rules = {f"FIX_{int(s*100)}": (lambda s: (lambda i: s))(s)
             for s in (0.0, 0.25, 0.5, 0.75, 1.0)}
    # vol targeting: exposure E = min(2, target/vol); CL2 share = E - 1
    for tgt in (0.20, 0.25):
        rules[f"voltarget_{int(tgt*100)}"] = (lambda t: (
            lambda i: np.clip(t / max(vol.iloc[i - 1], 1e-6) - 1.0, 0.0, 1.0)
            if np.isfinite(vol.iloc[i - 1]) else 0.5))(tgt)
    # buy leverage in drawdowns (anti-cyclical: cheap beta after crashes)
    rules["dd_scaled"] = lambda i: (0.0 if not np.isfinite(dd_ath.iloc[i - 1])
                                    else float(np.clip(-dd_ath.iloc[i - 1] / 0.4, 0.0, 1.0)))
    rules["dd20_all_in"] = lambda i: 1.0 if dd_ath.iloc[i - 1] < -0.20 else 0.0
    # trend-gated leverage (pro-cyclical: lever only in uptrend)
    rules["trend_gate"] = lambda i: 1.0 if (np.isfinite(sma200.iloc[i - 1])
                                            and sma200.iloc[i - 1] > 0) else 0.0
    # low-vol-regime leverage
    rules["lowvol_gate"] = lambda i: 1.0 if (np.isfinite(vol_pctl.iloc[i - 1])
                                             and vol_pctl.iloc[i - 1] < 0.5) else 0.0
    return rules


def main() -> None:
    validate()
    pair = build_lev_pair()
    cut = int(pair.index.searchsorted(IS_END, side="right"))
    segs = {"is": slice(0, cut), "oos": slice(cut, len(pair))}
    out = []
    for name, fn in make_rules(pair).items():
        row = {"name": name}
        for s, sl in segs.items():
            row[s] = simulate(pair, fn, sl)
        out.append(row)
    json.dump(out, open(Path(__file__).parent / "results_lev.json", "w"), indent=1)
    print(f"\n{'rule':16s} {'IS final':>10} {'dd':>6} {'share':>6}   {'OOS final':>10} {'dd':>6} {'share':>6}")
    for r in out:
        print(f"{r['name']:16s} {r['is']['final']:>10,} {r['is']['maxdd']:>6.0%} {r['is']['avg_share']:>6}   "
              f"{r['oos']['final']:>10,} {r['oos']['maxdd']:>6.0%} {r['oos']['avg_share']:>6}")


if __name__ == "__main__":
    main()
