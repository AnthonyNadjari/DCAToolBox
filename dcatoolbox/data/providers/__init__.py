"""Market-data providers behind a single abstract interface.

Adding a new data source means subclassing
:class:`~dcatoolbox.data.providers.base.MarketDataProvider` and registering it in
:func:`~dcatoolbox.data.factory.build_provider` -- nothing else in the framework
changes.
"""

from __future__ import annotations

from dcatoolbox.data.providers.base import MarketDataProvider
from dcatoolbox.data.providers.bloomberg_provider import BloombergProvider
from dcatoolbox.data.providers.csv_provider import CSVProvider
from dcatoolbox.data.providers.synthetic_provider import SyntheticProvider
from dcatoolbox.data.providers.yahoo_provider import YahooFinanceProvider

__all__ = [
    "MarketDataProvider",
    "YahooFinanceProvider",
    "CSVProvider",
    "BloombergProvider",
    "SyntheticProvider",
]
