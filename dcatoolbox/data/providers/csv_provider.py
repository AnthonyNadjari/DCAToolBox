"""CSV-file data provider for offline / proprietary datasets."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError, MarketDataProvider

__all__ = ["CSVProvider"]


class CSVProvider(MarketDataProvider):
    """Load OHLCV data from per-ticker CSV files in a directory.

    A file named ``<TICKER>.csv`` is expected to contain a date column (first
    column or one named ``date``) plus OHLCV columns in any common casing.
    """

    name = "csv"

    def __init__(self, directory: Path | str) -> None:
        """Initialise the provider with the directory holding the CSV files."""
        self.directory = Path(directory)

    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> MarketData:
        """Load and slice the CSV file for ``ticker``."""
        path = self.directory / f"{ticker.upper()}.csv"
        if not path.exists():
            raise DataProviderError(f"CSV file not found: {path}")
        frame = pd.read_csv(path)
        date_col = "date" if "date" in frame.columns else frame.columns[0]
        frame[date_col] = pd.to_datetime(frame[date_col])
        frame = frame.set_index(date_col)
        data = MarketData.from_frame(ticker, frequency, frame)
        return data.slice(pd.Timestamp(start), pd.Timestamp(end))
