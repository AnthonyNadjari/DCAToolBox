"""Extra coverage for the data service, incremental update and Yahoo provider."""

from __future__ import annotations

import sys
import types
from datetime import date

import pandas as pd
import pytest

from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import DataConfig
from dcatoolbox.data.factory import DataService
from dcatoolbox.data.models import MarketData
from dcatoolbox.data.providers.base import DataProviderError
from dcatoolbox.data.providers.yahoo_provider import YahooFinanceProvider


def test_service_without_cache(tmp_path) -> None:
    config = DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2019, 1, 1),
        end=date(2020, 1, 1),
        cache_dir=tmp_path,
        use_cache=False,
    )
    data = DataService(config).load()
    assert len(data) > 0


def test_service_incremental_update(tmp_path) -> None:
    short = DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2018, 1, 1),
        end=date(2019, 1, 1),
        cache_dir=tmp_path,
    )
    DataService(short).load()  # primes the cache
    extended = short.model_copy(update={"end": date(2020, 1, 1)})
    data = DataService(extended).load()
    assert data.end.year >= 2019


def test_service_load_repairs_gaps(tmp_path) -> None:
    config = DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2019, 1, 1),
        end=date(2020, 1, 1),
        cache_dir=tmp_path,
    )
    service = DataService(config)
    # Inject a series with a hole and a bad price into the cache.
    base = service.provider.fetch("SPY", config.start, config.end, Frequency.DAILY)
    broken = base.frame.copy()
    broken = broken.drop(broken.index[10:20])
    broken.iloc[5, broken.columns.get_loc("close")] = 0.0
    service.cache.save(MarketData("SPY", Frequency.DAILY, broken))
    config_no_dl = config.model_copy(update={"auto_download": False})
    data = DataService(config_no_dl).load()
    assert (data.frame["close"] > 0).all()


def _fake_yfinance(frame: pd.DataFrame) -> types.ModuleType:
    module = types.ModuleType("yfinance")
    module.download = lambda *a, **k: frame  # type: ignore[attr-defined]
    return module


def test_yahoo_provider_with_mock(monkeypatch) -> None:
    index = pd.date_range("2020-01-01", periods=5, name="Date")
    frame = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=index
    )
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yfinance(frame))
    data = YahooFinanceProvider().fetch("SPY", date(2020, 1, 1), date(2020, 1, 6), Frequency.DAILY)
    assert len(data) == 5


def test_yahoo_provider_empty_raises(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yfinance(pd.DataFrame()))
    with pytest.raises(DataProviderError):
        YahooFinanceProvider().fetch("SPY", date(2020, 1, 1), date(2020, 1, 6), Frequency.DAILY)
