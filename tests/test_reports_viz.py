"""Smoke tests for visualization and report generation."""

from __future__ import annotations

import plotly.graph_objects as go

from dcatoolbox.backtesting.runner import run_backtest
from dcatoolbox.config.enums import ReportFormat
from dcatoolbox.config.settings import OptimizationConfig
from dcatoolbox.optimization.grid_search import GridSearchOptimizer
from dcatoolbox.reports.generator import ReportGenerator
from dcatoolbox.reports.text import auto_conclusion, metrics_table
from dcatoolbox.visualization import charts, save_figures


def test_dashboard_returns_figures(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    dashboard = charts.build_dashboard(result)
    assert all(isinstance(fig, go.Figure) for fig in dashboard.values())
    assert "equity_curve" in dashboard


def test_save_figures_writes_html(base_config, synthetic_market, tmp_path) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    paths = save_figures(charts.build_dashboard(result), tmp_path)
    assert paths and all(p.exists() for p in paths)


def test_optimization_charts(base_config, synthetic_market) -> None:
    opt = GridSearchOptimizer(
        base_config,
        OptimizationConfig(
            param_grid={"threshold": [0.01, 0.02], "allocation": [0.2, 0.4]}, n_jobs=1
        ),
    )
    result = opt.run(synthetic_market)
    assert isinstance(charts.optimization_heatmap(result, "threshold", "allocation"), go.Figure)
    assert isinstance(charts.optimization_curve(result, "threshold"), go.Figure)


def test_metrics_table_and_conclusion(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    table = metrics_table(result)
    assert "CAGR" in table.index
    assert isinstance(auto_conclusion(result), str)


def test_report_generation_all_formats(base_config, synthetic_market, tmp_path) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    gen = ReportGenerator(result)
    md = gen.generate(ReportFormat.MARKDOWN, tmp_path / "r.md")
    html = gen.generate(ReportFormat.HTML, tmp_path / "r.html")
    pdf = gen.generate(ReportFormat.PDF, tmp_path / "r.pdf")
    assert md.exists() and html.exists() and pdf.exists()
    assert pdf.stat().st_size > 0
