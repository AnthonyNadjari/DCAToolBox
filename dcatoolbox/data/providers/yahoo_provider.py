"""Yahoo Finance data provider (via :mod:`yfinance`)."""

from __future__ import annotations

from datetime import date, timedelta

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError, MarketDataProvider
from dcatoolbox.utils.logging import logger

__all__ = ["YahooFinanceProvider"]


class YahooFinanceProvider(MarketDataProvider):
    """Fetch OHLCV data from Yahoo Finance.

    The framework never imports :mod:`yfinance` outside this module, so the rest
    of the code base is fully insulated from the vendor API.
    """

    name = "yahoo"

    def __init__(self, *, auto_adjust: bool = True) -> None:
        """Initialise the provider.

        Args:
            auto_adjust: Whether to let yfinance adjust prices for splits and
                dividends (recommended for total-return backtests).
        """
        self.auto_adjust = auto_adjust

    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> MarketData:
        """Download data for ``ticker`` from Yahoo Finance."""
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise DataProviderError("yfinance is not installed") from exc

        logger.info("Downloading {} from Yahoo Finance ({}-{})", ticker, start, end)
        frame = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval=frequency.yfinance_interval,
            auto_adjust=self.auto_adjust,
            progress=False,
        )
        if frame is None or frame.empty:
            raise DataProviderError(f"No data returned by Yahoo Finance for {ticker}")
        if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
            frame.columns = frame.columns.get_level_values(0)
        return MarketData.from_frame(ticker, frequency, frame)
