"""Campaign-2 feature extension: BASK-sourced Bloomberg-exclusive families.

Adds to the base library: CFTC positioning, NAAIM, implied correlation,
SPY short interest, ETF flows, index earnings revisions/valuation, and the
FOMC calendar (days-to/since announcement, Cieslak even-week cycle).
Publication lags applied conservatively on top of the uniform shift(1):
CFTC +3d (Friday release for Tuesday data), NAAIM +1d, short interest +7d.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dataset import DATA, load
from features import WIN_PCTL, _al, _pctl, build_features


def build_features2() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    asset, feats = build_features()
    idx = asset.index
    f: dict[str, pd.Series] = {}

    # --- CFTC net non-commercial e-mini positioning (weekly) ---
    imm = _al(load("IMM0ENCN Index")["PX_LAST"], idx, extra_lag=3)
    f["cftc_net"] = imm
    f["cftc_pctl"] = _pctl(imm)
    f["cftc_z_1y"] = (imm - imm.rolling(252).mean()) / imm.rolling(252).std()

    # --- NAAIM manager exposure (weekly) ---
    naaim = _al(load("NAAIMEXP Index")["PX_LAST"], idx, extra_lag=1)
    f["naaim"] = naaim
    f["naaim_pctl"] = _pctl(naaim)

    # --- implied correlation: JCJ (2007-2021) spliced with COR1M (2010->) ---
    jcj = load("JCJ Index")["PX_LAST"]
    cor = load("COR1M Index")["PX_LAST"]
    icorr = pd.concat([jcj[jcj.index < cor.index.min()], cor]).sort_index()
    ic = _al(icorr, idx)
    f["impl_corr"] = ic
    f["impl_corr_pctl"] = _pctl(ic)
    f["impl_corr_chg_21"] = ic.diff(21)

    # --- SPY short interest ratio (bi-monthly, ~9d publication lag) ---
    si = _al(load("SPY_SHORT_INT")["SHORT_INT_RATIO"], idx, extra_lag=7)
    f["si_ratio"] = si
    f["si_pctl"] = _pctl(si)

    # --- ETF primary-market flows ---
    flow = load("SPY_FLOW")["FUND_FLOW"].fillna(0.0)
    scale = flow.abs().rolling(252, min_periods=63).mean()
    fz = (flow.rolling(21).sum() / (scale * 21)).clip(-5, 5)
    f["spy_flow_21"] = _al(fz, idx)
    f["spy_flow_pctl"] = _pctl(f["spy_flow_21"])

    # --- index earnings revisions & valuation ---
    eps = _al(load("SPX_BEST_EPS")["BEST_EPS"], idx)
    f["eps_rev_21"] = eps.pct_change(21)
    f["eps_rev_63"] = eps.pct_change(63)
    ey = _al(load("SPX_EARN_YLD")["EARN_YLD"], idx)
    g10 = _al(load("USGG10YR Index")["PX_LAST"], idx)
    f["earn_yld"] = ey
    f["fed_model"] = ey - g10
    f["fed_model_pctl"] = _pctl(ey - g10)

    # --- FOMC calendar ---
    fomc_path = DATA.parent / "fomc_dates.csv"
    if fomc_path.exists():
        cal = pd.read_csv(fomc_path, parse_dates=["date"])
        days = pd.DatetimeIndex(cal.loc[cal["type"] == "scheduled", "date"]).sort_values()
        pos = np.searchsorted(days.values, idx.values, side="left")
        nxt = days.values[np.minimum(pos, len(days) - 1)]
        prv = days.values[np.maximum(pos - 1, 0)]
        to_next = (nxt - idx.values).astype("timedelta64[D]").astype(float)
        since = (idx.values - prv).astype("timedelta64[D]").astype(float)
        f["days_to_fomc"] = pd.Series(to_next, index=idx)
        f["days_since_fomc"] = pd.Series(since, index=idx)
        f["fomc_even_week"] = pd.Series(((since // 7) % 2 == 0).astype(float), index=idx)


    # --- short-horizon / calendar mechanics (practitioner rules) ---
    c = asset["close"]
    delta2 = c.diff()
    g2 = delta2.clip(lower=0).ewm(alpha=1 / 2, min_periods=2).mean()
    l2 = (-delta2.clip(upper=0)).ewm(alpha=1 / 2, min_periods=2).mean()
    f["rsi_2"] = 100 - 100 / (1 + g2 / l2.replace(0, np.nan))
    tpos = pd.Series(np.arange(len(idx)), index=idx)
    mend = tpos.groupby(idx.to_period("M")).transform("max")
    f["tdays_to_month_end"] = (mend - tpos).astype(float)
    # third Friday of month = OpEx; flag OpEx week (Mon-Fri containing it) and week after
    third_fri = {}
    for per, sub in pd.Series(idx, index=idx).groupby(idx.to_period("M")):
        fridays = [d for d in sub if d.weekday() == 4]
        cal_fri = pd.date_range(per.start_time, per.end_time, freq="W-FRI")
        tf = cal_fri[2] if len(cal_fri) >= 3 else None
        third_fri[per] = tf
    tf_ser = pd.Series([third_fri[p] for p in idx.to_period("M")], index=idx)
    delta_tf = (tf_ser - pd.Series(idx, index=idx)).dt.days
    f["days_to_opex"] = delta_tf.astype(float)          # >0 before, <0 after
    f["opex_week"] = ((delta_tf >= 0) & (delta_tf <= 4)).astype(float)
    f["post_opex_week"] = ((delta_tf < 0) & (delta_tf >= -7)).astype(float)


    # --- NFP calendar (first Friday of month) and vol-crush state ---
    nfp_map = {}
    for per in sorted(set(idx.to_period("M"))):
        fridays = pd.date_range(per.start_time, per.end_time, freq="W-FRI")
        nfp_map[per] = fridays[0]
    nfp_ser = pd.Series([nfp_map[p] for p in idx.to_period("M")], index=idx)
    nxt_map = {per: nfp_map.get(per + 1) for per in nfp_map}
    dtn = (nfp_ser - pd.Series(idx, index=idx)).dt.days.astype(float)
    nxt_ser = pd.Series([nxt_map[p] for p in idx.to_period("M")], index=idx)
    dtn2 = (nxt_ser - pd.Series(idx, index=idx)).dt.days.astype(float)
    f["days_to_nfp"] = dtn.where(dtn >= 0, dtn2)     # calendar days to next NFP
    vixs = _al(load("VIX Index")["PX_LAST"], idx)
    f["vix_peak_63"] = vixs.rolling(63).max()
    f["vix_now"] = vixs


    # --- campaign 2b: VRP, MOVE-VIX divergence, speculation sentiment ---
    spx_ret = _al(load("SPX Index")["PX_LAST"], idx).pct_change()
    rv22 = (spx_ret ** 2).rolling(22).sum() * (100 ** 2)   # monthly %^2 units approx
    iv = vixs ** 2 / 12
    vrp = iv - rv22
    f["vrp"] = vrp
    f["vrp_q_3y"] = vrp.rolling(756, min_periods=252).rank(pct=True)
    move2 = _al(load("MOVE Index")["PX_LAST"], idx)
    zm = (move2 - move2.rolling(252).mean()) / move2.rolling(252).std()
    zv = (vixs - vixs.rolling(252).mean()) / vixs.rolling(252).std()
    f["move_vix_div"] = zm - zv
    lev = None
    for t, sign in [("SSO_FLOW", 1), ("UPRO_FLOW", 1), ("SDS_FLOW", -1), ("SPXU_FLOW", -1)]:
        try:
            fl = load(t)["FUND_FLOW"].fillna(0.0) * sign
            lev = fl if lev is None else lev.add(fl, fill_value=0.0)
        except FileNotFoundError:
            pass
    if lev is not None:
        sc = lev.abs().rolling(252, min_periods=63).mean()
        f["spec_sent"] = _al((lev.rolling(21).sum() / (sc * 21)).clip(-5, 5), idx)

    extra = {k: s.shift(1).to_numpy(dtype=float) for k, s in f.items()}
    feats.update(extra)
    return asset, feats


if __name__ == "__main__":
    asset, feats = build_features2()
    base = 64
    newk = [k for k in feats if k in (
        "cftc_net","cftc_pctl","cftc_z_1y","naaim","naaim_pctl","impl_corr",
        "impl_corr_pctl","impl_corr_chg_21","si_ratio","si_pctl","spy_flow_21",
        "spy_flow_pctl","eps_rev_21","eps_rev_63","earn_yld","fed_model",
        "fed_model_pctl","days_to_fomc","days_since_fomc","fomc_even_week")]
    for k in sorted(newk):
        x = feats[k]
        print(f"{k:20s} {int(np.isfinite(x).sum()):6d} bars")
    print(f"\ntotal {len(feats)} features")
