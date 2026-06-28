"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import BacktestConfig, DataConfig, StrategyConfig
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.synthetic_provider import SyntheticProvider


@pytest.fixture
def synthetic_market() -> dict[str, MarketData]:
    """A deterministic synthetic market for SPY over several years."""
    provider = SyntheticProvider(seed=7)
    data = provider.fetch("SPY", date(2015, 1, 1), date(2021, 1, 1), Frequency.DAILY)
    return {"SPY": data}


@pytest.fixture
def base_config() -> BacktestConfig:
    """A standard backtest config using the synthetic provider."""
    return BacktestConfig(
        data=DataConfig(
            provider=ProviderType.SYNTHETIC,
            tickers=["SPY"],
            start=date(2015, 1, 1),
            end=date(2021, 1, 1),
        ),
        strategy=StrategyConfig(name="dip_buying", params={"threshold": 0.02, "allocation": 0.25}),
        benchmark=StrategyConfig(name="monthly_dca"),
    )


@pytest.fixture
def small_frame() -> pd.DataFrame:
    """A tiny, hand-built OHLCV frame for unit tests."""
    index = pd.bdate_range("2020-01-01", periods=10, name="date")
    close = np.array([100, 98, 102, 95, 97, 99, 90, 92, 94, 100], dtype=float)
    return pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.97,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )
