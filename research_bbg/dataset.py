"""Build the EUR-investor research frame from the pulled Bloomberg caches.

The tradable series is what a French investor actually buys: **ESE FP**
(BNP Paribas Easy S&P 500 UCITS, accumulating, EUR, Euronext). Real fund
prices are used from inception (2013-09-16). Before that the series is
backfilled with SPXT (S&P 500 total return, USD) converted to EUR at the
daily EURUSD close, with the fund's TER (0.15%/yr) subtracted so the
backfill is not flattered vs the real fund.

Frame columns: open/high/low/close in EUR (TR terms), plus volume.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data_bbg" / "daily"
ESE_INCEPTION = pd.Timestamp("2013-09-16")
TER = 0.0015  # ESE FP expense ratio, applied to the pre-inception backfill


def load(ticker: str) -> pd.DataFrame:
    name = re.sub(r"[^A-Za-z0-9]+", "_", ticker).strip("_")
    df = pd.read_parquet(DATA / f"{name}.parquet")
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index), name="date")
    return df


def build_asset_frame() -> pd.DataFrame:
    """EUR total-return OHLCV series for the tradable asset (ESE, backfilled)."""
    ese = load("ESE FP Equity")
    spxt = load("SPXT Index")["PX_LAST"]
    spx = load("SPX Index")
    fx = load("EURUSD Curncy")["PX_LAST"]  # USD per EUR

    # --- pre-inception synthetic leg: SPXT in EUR, TER-drag applied ---
    idx = spxt.index[spxt.index < ESE_INCEPTION]
    fx_al = fx.reindex(spxt.index).ffill()
    close_eur = (spxt / fx_al).loc[idx]
    yrs = (idx - idx[0]).days / 365.25
    close_eur = close_eur * (1 - TER) ** yrs
    # opens: apply the SPX open/prev-close gap, FX at previous close
    spx_al = spx.reindex(spxt.index).ffill()
    gap = (spx_al["PX_OPEN"] / spx_al["PX_LAST"].shift(1)).loc[idx]
    fx_gap = (fx_al / fx_al.shift(1)).loc[idx]
    open_eur = close_eur.shift(1) * gap / fx_gap
    pre = pd.DataFrame(
        {
            "open": open_eur,
            "high": np.maximum(open_eur, close_eur),
            "low": np.minimum(open_eur, close_eur),
            "close": close_eur,
            "volume": 0.0,
            "real": False,
        }
    ).dropna(subset=["open", "close"])

    # --- real fund leg, rescaled so the splice is continuous ---
    real = pd.DataFrame(
        {
            "open": ese["PX_OPEN"],
            "high": ese["PX_HIGH"],
            "low": ese["PX_LOW"],
            "close": ese["PX_LAST"],
            "volume": ese["PX_VOLUME"].fillna(0.0),
            "real": True,
        }
    ).dropna(subset=["close"])
    real[["open", "high", "low"]] = real[["open", "high", "low"]].ffill(axis=0)
    scale = pre["close"].iloc[-1] / real["close"].iloc[0]
    real[["open", "high", "low", "close"]] *= scale

    return pd.concat([pre, real])


def validate_splice() -> pd.DataFrame:
    """Compare the synthetic leg vs the real fund over the overlap (2013->now)."""
    ese = load("ESE FP Equity")["PX_LAST"].dropna()
    spxt = load("SPXT Index")["PX_LAST"]
    fx = load("EURUSD Curncy")["PX_LAST"].reindex(spxt.index).ffill()
    synth = (spxt / fx).reindex(ese.index).ffill()
    r_e, r_s = np.log(ese).diff().dropna(), np.log(synth).diff().dropna()
    both = pd.concat([r_e, r_s], axis=1, keys=["ese", "synth"]).dropna()
    corr = both["ese"].corr(both["synth"])
    yrs = (ese.index[-1] - ese.index[0]).days / 365.25
    cagr_e = (ese.iloc[-1] / ese.iloc[0]) ** (1 / yrs) - 1
    cagr_s = (synth.iloc[-1] / synth.iloc[0]) ** (1 / yrs) - 1
    te = (both["ese"] - both["synth"]).std() * np.sqrt(252)
    return pd.DataFrame(
        {
            "corr_daily": [corr],
            "cagr_real": [cagr_e],
            "cagr_synth": [cagr_s],
            "cagr_gap_bps": [(cagr_s - cagr_e) * 1e4],
            "tracking_err": [te],
        }
    )


if __name__ == "__main__":
    print(validate_splice().round(4).to_string(index=False))
    frame = build_asset_frame()
    print(frame.iloc[[0, 1, -2, -1]].round(2).to_string())
    print(
        f"{len(frame)} bars, {frame.index[0].date()} -> {frame.index[-1].date()}, "
        f"real from {frame.index[frame['real']].min().date()}"
    )
