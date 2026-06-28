"""Metrics layer: performance and risk analytics grouped in one class."""

from __future__ import annotations

from dcatoolbox.metrics.performance import PerformanceMetrics
from dcatoolbox.metrics.returns import (
    drawdown_series,
    external_flows,
    time_weighted_returns,
    wealth_index,
    xirr,
)

__all__ = [
    "PerformanceMetrics",
    "time_weighted_returns",
    "wealth_index",
    "drawdown_series",
    "external_flows",
    "xirr",
]
