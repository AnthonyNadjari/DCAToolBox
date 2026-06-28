"""Tests for the grid-search optimizer and data splitting."""

from __future__ import annotations

from datetime import date

import pytest

from dcatoolbox.config.settings import OptimizationConfig, SplitConfig
from dcatoolbox.optimization.grid_search import GridSearchOptimizer
from dcatoolbox.optimization.splitter import DataSplitter, default_split


@pytest.fixture
def optimizer(base_config) -> GridSearchOptimizer:
    grid = OptimizationConfig(
        param_grid={"threshold": [0.01, 0.02, 0.03], "allocation": [0.2, 0.5]},
        rank_metric="sharpe",
        n_jobs=1,
    )
    return GridSearchOptimizer(base_config, grid)


def test_grid_combinations_count(optimizer) -> None:
    assert len(optimizer._combinations()) == 6


def test_run_ranks_results(optimizer, synthetic_market) -> None:
    result = optimizer.run(synthetic_market)
    assert len(result.results) == 6
    sharpe = result.results["sharpe"].values
    assert list(sharpe) == sorted(sharpe, reverse=True)
    assert set(result.best_params) == {"threshold", "allocation"}


def test_leaderboard_shape(optimizer, synthetic_market) -> None:
    board = optimizer.run(synthetic_market).leaderboard(3)
    assert len(board) == 3
    assert "threshold" in board.columns


def test_evaluate_splits_reports_each_window(optimizer, synthetic_market) -> None:
    split = default_split(2015, 2021)
    evaluation = optimizer.evaluate_splits(synthetic_market, split)
    assert list(evaluation.per_window.index) == ["train", "validation", "test"]
    assert "cagr" in evaluation.per_window.columns


def test_default_split_is_contiguous() -> None:
    split = default_split(2010, 2020)
    assert split.train[1] == split.validation[0]
    assert split.validation[1] == split.test[0]


def test_data_splitter_slices_market(synthetic_market) -> None:
    split = SplitConfig(
        train=(date(2015, 1, 1), date(2017, 1, 1)),
        validation=(date(2017, 1, 1), date(2019, 1, 1)),
        test=(date(2019, 1, 1), date(2021, 1, 1)),
    )
    windows = DataSplitter(split).split_market(synthetic_market)
    assert windows["train"]["SPY"].end.year <= 2017
