"""Pull all available ESE FP intraday bars (trade/bid/ask) from Bloomberg.

Bloomberg keeps roughly the last ~6 months of intraday bars. One parquet per
(day, type) is appended into data_bbg/intraday_ese.parquet. Used by the
execution study: spread, volume and relative premium by time of day.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from xbbg import blp

OUT = Path(__file__).resolve().parents[1] / "data_bbg" / "intraday_ese.parquet"
TICKER = "ESE FP Equity"


def main() -> None:
    days = pd.bdate_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1),
                          periods=130)
    frames = []
    for d in days:
        ds = d.strftime("%Y-%m-%d")
        day = {}
        for typ in ("TRADE", "BID", "ASK"):
            try:
                df = blp.bdib(TICKER, dt=ds, typ=typ)
            except Exception:
                continue
            if df.empty:
                continue
            df = df.droplevel(0, axis=1) if isinstance(df.columns, pd.MultiIndex) else df
            day[typ] = df
        if "TRADE" not in day:
            continue
        merged = day["TRADE"][["open", "high", "low", "close", "volume"]].copy()
        merged.columns = [f"trd_{c}" for c in merged.columns]
        for typ in ("BID", "ASK"):
            if typ in day:
                merged[f"{typ.lower()}_close"] = day[typ]["close"]
        frames.append(merged)
        print(ds, len(merged), "bars", flush=True)
    if not frames:
        raise SystemExit("no intraday data returned")
    allb = pd.concat(frames)
    allb.to_parquet(OUT)
    print(f"wrote {OUT}: {len(allb)} bars over {len(frames)} days")


if __name__ == "__main__":
    main()
