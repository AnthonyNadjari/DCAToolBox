"""Import side-effect module that registers all built-in strategies.

Importing this module guarantees every shipped strategy is present in the
registry. Third-party strategies only need to be imported once (e.g. via a plugin
entry point) to become available everywhere.
"""

from __future__ import annotations

from dcatoolbox.strategies.dip_buying import DipBuyingStrategy
from dcatoolbox.strategies.momentum import (
    AbsoluteMomentumStrategy,
    MomentumRotationStrategy,
)
from dcatoolbox.strategies.monthly_dca import MonthlyDCA
from dcatoolbox.strategies.moving_average_strategy import MovingAverageStrategy
from dcatoolbox.strategies.rsi_strategy import RSIStrategy
from dcatoolbox.strategies.trend_filter import TrendFilterStrategy

__all__ = [
    "MonthlyDCA",
    "DipBuyingStrategy",
    "RSIStrategy",
    "MovingAverageStrategy",
    "TrendFilterStrategy",
    "AbsoluteMomentumStrategy",
    "MomentumRotationStrategy",
]
