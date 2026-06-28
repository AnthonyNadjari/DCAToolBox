"""Bundle market data as compact JSON for the in-browser backtester.

Reuses the framework's own data layer (:class:`DataService`) to fetch each
instrument, then writes one JSON file per ticker plus a manifest into
``site/data/``. In CI the Yahoo provider is used; if a download fails (offline,
rate limit) the deterministic synthetic provider is used as a fallback so the
page is never left without data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import DataConfig
from dcatoolbox.data.factory import DataService
from dcatoolbox.data.models import MarketData
from dcatoolbox.utils.logging import logger

OUT = Path("site/data")
START = date(2000, 1, 1)
# Always fetch up to "today" so every deploy refreshes the data instead of
# freezing at a hardcoded date. Override with DCA_DATA_END=YYYY-MM-DD if needed.
END = (
    date.fromisoformat(os.environ["DCA_DATA_END"])
    if os.environ.get("DCA_DATA_END")
    else date.today()
)


@dataclass(frozen=True)
class Instrument:
    """A selectable instrument: Yahoo ticker plus a human-friendly label."""

    ticker: str
    label: str


INSTRUMENTS: list[Instrument] = [
    Instrument("SPY", "SPY — S&P 500 ETF (US)"),
    Instrument("VOO", "VOO — Vanguard S&P 500 (US)"),
    Instrument("QQQ", "QQQ — Nasdaq 100 ETF (US)"),
    Instrument("CSPX.L", "CSPX — iShares Core S&P 500 (LSE)"),
    Instrument("EXW1.DE", "EXW1 — iShares EURO STOXX 50 (XETRA)"),
]


def _fetch(ticker: str) -> tuple[MarketData, str]:
    """Fetch a ticker, falling back to synthetic data on any failure."""
    cfg = DataConfig(
        provider=ProviderType.YAHOO,
        tickers=[ticker],
        start=START,
        end=END,
        use_cache=False,
    )
    try:
        return DataService(cfg).load(ticker), "yahoo"
    except Exception as exc:  # noqa: BLE001 - network/data issues fall back cleanly
        logger.warning("Yahoo fetch failed for {} ({}); using synthetic data", ticker, exc)
        synth = DataConfig(
            provider=ProviderType.SYNTHETIC,
            tickers=[ticker],
            start=START,
            end=END,
            use_cache=False,
        )
        return DataService(synth).load(ticker), "synthetic"


def _to_json(data: MarketData) -> dict:
    """Serialise an OHLC series compactly (rounded, no volume)."""
    frame = data.frame
    return {
        "ticker": data.ticker,
        "dates": [d.strftime("%Y-%m-%d") for d in frame.index],
        "open": [round(float(v), 4) for v in frame["open"]],
        "high": [round(float(v), 4) for v in frame["high"]],
        "low": [round(float(v), 4) for v in frame["low"]],
        "close": [round(float(v), 4) for v in frame["close"]],
    }


def main() -> None:
    """Fetch every instrument and write site/data/*.json plus a manifest."""
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for inst in INSTRUMENTS:
        data, source = _fetch(inst.ticker)
        (OUT / f"{inst.ticker}.json").write_text(json.dumps(_to_json(data)), encoding="utf-8")
        entries.append(
            {
                "ticker": inst.ticker,
                "label": inst.label,
                "source": source,
                "start": data.start.strftime("%Y-%m-%d"),
                "end": data.end.strftime("%Y-%m-%d"),
                "rows": len(data),
            }
        )
        logger.info("Bundled {} ({} rows, {})", inst.ticker, len(data), source)
    (OUT / "manifest.json").write_text(
        json.dumps({"frequency": Frequency.DAILY.value, "instruments": entries}, indent=2),
        encoding="utf-8",
    )
    print(f"Bundled {len(entries)} instruments into {OUT}/")


if __name__ == "__main__":
    main()
