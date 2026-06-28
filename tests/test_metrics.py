"""Tests for the metrics layer (returns, XIRR and the aggregate class)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.metrics.performance import PerformanceMetrics
from dcatoolbox.metrics.returns import drawdown_series, xirr


def _history(values: list[float], invested: list[float]) -> pd.DataFrame:
    index = pd.bdate_range("2020-01-01", periods=len(values), name="date")
    return pd.DataFrame(
        {
            "cash": 0.0,
            "positions_value": values,
            "total_value": values,
            "invested_capital": invested,
            "cumulative_fees": 0.0,
            "quantity": 1.0,
            "n_trades": 1.0,
        },
        index=index,
    )


def test_xirr_simple_doubling() -> None:
    rate = xirr([-100.0, 200.0], [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")])
    # ~1.0; 2020 is a leap year (366 days) so the annualised rate is slightly below 1.
    assert rate == pytest.approx(1.0, abs=0.01)


def test_xirr_returns_nan_for_same_sign() -> None:
    assert np.isnan(xirr([-100.0, -50.0], [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")]))


def test_drawdown_series_is_non_positive() -> None:
    series = pd.Series([1.0, 1.2, 0.9, 1.1, 0.8])
    dd = drawdown_series(series)
    assert (dd <= 1e-12).all()
    assert dd.min() == pytest.approx(0.8 / 1.2 - 1.0)


def test_metrics_on_known_growth() -> None:
    values = [100.0 * 1.001**i for i in range(252)]
    invested = [100.0] * 252
    metrics = PerformanceMetrics(_history(values, invested), [], periods_per_year=252)
    assert metrics.total_return == pytest.approx(values[-1] / 100.0 - 1.0)
    assert metrics.annual_volatility >= 0.0
    assert metrics.max_drawdown <= 0.0


def test_metrics_empty_history_is_safe() -> None:
    empty = pd.DataFrame(
        columns=["cash", "positions_value", "total_value", "invested_capital", "cumulative_fees"]
    )
    metrics = PerformanceMetrics(empty, [])
    assert metrics.cagr == 0.0
    assert metrics.as_dict()["sharpe"] == 0.0


def test_relative_metrics_zero_when_identical() -> None:
    values = [100.0 + i for i in range(50)]
    invested = [100.0] * 50
    hist = _history(values, invested)
    metrics = PerformanceMetrics(hist, [], benchmark_history=hist)
    assert metrics.excess_total_return == pytest.approx(0.0, abs=1e-9)
    assert metrics.tracking_error == pytest.approx(0.0, abs=1e-9)


def test_as_dict_contains_all_expected_keys() -> None:
    metrics = PerformanceMetrics(_history([100.0, 101.0], [100.0, 100.0]), [])
    for key in ("cagr", "sharpe", "sortino", "calmar", "max_drawdown", "xirr", "n_orders"):
        assert key in metrics.as_dict()
