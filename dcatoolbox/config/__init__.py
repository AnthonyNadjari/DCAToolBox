"""Strongly-typed, validated configuration objects (Pydantic v2).

Every tunable parameter of the framework lives here. Configurations can be built
programmatically, loaded from YAML/JSON, and are immutable-by-convention once a
backtest starts.
"""

from __future__ import annotations

from dcatoolbox.config.enums import (
    Frequency,
    OrderSide,
    ProviderType,
    ReportFormat,
    SignalMethod,
)
from dcatoolbox.config.io import load_config, save_config
from dcatoolbox.config.settings import (
    BacktestConfig,
    BrokerConfig,
    DataConfig,
    OptimizationConfig,
    SplitConfig,
    StrategyConfig,
)

__all__ = [
    "Frequency",
    "OrderSide",
    "ProviderType",
    "ReportFormat",
    "SignalMethod",
    "DataConfig",
    "BrokerConfig",
    "StrategyConfig",
    "SplitConfig",
    "OptimizationConfig",
    "BacktestConfig",
    "load_config",
    "save_config",
]
