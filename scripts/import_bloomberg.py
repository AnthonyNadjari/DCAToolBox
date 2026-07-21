"""Import Bloomberg exports into the research data format.

Lets a Bloomberg user re-run the ENTIRE research harness on their own data,
replacing the Yahoo series ticker by ticker. Export from a terminal with BDH
into Excel/CSV, one file per instrument, with columns:

    date, open, high, low, close[, volume]

IMPORTANT: use TOTAL-RETURN prices (``TOT_RETURN_INDEX_GROSS_DVDS`` or
``PX_LAST`` with ``DVD_ADJ``), not raw ``PX_LAST`` — accumulation strategies
compound dividends, and raw prices understate every DCA by ~2 CAGR points.

Usage::

    python scripts/import_bloomberg.py SPY my_export.csv
    # writes data_real/SPY.json; then re-run scripts/research.py normally
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def main() -> None:
    """Convert one Bloomberg CSV export to the data_real JSON format."""
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    ticker, src = sys.argv[1], Path(sys.argv[2])
    rows = []
    with src.open() as fh:
        for row in csv.DictReader(fh):
            keys = {k.lower().strip(): k for k in row}
            try:
                date = row[keys["date"]].strip()[:10]
                close = float(row[keys["close"]])
                o = float(row.get(keys.get("open", ""), close) or close)
                h = float(row.get(keys.get("high", ""), close) or close)
                lo = float(row.get(keys.get("low", ""), close) or close)
                v = float(row.get(keys.get("volume", ""), 0) or 0)
            except (KeyError, ValueError):
                continue
            rows.append((date, o, h, lo, close, v))
    rows.sort()
    if len(rows) < 100:
        raise SystemExit(f"only {len(rows)} usable rows parsed — check the export format")
    out = Path("data_real") / f"{ticker}.json"
    json.dump(
        {
            "ticker": ticker,
            "dates": [r[0] for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        },
        out.open("w"),
    )
    print(f"wrote {out} ({len(rows)} bars, {rows[0][0]} -> {rows[-1][0]})")


if __name__ == "__main__":
    main()
