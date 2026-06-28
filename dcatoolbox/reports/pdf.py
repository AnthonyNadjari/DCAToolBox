"""PDF report generation using Matplotlib (no external system dependencies).

Plotly's image export needs the ``kaleido`` binary, which is not always
available offline. To keep PDF generation robust, charts are re-drawn with
Matplotlib from the same underlying data and written to a multi-page PDF.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from dcatoolbox.backtesting.result import BacktestResult  # noqa: E402
from dcatoolbox.reports.text import auto_conclusion, key_findings, metrics_table  # noqa: E402

__all__ = ["write_pdf"]


def write_pdf(result: BacktestResult, path: Path | str) -> Path:
    """Render a multi-page PDF report for ``result`` to ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(path)) as pdf:
        _summary_page(result, pdf)
        _metrics_page(result, pdf)
        _charts_page(result, pdf)
    return path


def _summary_page(result: BacktestResult, pdf: PdfPages) -> None:
    """First page: title, key findings and the auto conclusion."""
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
    fig.text(0.5, 0.95, "DCA Backtest Report", ha="center", fontsize=20, weight="bold")
    fig.text(
        0.5,
        0.91,
        f"{result.strategy.name} on {result.primary_ticker}",
        ha="center",
        fontsize=13,
        color="#2563eb",
    )
    y = 0.83
    fig.text(0.08, y, "Key findings", fontsize=14, weight="bold")
    for item in key_findings(result):
        y -= 0.05
        fig.text(0.10, y, f"• {item}", fontsize=10, wrap=True)
    y -= 0.08
    fig.text(0.08, y, "Conclusion", fontsize=14, weight="bold")
    fig.text(0.10, y - 0.04, auto_conclusion(result).replace("**", ""), fontsize=10, wrap=True)
    pdf.savefig(fig)
    plt.close(fig)


def _metrics_page(result: BacktestResult, pdf: PdfPages) -> None:
    """Second page: the formatted metrics table."""
    table = metrics_table(result).reset_index()
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis("off")
    ax.set_title("Performance metrics", fontsize=14, weight="bold", pad=20)
    rendered = ax.table(
        cellText=table.values, colLabels=table.columns, loc="center", cellLoc="center"
    )
    rendered.auto_set_font_size(False)
    rendered.set_fontsize(8)
    rendered.scale(1, 1.4)
    pdf.savefig(fig)
    plt.close(fig)


def _charts_page(result: BacktestResult, pdf: PdfPages) -> None:
    """Third page: equity, drawdown, cash and fees charts."""
    hist = result.strategy.history
    fig, axes = plt.subplots(2, 2, figsize=(11.69, 8.27))
    equity = result.equity_frame()
    for column in equity.columns:
        axes[0, 0].plot(equity.index, equity[column], label=column)
    axes[0, 0].set_title("Portfolio value")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].fill_between(
        result.strategy_metrics.drawdown.index,
        result.strategy_metrics.drawdown.values,
        0,
        color="#ef4444",
        alpha=0.5,
    )
    axes[0, 1].set_title("Drawdown")
    axes[1, 0].fill_between(hist.index, hist["cash"], 0, color="#10b981", alpha=0.5)
    axes[1, 0].set_title("Remaining cash")
    axes[1, 1].plot(hist.index, hist["cumulative_fees"], color="#f59e0b")
    axes[1, 1].set_title("Cumulative fees")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
