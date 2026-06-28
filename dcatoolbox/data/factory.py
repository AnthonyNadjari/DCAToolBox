"""High-level data access: provider selection, caching and validation.

:class:`DataService` is the single entry point the rest of the framework uses to
obtain market data. It hides provider choice, incremental caching, validation and
gap repair behind one method, :meth:`DataService.load`.
"""

from __future__ import annotations

import pandas as pd

from dcatoolbox.config.enums import ProviderType
from dcatoolbox.config.settings import DataConfig
from dcatoolbox.data.cache import DataCache
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError, MarketDataProvider
from dcatoolbox.data.providers.bloomberg_provider import BloombergProvider
from dcatoolbox.data.providers.csv_provider import CSVProvider
from dcatoolbox.data.providers.synthetic_provider import SyntheticProvider
from dcatoolbox.data.providers.yahoo_provider import YahooFinanceProvider
from dcatoolbox.data.validation import DataValidator
from dcatoolbox.utils.logging import logger

__all__ = ["build_provider", "DataService"]


def build_provider(config: DataConfig) -> MarketDataProvider:
    """Instantiate the provider declared in ``config``.

    This is the *only* place that maps a :class:`ProviderType` to a concrete
    class, so adding a provider is a one-line change here.
    """
    match config.provider:
        case ProviderType.YAHOO:
            return YahooFinanceProvider()
        case ProviderType.CSV:
            if config.csv_dir is None:
                raise ValueError("DataConfig.csv_dir is required for the CSV provider")
            return CSVProvider(config.csv_dir)
        case ProviderType.BLOOMBERG:
            return BloombergProvider()
        case ProviderType.SYNTHETIC:
            return SyntheticProvider()
    raise ValueError(f"Unknown provider type: {config.provider}")  # pragma: no cover


class DataService:
    """Orchestrates providers, cache and validation for the whole framework."""

    def __init__(
        self,
        config: DataConfig,
        *,
        provider: MarketDataProvider | None = None,
        validator: DataValidator | None = None,
    ) -> None:
        """Create the service.

        Args:
            config: Data configuration.
            provider: Optional explicit provider (defaults to ``build_provider``).
            validator: Optional explicit validator.
        """
        self.config = config
        self.provider = provider or build_provider(config)
        self.cache = DataCache(config.cache_dir)
        self.validator = validator or DataValidator()

    def load(self, ticker: str | None = None) -> MarketData:
        """Return validated, repaired data for ``ticker`` (or the primary one)."""
        ticker = (ticker or self.config.primary_ticker).upper()
        data = self._load_raw(ticker)
        data = data.slice(pd.Timestamp(self.config.start), pd.Timestamp(self.config.end))
        report = self.validator.validate(data)
        if not report.is_valid or report.gaps:
            logger.warning("Repairing data quality issues: {}", report.summary())
            data = self.validator.repair(data)
        if len(data) == 0:
            raise DataProviderError(f"No usable data for {ticker} in the requested window")
        return data

    def load_many(self, tickers: list[str] | None = None) -> dict[str, MarketData]:
        """Load several instruments at once, keyed by ticker."""
        tickers = tickers or self.config.tickers
        return {t.upper(): self.load(t) for t in tickers}

    def _load_raw(self, ticker: str) -> MarketData:
        """Resolve raw data using the cache with incremental update."""
        freq = self.config.frequency
        if not self.config.use_cache:
            return self.provider.fetch(ticker, self.config.start, self.config.end, freq)

        cached = self.cache.load(ticker, freq)
        if cached is None:
            return self._download_and_cache(ticker)

        if self.config.auto_download:
            cached = self._incremental_update(ticker, cached)
        return cached

    def _incremental_update(self, ticker: str, cached: MarketData) -> MarketData:
        """Fetch only the missing tail beyond the cached series, if any."""
        last = cached.end.date()
        if last >= self.config.end:
            return cached
        try:
            fresh = self.provider.fetch(ticker, last, self.config.end, self.config.frequency)
        except DataProviderError as exc:
            logger.warning("Incremental update failed for {}: {}", ticker, exc)
            return cached
        merged = self.cache.merge(cached, fresh)
        self.cache.save(merged)
        return merged

    def _download_and_cache(self, ticker: str) -> MarketData:
        """Download the full window and store it in the cache."""
        data = self.provider.fetch(
            ticker, self.config.start, self.config.end, self.config.frequency
        )
        self.cache.save(data)
        return data
