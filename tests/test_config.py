"""Tests for configuration models and (de)serialisation."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from dcatoolbox.config.io import load_config, save_config
from dcatoolbox.config.settings import (
    BacktestConfig,
    DataConfig,
    OptimizationConfig,
    SplitConfig,
)


def test_ticker_normalisation_from_string() -> None:
    cfg = DataConfig(tickers="spy")
    assert cfg.tickers == ["SPY"]
    assert cfg.primary_ticker == "SPY"


def test_date_order_validation() -> None:
    with pytest.raises(ValidationError):
        DataConfig(start=date(2020, 1, 1), end=date(2019, 1, 1))


def test_with_strategy_params_merges() -> None:
    cfg = BacktestConfig()
    updated = cfg.with_strategy_params(threshold=0.03)
    assert updated.strategy.params["threshold"] == 0.03
    assert cfg.strategy.params == {}  # original untouched


def test_optimization_config_rejects_empty_grid() -> None:
    with pytest.raises(ValidationError):
        OptimizationConfig(param_grid={})


def test_split_config_validates_windows() -> None:
    with pytest.raises(ValidationError):
        SplitConfig(
            train=(date(2010, 1, 1), date(2009, 1, 1)),
            validation=(date(2010, 1, 1), date(2011, 1, 1)),
            test=(date(2011, 1, 1), date(2012, 1, 1)),
        )


def test_save_and_load_roundtrip(tmp_path) -> None:
    cfg = BacktestConfig(monthly_budget=500.0, day_of_month=15)
    for suffix in ("yaml", "json"):
        path = save_config(cfg, tmp_path / f"cfg.{suffix}")
        loaded = load_config(path)
        assert loaded.monthly_budget == 500.0
        assert loaded.day_of_month == 15
        assert loaded == cfg
