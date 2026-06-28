"""Bloomberg data provider stub.

A production deployment would wrap the Bloomberg ``blpapi`` / ``xbbg`` client
here. The class is intentionally a thin, well-documented placeholder so the
rest of the framework can already target it via configuration; the abstraction
proves the engine is provider-agnostic.
"""

from __future__ import annotations

from datetime import date

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError, MarketDataProvider

__all__ = ["BloombergProvider"]


class BloombergProvider(MarketDataProvider):
    """Placeholder provider for the Bloomberg Terminal / Data License API."""

    name = "bloomberg"

    def __init__(self, host: str = "localhost", port: int = 8194) -> None:
        """Store connection parameters for a real ``blpapi`` session."""
        self.host = host
        self.port = port

    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> MarketData:
        """Not implemented: requires a licensed Bloomberg connection.

        Raises:
            DataProviderError: Always, until wired to a real ``blpapi`` session.
        """
        raise DataProviderError(
            "BloombergProvider is a stub. Implement the blpapi/xbbg call here "
            "to enable Bloomberg as a data source."
        )
