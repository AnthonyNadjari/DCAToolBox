"""Pull the Block B options/VRP universe — the one branch of the Bloomberg
data request (docs/BLOOMBERG_DATA_REQUEST.md) that was never pulled or tested.

Requires the terminal logged in. Usage::

    python research_bbg/pull_options.py            # pull everything missing
    python research_bbg/pull_options.py --refresh  # re-pull everything

One parquet per series under ``data_bbg/daily/`` (same cache dir as pull.py,
same naming). The IV-surface fields are point-in-time fitted vols on SPX Index.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from xbbg import blp

OUT = Path(__file__).resolve().parents[1] / "data_bbg" / "daily"
END = date.today().isoformat()

LAST = ["PX_LAST"]

#: ticker -> (fields, start date)
OPTIONS_UNIVERSE: dict[str, tuple[list[str], str]] = {
    # --- Cboe strategy benchmark indices (ground truth for the VRP harvest) ---
    "PUT Index": (LAST, "1986-01-01"),  # cash-secured ATM put write
    "BXM Index": (LAST, "1986-01-01"),  # covered call, ATM
    "BXY Index": (LAST, "1986-01-01"),  # covered call, 2% OTM
    "BXD Index": (LAST, "1986-01-01"),  # covered call, OTM (older variant)
    "BXMD Index": (LAST, "1986-01-01"),  # covered call on dow? resolve on terminal
    "CMBO Index": (LAST, "2006-01-01"),  # covered combo
    "WPUT Index": (LAST, "2006-01-01"),  # weekly put write
    "PPUT Index": (LAST, "1986-01-01"),  # protective put (5% OTM)
    "CLL Index": (LAST, "1986-01-01"),  # collar
    # --- Cboe VIX futures premium strategies ---
    "VPD Index": (LAST, "2006-01-01"),  # capped VIX premium (short mid-curve)
    "VPN Index": (LAST, "2006-01-01"),
    # --- S&P VIX short-term futures indices (roll-yield measurement) ---
    "SPVXSP Index": (LAST, "2005-01-01"),  # pre-2009 is backfill
    "SPVXSTR Index": (LAST, "2005-01-01"),
    # --- extended vol family ---
    "VIX9D Index": (LAST, "1990-01-01"),
    "VIX6M Index": (LAST, "2002-01-01"),
    "VXN Index": (LAST, "2001-01-01"),
    "UX4 Index": (LAST, "2004-01-01"),
    # --- SPX fitted IV surface (synthetic option pricing input) ---
    "SPX Index": (
        [
            "30DAY_IMPVOL_100.0%MNY_DF",
            "30DAY_IMPVOL_95.0%MNY_DF",
            "30DAY_IMPVOL_90.0%MNY_DF",
            "EQY_DVD_YLD_12M",
        ],
        "1990-01-01",
    ),
    # --- collateral leg for put-write replication ---
    "USGG3M Index": (LAST, "1980-01-01"),
}


def safe_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", ticker).strip("_")


def out_name(ticker: str, fields: list[str]) -> str:
    """SPX gets a dedicated file here so the IV pull can't clobber the OHLC cache."""
    if ticker == "SPX Index":
        return "SPX_IVSURF"
    return safe_name(ticker)


def pull_one(ticker: str, fields: list[str], start: str, attempts: int = 4) -> dict:
    import time

    last = {"ticker": ticker, "rows": 0, "error": "empty"}
    for _ in range(attempts):
        try:
            df = blp.bdh(ticker, fields, start, END)
        except Exception as exc:  # noqa: BLE001
            last = {"ticker": ticker, "rows": 0, "error": str(exc)[:200]}
            time.sleep(3)
            continue
        if df.empty:
            time.sleep(3)
            continue
        df.columns = [c[1] for c in df.columns]  # drop ticker level
        df.index.name = "date"
        path = OUT / f"{out_name(ticker, fields)}.parquet"
        df.to_parquet(path)
        return {
            "ticker": ticker,
            "rows": len(df),
            "first": str(df.index[0])[:10],
            "last": str(df.index[-1])[:10],
            "file": path.name,
        }
    return last


def main() -> None:
    import json

    refresh = "--refresh" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    for ticker, (fields, start) in OPTIONS_UNIVERSE.items():
        import time

        time.sleep(0.75)  # politeness: throttling caused empty responses
        path = OUT / f"{out_name(ticker, fields)}.parquet"
        if path.exists() and not refresh:
            print(f"skip   {ticker}")
            continue
        try:
            info = pull_one(ticker, fields, start)
        except Exception as exc:  # noqa: BLE001
            info = {"ticker": ticker, "rows": 0, "error": str(exc)[:200]}
        log.append(info)
        print(
            f"{'PULLED' if info['rows'] else 'FAILED':6} {ticker}: "
            f"{info.get('rows')} rows {info.get('first', '')} -> {info.get('last', '')}"
        )
    (OUT.parent / "pull_log_options.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
