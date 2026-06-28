"""Enumerations shared across the framework.

Using string-valued enums keeps configuration files human-readable while still
giving the code base the safety of a closed set of values.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "Frequency",
    "ProviderType",
    "OrderSide",
    "SignalMethod",
    "ReportFormat",
]


class Frequency(StrEnum):
    """Bar frequency of a market data series."""

    DAILY = "daily"
    HOURLY = "hourly"
    INTRADAY = "intraday"

    @property
    def yfinance_interval(self) -> str:
        """Map the frequency to a yfinance ``interval`` string."""
        return {
            Frequency.DAILY: "1d",
            Frequency.HOURLY: "1h",
            Frequency.INTRADAY: "15m",
        }[self]


class ProviderType(StrEnum):
    """Supported market-data provider back-ends."""

    YAHOO = "yahoo"
    CSV = "csv"
    BLOOMBERG = "bloomberg"
    SYNTHETIC = "synthetic"


class OrderSide(StrEnum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class SignalMethod(StrEnum):
    """Built-in price-based dip detection methods.

    Each value maps to an interchangeable :class:`~dcatoolbox.strategies.signals`
    module. New methods can be registered without modifying the engine.
    """

    OPEN_VS_OPEN = "open_vs_open"
    CLOSE_VS_CLOSE = "close_vs_close"
    OPEN_VS_CLOSE = "open_vs_close"
    CLOSE_VS_OPEN = "close_vs_open"
    DRAWDOWN_N_DAYS = "drawdown_n_days"
    CUMULATIVE_RETURN = "cumulative_return"


class ReportFormat(StrEnum):
    """Output formats supported by the report generator."""

    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
