"""Deterministic synthetic data provider.

This provider generates a reproducible geometric-Brownian-motion price path. It
serves two purposes: it makes the entire framework usable and *fully testable
offline* (no network), and it gives users a sandbox to validate strategies on
controlled scenarios.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import MarketDataProvider

__all__ = ["SyntheticProvider"]


class SyntheticProvider(MarketDataProvider):
    """Generate deterministic OHLCV data via geometric Brownian motion."""

    name = "synthetic"

    def __init__(
        self,
        *,
        seed: int = 42,
        annual_drift: float = 0.08,
        annual_vol: float = 0.18,
        start_price: float = 100.0,
    ) -> None:
        """Configure the price-process parameters.

        Args:
            seed: RNG seed; identical configs always produce identical paths.
            annual_drift: Expected annualised log-return.
            annual_vol: Annualised volatility.
            start_price: Initial close price.
        """
        self.seed = seed
        self.annual_drift = annual_drift
        self.annual_vol = annual_vol
        self.start_price = start_price

    def fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> MarketData:
        """Generate a synthetic OHLCV series for ``ticker``."""
        index = pd.bdate_range(start=start, end=end, name="date")
        n = len(index)
        # Seed deterministically from both the config seed and the ticker so that
        # different tickers get different but reproducible paths.
        rng = np.random.default_rng(self.seed + (abs(hash(ticker)) % 10_000))
        dt = 1.0 / 252.0
        shocks = rng.normal(
            loc=(self.annual_drift - 0.5 * self.annual_vol**2) * dt,
            scale=self.annual_vol * np.sqrt(dt),
            size=n,
        )
        close = self.start_price * np.exp(np.cumsum(shocks))
        open_ = np.concatenate([[self.start_price], close[:-1]])
        intraday = np.abs(rng.normal(0.0, self.annual_vol * np.sqrt(dt), size=n))
        high = np.maximum(open_, close) * (1.0 + intraday)
        low = np.minimum(open_, close) * (1.0 - intraday)
        volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
        frame = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=index,
        )
        return MarketData.from_frame(ticker, frequency, frame)
