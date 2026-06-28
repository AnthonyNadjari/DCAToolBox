"""In-memory representation of market data used everywhere downstream.

:class:`MarketData` is a thin, validated wrapper around a tidy OHLCV
:class:`pandas.DataFrame`. It is the *only* data type the backtest engine knows
about, which is what decouples the engine from the provider implementations.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dcatoolbox.config.enums import Frequency

__all__ = ["MarketData", "OHLCV_COLUMNS"]

OHLCV_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class MarketData:
    """Validated OHLCV series for a single instrument.

    Attributes:
        ticker: The instrument symbol (e.g. ``"SPY"``).
        frequency: Bar frequency of the series.
        frame: A DataFrame indexed by a sorted, tz-naive ``DatetimeIndex`` named
            ``"date"`` and containing at least the columns in
            :data:`OHLCV_COLUMNS`.
    """

    ticker: str
    frequency: Frequency
    frame: pd.DataFrame

    def __post_init__(self) -> None:
        missing = [c for c in OHLCV_COLUMNS if c not in self.frame.columns]
        if missing:
            raise ValueError(f"MarketData for {self.ticker} missing columns: {missing}")
        if not isinstance(self.frame.index, pd.DatetimeIndex):
            raise TypeError("MarketData frame must be indexed by a DatetimeIndex")
        if not self.frame.index.is_monotonic_increasing:
            raise ValueError("MarketData frame index must be sorted ascending")

    @property
    def calendar(self) -> pd.DatetimeIndex:
        """The trading calendar implied by the data (its index)."""
        return self.frame.index

    @property
    def start(self) -> pd.Timestamp:
        """First available timestamp."""
        return self.frame.index[0]

    @property
    def end(self) -> pd.Timestamp:
        """Last available timestamp."""
        return self.frame.index[-1]

    def __len__(self) -> int:
        return len(self.frame)

    def slice(self, start: pd.Timestamp | None, end: pd.Timestamp | None) -> MarketData:
        """Return a new :class:`MarketData` restricted to ``[start, end]``.

        Bounds are inclusive and ``None`` means "unbounded on that side".
        """
        sliced = self.frame.loc[start:end]
        return MarketData(ticker=self.ticker, frequency=self.frequency, frame=sliced.copy())

    @classmethod
    def from_frame(cls, ticker: str, frequency: Frequency, frame: pd.DataFrame) -> MarketData:
        """Build a :class:`MarketData` from a raw frame, normalising it first.

        Column names are lower-cased and the index is coerced to a sorted,
        tz-naive ``DatetimeIndex`` named ``"date"``.
        """
        normalised = frame.copy()
        normalised.columns = [str(c).lower().replace(" ", "_") for c in normalised.columns]
        if "adj_close" in normalised.columns and "close" not in normalised.columns:
            normalised["close"] = normalised["adj_close"]
        idx = pd.DatetimeIndex(normalised.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        normalised.index = idx
        normalised.index.name = "date"
        normalised = normalised.sort_index()
        normalised = normalised[~normalised.index.duplicated(keep="last")]
        return cls(ticker=ticker, frequency=frequency, frame=normalised)
