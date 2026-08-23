"""Execution study: when during the Euronext day is ESE cheapest to buy?

Uses the pulled intraday bars (trade/bid/ask). Everything here is about
CERTAIN costs (spread, liquidity) and systematic intraday price patterns —
the branch of the program where edges are real because they are paid, not
predicted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "data_bbg" / "intraday_ese.parquet"


def main() -> None:
    df = pd.read_parquet(SRC)
    df.index = pd.DatetimeIndex(df.index)
    df["mid"] = (df["bid_close"] + df["ask_close"]) / 2
    df["spread_bp"] = (df["ask_close"] - df["bid_close"]) / df["mid"] * 1e4
    df["date"] = df.index.date
    df["hour"] = df.index.hour + df.index.minute / 60

    # normalize each day: price relative to the day's VWAP
    vwap = (df["trd_close"] * df["trd_volume"]).groupby(df["date"]).transform("sum") / \
           df.groupby("date")["trd_volume"].transform("sum")
    df["rel_vwap_bp"] = (df["trd_close"] / vwap - 1) * 1e4

    buckets = pd.cut(df["hour"], bins=np.arange(9.0, 17.75, 0.5))
    g = df.groupby(buckets, observed=True)
    out = pd.DataFrame({
        "med_spread_bp": g["spread_bp"].median(),
        "p90_spread_bp": g["spread_bp"].quantile(0.9),
        "vol_share_%": g["trd_volume"].sum() / df["trd_volume"].sum() * 100,
        "avg_rel_vwap_bp": g["rel_vwap_bp"].mean(),
        "se_rel_vwap_bp": g["rel_vwap_bp"].std() / np.sqrt(g["date"].nunique()),
    }).round(2)
    print(f"{df['date'].nunique()} days, {len(df)} bars, "
          f"{df.index.min()} -> {df.index.max()}\n")
    print(out.to_string())


if __name__ == "__main__":
    main()
