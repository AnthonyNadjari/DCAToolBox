"""Tests for the data layer: models, cache, validation, providers, service."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import DataConfig
from dcatoolbox.data.cache import DataCache
from dcatoolbox.data.factory import DataService, build_provider
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError
from dcatoolbox.data.providers.bloomberg_provider import BloombergProvider
from dcatoolbox.data.providers.csv_provider import CSVProvider
from dcatoolbox.data.validation import DataValidator


def test_marketdata_requires_columns() -> None:
    frame = pd.DataFrame({"open": [1.0]}, index=pd.DatetimeIndex(["2020-01-01"]))
    with pytest.raises(ValueError):
        MarketData("X", Frequency.DAILY, frame)


def test_from_frame_normalises_columns_and_index(small_frame: pd.DataFrame) -> None:
    renamed = small_frame.rename(columns=str.upper)
    data = MarketData.from_frame("spy", Frequency.DAILY, renamed)
    assert {"open", "high", "low", "close", "volume"}.issubset(data.frame.columns)
    assert data.frame.index.is_monotonic_increasing


def test_slice_is_inclusive(small_frame: pd.DataFrame) -> None:
    data = MarketData.from_frame("SPY", Frequency.DAILY, small_frame)
    sliced = data.slice(small_frame.index[2], small_frame.index[5])
    assert len(sliced) == 4


def test_cache_roundtrip_and_merge(tmp_path, small_frame: pd.DataFrame) -> None:
    cache = DataCache(tmp_path)
    data = MarketData.from_frame("SPY", Frequency.DAILY, small_frame)
    assert not cache.has("SPY", Frequency.DAILY)
    cache.save(data)
    assert cache.has("SPY", Frequency.DAILY)
    loaded = cache.load("SPY", Frequency.DAILY)
    assert loaded is not None and len(loaded) == len(data)
    merged = cache.merge(data, data)
    assert len(merged) == len(data)


def test_validator_detects_and_repairs_bad_prices(small_frame: pd.DataFrame) -> None:
    frame = small_frame.copy()
    frame.iloc[3, frame.columns.get_loc("close")] = 0.0
    data = MarketData.from_frame("SPY", Frequency.DAILY, frame)
    validator = DataValidator()
    report = validator.validate(data)
    assert report.n_non_positive_prices >= 1
    assert not report.is_valid
    repaired = validator.repair(data)
    assert (repaired.frame[["open", "high", "low", "close"]] > 0).all().all()


def test_validator_finds_gaps(small_frame: pd.DataFrame) -> None:
    frame = small_frame.drop(small_frame.index[3:6])
    data = MarketData.from_frame("SPY", Frequency.DAILY, frame)
    report = DataValidator(max_gap_days=2).validate(data)
    assert len(report.gaps) >= 1


def test_synthetic_provider_is_deterministic() -> None:
    provider = build_provider(DataConfig(provider=ProviderType.SYNTHETIC))
    a = provider.fetch("SPY", date(2020, 1, 1), date(2021, 1, 1), Frequency.DAILY)
    b = provider.fetch("SPY", date(2020, 1, 1), date(2021, 1, 1), Frequency.DAILY)
    assert np.allclose(a.frame["close"].values, b.frame["close"].values)


def test_bloomberg_provider_is_stub() -> None:
    with pytest.raises(DataProviderError):
        BloombergProvider().fetch("SPY", date(2020, 1, 1), date(2021, 1, 1), Frequency.DAILY)


def test_csv_provider_roundtrip(tmp_path, small_frame: pd.DataFrame) -> None:
    small_frame.to_csv(tmp_path / "SPY.csv")
    provider = CSVProvider(tmp_path)
    data = provider.fetch("SPY", date(2020, 1, 1), date(2020, 12, 31), Frequency.DAILY)
    assert len(data) > 0
    with pytest.raises(DataProviderError):
        provider.fetch("MISSING", date(2020, 1, 1), date(2020, 12, 31), Frequency.DAILY)


def test_data_service_loads_and_caches(tmp_path) -> None:
    config = DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY", "VOO"],
        start=date(2018, 1, 1),
        end=date(2020, 1, 1),
        cache_dir=tmp_path,
    )
    service = DataService(config)
    market = service.load_many()
    assert set(market) == {"SPY", "VOO"}
    assert (tmp_path / "SPY_daily.parquet").exists()


def test_build_provider_csv_requires_dir() -> None:
    with pytest.raises(ValueError):
        build_provider(DataConfig(provider=ProviderType.CSV))
