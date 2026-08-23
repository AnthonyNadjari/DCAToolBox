"""Pull the full daily universe from Bloomberg into local parquet caches.

Usage::

    python research_bbg/pull.py            # pull everything missing
    python research_bbg/pull.py --refresh  # re-pull everything

One parquet per ticker under ``data_bbg/daily/``. A manifest of pull results is
written to ``data_bbg/pull_log.json``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from xbbg import blp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from universe import DAILY_UNIVERSE  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data_bbg" / "daily"
END = date.today().isoformat()


def safe_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", ticker).strip("_")


def pull_one(ticker: str, fields: list[str], start: str) -> dict:
    df = blp.bdh(ticker, fields, start, END)
    if df.empty:
        return {"ticker": ticker, "rows": 0, "error": "empty"}
    df.columns = [c[1] for c in df.columns]  # drop ticker level
    df.index.name = "date"
    path = OUT / f"{safe_name(ticker)}.parquet"
    df.to_parquet(path)
    return {
        "ticker": ticker,
        "rows": len(df),
        "first": str(df.index[0])[:10],
        "last": str(df.index[-1])[:10],
        "fields": list(df.columns),
        "file": path.name,
    }


def main() -> None:
    refresh = "--refresh" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    for ticker, (fields, start) in DAILY_UNIVERSE.items():
        path = OUT / f"{safe_name(ticker)}.parquet"
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
    (OUT.parent / "pull_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
