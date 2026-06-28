"""Pydantic configuration models for every layer of the framework.

The configuration is deliberately split into small, composable models so that,
for example, swapping the data provider is a one-line change and the backtest
engine itself never needs to be edited.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dcatoolbox.config.enums import Frequency, ProviderType

__all__ = [
    "DataConfig",
    "BrokerConfig",
    "StrategyConfig",
    "SplitConfig",
    "OptimizationConfig",
    "BacktestConfig",
]


class _FrozenModel(BaseModel):
    """Base model: validated on assignment and forbidding unknown fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DataConfig(_FrozenModel):
    """Configuration of the market-data source.

    The engine only ever sees a :class:`~dcatoolbox.data.models.MarketData`
    object; this model decides *where* that data comes from.
    """

    provider: ProviderType = ProviderType.YAHOO
    tickers: list[str] = Field(default_factory=lambda: ["SPY"], min_length=1)
    start: date = Field(default=date(2010, 1, 1))
    end: date = Field(default=date(2026, 1, 1))
    frequency: Frequency = Frequency.DAILY
    cache_dir: Path = Path("data_cache")
    csv_dir: Path | None = None
    use_cache: bool = True
    auto_download: bool = True

    @field_validator("tickers", mode="before")
    @classmethod
    def _normalise_tickers(cls, value: Any) -> Any:
        """Accept a single ticker string and upper-case all symbols."""
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            return [str(v).upper().strip() for v in value]
        return value

    @model_validator(mode="after")
    def _check_date_order(self) -> DataConfig:
        if self.end <= self.start:
            raise ValueError("`end` date must be strictly after `start` date")
        return self

    @property
    def primary_ticker(self) -> str:
        """First ticker, used as the investment/benchmark asset by default."""
        return self.tickers[0]


class BrokerConfig(_FrozenModel):
    """Trading-cost assumptions of the simulated broker."""

    fee_rate: float = Field(default=0.005, ge=0.0, le=1.0)
    slippage_rate: float = Field(default=0.0005, ge=0.0, le=1.0)
    min_fee: float = Field(default=0.0, ge=0.0)


class StrategyConfig(_FrozenModel):
    """Identifies a strategy by name and carries its free-form parameters.

    Parameters are intentionally kept as an open mapping so that registering a
    new strategy never requires changing this model. Each strategy validates its
    own parameters at construction time.
    """

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class SplitConfig(_FrozenModel):
    """Train / validation / test date boundaries for anti-overfitting analysis."""

    train: tuple[date, date]
    validation: tuple[date, date]
    test: tuple[date, date]

    @model_validator(mode="after")
    def _check_each_window(self) -> SplitConfig:
        for label, (start, end) in self.as_dict().items():
            if end <= start:
                raise ValueError(f"{label} window end must be after start")
        return self

    def as_dict(self) -> dict[str, tuple[date, date]]:
        """Return the three windows keyed by name."""
        return {"train": self.train, "validation": self.validation, "test": self.test}


class OptimizationConfig(_FrozenModel):
    """Grid-search parameter space and ranking options."""

    param_grid: dict[str, list[Any]] = Field(
        default_factory=lambda: {
            "threshold": [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05],
            "allocation": [0.10, 0.20, 0.25, 0.30, 0.40, 0.50],
        }
    )
    rank_metric: str = "sharpe"
    maximize: bool = True
    n_jobs: int = -1

    @field_validator("param_grid")
    @classmethod
    def _non_empty(cls, value: dict[str, list[Any]]) -> dict[str, list[Any]]:
        if not value:
            raise ValueError("`param_grid` must contain at least one parameter")
        if any(len(v) == 0 for v in value.values()):
            raise ValueError("every parameter in `param_grid` needs >= 1 value")
        return value


class BacktestConfig(_FrozenModel):
    """Top-level configuration aggregating every sub-configuration.

    This single object fully describes a reproducible backtest run: the data, the
    cost model, the strategy under test, the contribution plan and the benchmark.
    """

    data: DataConfig = Field(default_factory=DataConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    strategy: StrategyConfig = Field(default_factory=lambda: StrategyConfig(name="dip_buying"))
    benchmark: StrategyConfig = Field(default_factory=lambda: StrategyConfig(name="monthly_dca"))
    monthly_budget: float = Field(default=1000.0, gt=0.0)
    day_of_month: int = Field(default=26, ge=1, le=31)
    initial_cash: float = Field(default=0.0, ge=0.0)
    risk_free_rate: float = Field(default=0.02, ge=0.0, le=1.0)

    def with_strategy_params(self, **params: Any) -> BacktestConfig:
        """Return a copy with the strategy parameters overridden/merged.

        Used heavily by the optimizer to spawn parameter variations without
        mutating the original configuration.
        """
        merged = {**self.strategy.params, **params}
        new_strategy = self.strategy.model_copy(update={"params": merged})
        return self.model_copy(update={"strategy": new_strategy})
