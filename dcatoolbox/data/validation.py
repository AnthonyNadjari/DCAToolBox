"""Data-quality validation and gap handling.

The validator is intentionally conservative: it *reports* problems and offers a
single, well-defined repair (forward-filling internal gaps) rather than silently
mutating data in surprising ways.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dcatoolbox.data.models import OHLCV_COLUMNS, MarketData
from dcatoolbox.utils.logging import logger

__all__ = ["ValidationReport", "DataValidator"]


@dataclass
class ValidationReport:
    """Outcome of validating a :class:`MarketData` series."""

    ticker: str
    n_rows: int
    n_duplicates: int = 0
    n_missing_values: int = 0
    n_non_positive_prices: int = 0
    gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """``True`` when no blocking issue was detected."""
        return self.n_rows > 0 and self.n_duplicates == 0 and self.n_non_positive_prices == 0

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"[{self.ticker}] rows={self.n_rows} dupes={self.n_duplicates} "
            f"missing={self.n_missing_values} bad_prices={self.n_non_positive_prices} "
            f"gaps={len(self.gaps)} -> {'OK' if self.is_valid else 'ISSUES'}"
        )


class DataValidator:
    """Validate and optionally repair OHLCV market data."""

    def __init__(self, max_gap_days: int = 5) -> None:
        """Initialise the validator.

        Args:
            max_gap_days: Calendar-day distance above which a missing stretch is
                flagged as a gap (weekends/holidays below this are ignored).
        """
        self.max_gap_days = max_gap_days

    def validate(self, data: MarketData) -> ValidationReport:
        """Inspect ``data`` and return a :class:`ValidationReport`."""
        frame = data.frame
        report = ValidationReport(ticker=data.ticker, n_rows=len(frame))
        report.n_duplicates = int(frame.index.duplicated().sum())
        report.n_missing_values = int(frame[list(OHLCV_COLUMNS)].isna().sum().sum())
        prices = frame[["open", "high", "low", "close"]]
        report.n_non_positive_prices = int((prices <= 0).sum().sum())
        report.gaps = self._find_gaps(frame.index)
        logger.debug(report.summary())
        return report

    def repair(self, data: MarketData) -> MarketData:
        """Return a repaired copy: drop duplicates and forward-fill price gaps.

        Volume gaps are filled with zero (no trading), prices are carried
        forward, which is the standard convention for non-trading bars.
        """
        frame = data.frame[~data.frame.index.duplicated(keep="last")].copy()
        price_cols = ["open", "high", "low", "close"]
        frame[price_cols] = frame[price_cols].replace(0.0, np.nan).ffill()
        if "volume" in frame.columns:
            frame["volume"] = frame["volume"].fillna(0.0)
        frame = frame.dropna(subset=price_cols)
        return MarketData(ticker=data.ticker, frequency=data.frequency, frame=frame)

    def _find_gaps(self, index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Return ``(prev, next)`` pairs separated by more than ``max_gap_days``."""
        if len(index) < 2:
            return []
        deltas = index.to_series().diff().dt.days.fillna(0)
        gap_positions = np.where(deltas > self.max_gap_days)[0]
        return [(index[pos - 1], index[pos]) for pos in gap_positions]
