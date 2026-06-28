"""Abstract base class for all market-data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData

__all__ = ["MarketDataProvider"]


class MarketDataProvider(ABC):
    """Contract every concrete data source must fulfil.

    Implementations are responsible solely for *fetching* raw data and returning
    a normalised :class:`MarketData`. Caching, validation and gap-handling are
    handled by higher layers, keeping providers small and single-purpose.
    """

    name: str = "abstract"

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> MarketData:
        """Fetch OHLCV data for a single instrument.

        Args:
            ticker: Instrument symbol.
            start: Inclusive start date.
            end: Inclusive end date.
            frequency: Requested bar frequency.

        Returns:
            A validated :class:`MarketData` instance.

        Raises:
            DataProviderError: If the data cannot be retrieved.
        """
        raise NotImplementedError


class DataProviderError(RuntimeError):
    """Raised when a provider fails to return usable data."""
