"""Bundle market data (daily + intraday) as compact JSON for the web backtester.

Reuses the framework's data layer (:class:`DataService`). For every instrument it
writes a daily series (long history) and, when available, an hourly series
(intraday execution, limited by the vendor to ~2 years). A manifest lists, per
instrument, which frequencies exist and their ranges. Yahoo is used in CI; on any
failure the deterministic synthetic provider is the fallback so the page always
has data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dcatoolbox.backtesting.engine import periods_per_year
from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import DataConfig
from dcatoolbox.data.factory import DataService
from dcatoolbox.data.models import MarketData
from dcatoolbox.utils.logging import logger

OUT = Path("site/data")
DAILY_START = date(2000, 1, 1)
END = (
    date.fromisoformat(os.environ["DCA_DATA_END"])
    if os.environ.get("DCA_DATA_END")
    else date.today()
)
HOURLY_START = END - timedelta(days=700)  # vendor intraday history limit (~2y)


@dataclass(frozen=True)
class Instrument:
    """A selectable instrument: Yahoo ticker plus a human-friendly label."""

    ticker: str
    label: str


INSTRUMENTS: list[Instrument] = [
    Instrument("SPY", "SPY — S&P 500 ETF (US, $)"),
    Instrument("VOO", "VOO — Vanguard S&P 500 (US, $)"),
    Instrument("QQQ", "QQQ — Nasdaq 100 ETF (US, $)"),
    Instrument("CSPX.L", "CSPX — iShares Core S&P 500 (LSE, $)"),
    Instrument("EXW1.DE", "EXW1 — iShares EURO STOXX 50 (XETRA, €)"),
    # French-listed UCITS ETFs (Euronext Paris, €) — PEA-eligible candidates.
    Instrument("CW8.PA", "CW8 — Amundi MSCI World (Paris, €, PEA)"),
    Instrument("ESE.PA", "ESE — BNP Easy S&P 500 (Paris, €, PEA)"),
    Instrument("PUST.PA", "PUST — Amundi PEA Nasdaq-100 (Paris, €, PEA)"),
    Instrument("C40.PA", "C40 — Amundi CAC 40 (Paris, €, PEA)"),
]


def _fetch(ticker: str, start: date, frequency: Frequency) -> tuple[MarketData, str]:
    """Fetch one series, falling back to synthetic data on any failure."""
    base = {
        "tickers": [ticker],
        "start": start,
        "end": END,
        "frequency": frequency,
        "use_cache": False,
    }
    try:
        return DataService(DataConfig(provider=ProviderType.YAHOO, **base)).load(ticker), "yahoo"
    except Exception as exc:  # noqa: BLE001 - network/data issues fall back cleanly
        logger.warning("Yahoo fetch failed for {} {} ({}); synthetic", ticker, frequency.value, exc)
        return DataService(DataConfig(provider=ProviderType.SYNTHETIC, **base)).load(
            ticker
        ), "synthetic"


def _to_json(data: MarketData, frequency: Frequency) -> dict:
    """Serialise an OHLC series compactly (datetime stamps for intraday)."""
    fmt = "%Y-%m-%d" if frequency is Frequency.DAILY else "%Y-%m-%dT%H:%M"
    frame = data.frame
    return {
        "ticker": data.ticker,
        "dates": [d.strftime(fmt) for d in frame.index],
        "open": [round(float(v), 4) for v in frame["open"]],
        "high": [round(float(v), 4) for v in frame["high"]],
        "low": [round(float(v), 4) for v in frame["low"]],
        "close": [round(float(v), 4) for v in frame["close"]],
    }


def _bundle_one(inst: Instrument) -> dict:
    """Bundle all available frequencies for one instrument; return its manifest."""
    frequencies: dict[str, dict] = {}
    plan = [("daily", Frequency.DAILY, DAILY_START), ("hourly", Frequency.HOURLY, HOURLY_START)]
    for name, freq, start in plan:
        data, source = _fetch(inst.ticker, start, freq)
        suffix = "" if name == "daily" else f"_{name}"
        filename = f"{inst.ticker}{suffix}.json"
        (OUT / filename).write_text(json.dumps(_to_json(data, freq)), encoding="utf-8")
        frequencies[name] = {
            "file": filename,
            "source": source,
            "rows": len(data),
            "start": data.start.strftime("%Y-%m-%d"),
            "end": data.end.strftime("%Y-%m-%d"),
            "periodsPerYear": periods_per_year(freq),
        }
        logger.info("Bundled {} {} ({} rows, {})", inst.ticker, name, len(data), source)
    return {"ticker": inst.ticker, "label": inst.label, "frequencies": frequencies}


def main() -> None:
    """Fetch every instrument/frequency and write site/data/*.json + manifest."""
    OUT.mkdir(parents=True, exist_ok=True)
    instruments = [_bundle_one(inst) for inst in INSTRUMENTS]
    (OUT / "manifest.json").write_text(
        json.dumps({"instruments": instruments}, indent=2), encoding="utf-8"
    )
    print(f"Bundled {len(instruments)} instruments into {OUT}/")


if __name__ == "__main__":
    main()
