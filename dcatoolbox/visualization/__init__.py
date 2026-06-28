"""Visualization layer: interactive Plotly charts and figure export."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from dcatoolbox.visualization.charts import (
    build_dashboard,
    cash_chart,
    drawdown_chart,
    equity_curve,
    fees_chart,
    invested_capital_chart,
    optimization_curve,
    optimization_heatmap,
    price_and_signals,
    purchase_distribution,
    returns_histogram,
)

__all__ = [
    "build_dashboard",
    "equity_curve",
    "drawdown_chart",
    "cash_chart",
    "invested_capital_chart",
    "fees_chart",
    "price_and_signals",
    "purchase_distribution",
    "returns_histogram",
    "optimization_heatmap",
    "optimization_curve",
    "save_figures",
]


def save_figures(figures: dict[str, go.Figure], out_dir: Path | str) -> list[Path]:
    """Write each figure to a standalone interactive HTML file.

    Args:
        figures: Mapping of slug name to figure.
        out_dir: Destination directory (created if needed).

    Returns:
        The list of written file paths.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, figure in figures.items():
        path = out / f"{name}.html"
        figure.write_html(str(path), include_plotlyjs="cdn", full_html=True)
        paths.append(path)
    return paths
