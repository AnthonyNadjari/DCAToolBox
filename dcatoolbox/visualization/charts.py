"""Interactive Plotly charts for a :class:`BacktestResult` and optimizations.

Each function builds and returns a self-contained :class:`plotly.graph_objects.Figure`
so callers (CLI, reports, Streamlit) can display, embed or export them freely.
"""

from __future__ import annotations

import plotly.graph_objects as go

from dcatoolbox.backtesting.result import BacktestResult
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.optimization.grid_search import OptimizationResult

__all__ = [
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
    "build_dashboard",
]

_TEMPLATE = "plotly_white"


def _figure(title: str, ytitle: str) -> go.Figure:
    """Create an empty, consistently-themed figure."""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template=_TEMPLATE,
        xaxis_title="Date",
        yaxis_title=ytitle,
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.05},
    )
    return fig


def equity_curve(result: BacktestResult) -> go.Figure:
    """Portfolio value over time, strategy versus benchmark."""
    fig = _figure("Portfolio value: strategy vs benchmark", "Total value")
    equity = result.equity_frame()
    for column in equity.columns:
        fig.add_scatter(x=equity.index, y=equity[column], mode="lines", name=column)
    return fig


def drawdown_chart(result: BacktestResult) -> go.Figure:
    """Time-weighted drawdown of the strategy (and benchmark, if present)."""
    fig = _figure("Drawdown", "Drawdown")
    dd = result.strategy_metrics.drawdown
    fig.add_scatter(
        x=dd.index, y=dd.values, mode="lines", name=result.strategy.name, fill="tozeroy"
    )
    if result.benchmark_metrics is not None:
        bdd = result.benchmark_metrics.drawdown
        fig.add_scatter(x=bdd.index, y=bdd.values, mode="lines", name=result.benchmark.name)
    fig.update_layout(yaxis_tickformat=".0%")
    return fig


def cash_chart(result: BacktestResult) -> go.Figure:
    """Uninvested cash (remaining budget) over time."""
    fig = _figure("Remaining cash", "Cash")
    cash = result.strategy.history["cash"]
    fig.add_scatter(x=cash.index, y=cash.values, mode="lines", name="Cash", fill="tozeroy")
    return fig


def invested_capital_chart(result: BacktestResult) -> go.Figure:
    """Cumulative invested capital versus marked-to-market portfolio value."""
    fig = _figure("Invested capital vs portfolio value", "Amount")
    hist = result.strategy.history
    fig.add_scatter(x=hist.index, y=hist["invested_capital"], mode="lines", name="Invested capital")
    fig.add_scatter(x=hist.index, y=hist["total_value"], mode="lines", name="Portfolio value")
    return fig


def fees_chart(result: BacktestResult) -> go.Figure:
    """Cumulative trading fees over time."""
    fig = _figure("Cumulative fees", "Fees")
    fees = result.strategy.history["cumulative_fees"]
    fig.add_scatter(x=fees.index, y=fees.values, mode="lines", name="Fees", fill="tozeroy")
    return fig


def price_and_signals(result: BacktestResult) -> go.Figure:
    """ETF price with buy markers coloured by their trigger reason."""
    fig = _figure(f"{result.primary_ticker} price and buy signals", "Price")
    frame = result.market[result.primary_ticker].frame
    fig.add_scatter(
        x=frame.index, y=frame["close"], mode="lines", name=f"{result.primary_ticker} close"
    )
    buys = [t for t in result.strategy.trades if t.side is OrderSide.BUY]
    for reason in sorted({t.reason for t in buys}):
        points = [t for t in buys if t.reason == reason]
        fig.add_scatter(
            x=[t.timestamp for t in points],
            y=[t.price for t in points],
            mode="markers",
            name=f"buy: {reason or 'n/a'}",
            marker={"size": 8},
        )
    return fig


def purchase_distribution(result: BacktestResult) -> go.Figure:
    """Histogram of purchase amounts, split by trigger reason."""
    fig = _figure("Distribution of purchase amounts", "Count")
    fig.update_layout(xaxis_title="Order amount", barmode="overlay")
    buys = [t for t in result.strategy.trades if t.side is OrderSide.BUY]
    for reason in sorted({t.reason for t in buys}):
        amounts = [t.gross_value for t in buys if t.reason == reason]
        fig.add_histogram(x=amounts, name=f"{reason or 'n/a'}", opacity=0.7)
    return fig


def returns_histogram(result: BacktestResult) -> go.Figure:
    """Histogram of the strategy's daily time-weighted returns."""
    fig = _figure("Distribution of daily returns", "Count")
    fig.update_layout(xaxis_title="Daily return", xaxis_tickformat=".1%")
    fig.add_histogram(x=result.strategy_metrics.returns.values, name="Daily returns")
    return fig


def optimization_heatmap(
    result: OptimizationResult, x: str, y: str, metric: str | None = None
) -> go.Figure:
    """Heatmap of an optimization metric across two parameters."""
    metric = metric or result.rank_metric
    pivot = result.results.pivot_table(index=y, columns=x, values=metric, aggfunc="mean")
    fig = go.Figure(
        go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, colorbar={"title": metric})
    )
    fig.update_layout(
        title=f"{metric} by {x} and {y}", template=_TEMPLATE, xaxis_title=x, yaxis_title=y
    )
    return fig


def optimization_curve(result: OptimizationResult, x: str, metric: str | None = None) -> go.Figure:
    """Line chart of a metric versus one parameter (averaged over the rest)."""
    metric = metric or result.rank_metric
    curve = result.results.groupby(x)[metric].mean().sort_index()
    fig = _figure(f"{metric} versus {x}", metric)
    fig.update_layout(xaxis_title=x)
    fig.add_scatter(x=curve.index, y=curve.values, mode="lines+markers", name=metric)
    return fig


def build_dashboard(result: BacktestResult) -> dict[str, go.Figure]:
    """Return the standard set of charts keyed by a slug name."""
    return {
        "equity_curve": equity_curve(result),
        "drawdown": drawdown_chart(result),
        "cash": cash_chart(result),
        "invested_capital": invested_capital_chart(result),
        "fees": fees_chart(result),
        "price_and_signals": price_and_signals(result),
        "purchase_distribution": purchase_distribution(result),
        "returns_histogram": returns_histogram(result),
    }
