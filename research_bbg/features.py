"""Point-in-time feature library over the full Bloomberg universe.

Every feature is computed on data through the PREVIOUS close and aligned to
the asset frame's calendar (Euronext). Uniform shift(1) is applied at the end:
at the Euronext open of day t, US closes of t-1 (which happen after the
Euronext close of t-1) are legitimately known — no look-ahead.

Weekly/lagged series (AAII, NFCI) get extra publication lag on top.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataset import build_asset_frame, load

WIN_PCTL = 1260  # 5y rolling percentile window


def _pctl(s: pd.Series) -> pd.Series:
    return s.rolling(WIN_PCTL, min_periods=252).rank(pct=True)


def _al(s: pd.Series, idx: pd.DatetimeIndex, extra_lag: int = 0) -> pd.Series:
    out = s.reindex(idx.union(s.index)).ffill().reindex(idx)
    return out.shift(extra_lag) if extra_lag else out


def build_features() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    asset = build_asset_frame()
    idx = asset.index
    c = asset["close"]
    rets = c.pct_change()
    f: dict[str, pd.Series] = {}

    # ---- price/trend on the EUR asset ----
    for n in (5, 21, 63, 126, 252):
        f[f"ret_{n}"] = c.pct_change(n)
    for n in (20, 50, 100, 200):
        f[f"sma_ratio_{n}"] = c / c.rolling(n).mean() - 1
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14).mean()
    f["rsi_14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    for n in (21, 63):
        f[f"rvol_{n}"] = rets.rolling(n).std() * np.sqrt(252)
    f["rvol_pctl"] = _pctl(f["rvol_21"])
    for n in (63, 252):
        f[f"dd_{n}"] = c / c.rolling(n).max() - 1
    f["dd_ath"] = c / c.cummax() - 1
    f["down_streak"] = (rets < 0).astype(int).groupby((rets >= 0).cumsum()).cumsum().astype(float)
    f["ret_1"] = rets

    # ---- USD leg & FX ----
    spx = load("SPX Index")
    spx_c = _al(spx["PX_LAST"], idx)
    f["spx_ret_21"] = spx_c.pct_change(21)
    f["spx_dd_252"] = spx_c / spx_c.rolling(252).max() - 1
    fx = _al(load("EURUSD Curncy")["PX_LAST"], idx)
    f["fx_ret_21"] = fx.pct_change(21)
    f["fx_ret_63"] = fx.pct_change(63)
    f["fx_pctl"] = _pctl(fx)
    f["fx_vol1m"] = _al(load("EURUSDV1M Curncy")["PX_LAST"], idx)
    f["fx_rr25"] = _al(load("EURUSD25R1M Curncy")["PX_LAST"], idx)
    f["dxy_ret_63"] = _al(load("DXY Curncy")["PX_LAST"], idx).pct_change(63)
    # overnight decomposition: US close move not yet in the Euronext close
    ese_ret_usd = (c * 0 + rets) + fx.pct_change()  # asset ret in USD approx
    f["us_after_eu_close"] = spx_c.pct_change() - ese_ret_usd  # yesterday's late-US move

    # ---- volatility complex ----
    vix = _al(load("VIX Index")["PX_LAST"], idx)
    f["vix"] = vix
    f["vix_pctl"] = _pctl(vix)
    f["vix_chg_5"] = vix.diff(5)
    f["vix_chg_21"] = vix.diff(21)
    vix3m = _al(load("VIX3M Index")["PX_LAST"], idx)
    f["vix_ts"] = vix / vix3m - 1  # backwardation > 0
    ux1 = _al(load("UX1 Index")["PX_LAST"], idx)
    ux2 = _al(load("UX2 Index")["PX_LAST"], idx)
    f["ux_roll"] = ux1 / ux2 - 1  # real futures curve inversion
    f["vix_basis"] = vix / ux1 - 1  # spot vs front future
    f["vvix"] = _al(load("VVIX Index")["PX_LAST"], idx)
    v2x = _al(load("V2X Index")["PX_LAST"], idx)
    f["v2x_vix"] = v2x - vix  # EU fear premium
    move = _al(load("MOVE Index")["PX_LAST"], idx)
    f["move_pctl"] = _pctl(move)
    f["skew"] = _al(load("SKEW Index")["PX_LAST"], idx)

    # ---- rates & credit ----
    g3m = _al(load("USGG3M Index")["PX_LAST"], idx)
    g2 = _al(load("USGG2YR Index")["PX_LAST"], idx)
    g10 = _al(load("USGG10YR Index")["PX_LAST"], idx)
    f["curve_10y3m"] = g10 - g3m
    f["curve_2s10s"] = g10 - g2
    f["rate_chg_63"] = g10.diff(63)
    de10 = _al(load("GTDEM10Y Govt")["PX_LAST"], idx)
    f["us_de_10y"] = g10 - de10
    hy = _al(load("LF98OAS Index")["PX_LAST"], idx)
    ig = _al(load("LUACOAS Index")["PX_LAST"], idx)
    f["hy_oas"] = hy
    f["hy_oas_pctl"] = _pctl(hy)
    f["hy_oas_chg_21"] = hy.diff(21)
    f["hy_ig"] = hy - ig
    f["hy_ig_pctl"] = _pctl(hy - ig)
    f["cdx_hy"] = _al(load("CDX HY CDSI GEN 5Y SPRD Corp")["PX_LAST"], idx)

    # ---- sentiment / breadth / macro ----
    f["aaii_bull"] = _al(load("AAIIBULL Index")["PX_LAST"], idx, extra_lag=1)
    f["aaii_bear"] = _al(load("AAIIBEAR Index")["PX_LAST"], idx, extra_lag=1)
    f["aaii_spread"] = f["aaii_bull"] - f["aaii_bear"]
    f["putcall"] = _al(load("PCUSEQTR Index")["PX_LAST"], idx)
    f["putcall_pctl"] = _pctl(f["putcall"])
    adln = _al(load("ADLN Index")["PX_LAST"], idx)
    f["adln_dev_126"] = (adln - adln.rolling(126).mean()) / adln.rolling(126).std()
    f["nfci"] = _al(load("NFCIINDX Index")["PX_LAST"], idx, extra_lag=3)
    f["cesi_usd"] = _al(load("CESIUSD Index")["PX_LAST"], idx)
    f["cesi_eur"] = _al(load("CESIEUR Index")["PX_LAST"], idx)

    # ---- cross-asset ----
    gold = _al(load("XAU Curncy")["PX_LAST"], idx)
    copper = _al(load("HG1 Comdty")["PX_LAST"], idx)
    oil = _al(load("CL1 Comdty")["PX_LAST"], idx)
    f["gold_ret_63"] = gold.pct_change(63)
    f["copper_gold"] = (copper / gold).pct_change(63)
    f["oil_ret_63"] = oil.pct_change(63)
    es1 = _al(load("ES1 Index")["PX_LAST"], idx)
    f["es_basis"] = es1 / spx_c - 1

    # ---- calendar ----
    f["day_of_month"] = pd.Series(idx.day.astype(float), index=idx)
    f["month"] = pd.Series(idx.month.astype(float), index=idx)
    tdom = pd.Series(np.arange(len(idx)), index=idx)
    mstart = tdom.groupby(idx.to_period("M")).transform("min")
    f["tday_of_month"] = (tdom - mstart).astype(float)

    feats = {k: s.shift(1).to_numpy(dtype=float) for k, s in f.items()}
    return asset, feats


if __name__ == "__main__":
    asset, feats = build_features()
    cov = {k: int(np.isfinite(v).sum()) for k, v in feats.items()}
    for k in sorted(cov):
        print(f"{k:20s} {cov[k]:6d} bars")
    print(f"\n{len(feats)} features, asset {len(asset)} bars")
