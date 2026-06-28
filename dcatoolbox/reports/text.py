"""Human-readable formatting and an automatic conclusion for reports."""

from __future__ import annotations

import pandas as pd

from dcatoolbox.backtesting.result import BacktestResult

__all__ = ["METRIC_LABELS", "format_value", "metrics_table", "auto_conclusion", "key_findings"]

#: Display label and format kind for each metric.
METRIC_LABELS: dict[str, tuple[str, str]] = {
    "total_return": ("Total return", "pct"),
    "twr_total_return": ("Time-weighted return", "pct"),
    "cagr": ("CAGR", "pct"),
    "annual_return": ("Annualised return", "pct"),
    "annual_volatility": ("Annualised volatility", "pct"),
    "sharpe": ("Sharpe ratio", "num"),
    "sortino": ("Sortino ratio", "num"),
    "calmar": ("Calmar ratio", "num"),
    "max_drawdown": ("Maximum drawdown", "pct"),
    "time_under_water": ("Time under water", "pct"),
    "max_time_under_water_days": ("Longest underwater run (bars)", "int"),
    "irr": ("IRR (monthly)", "pct"),
    "xirr": ("XIRR (annual)", "pct"),
    "tracking_error": ("Tracking error", "pct"),
    "information_ratio": ("Information ratio", "num"),
    "n_orders": ("Number of orders", "int"),
    "avg_order_amount": ("Average order amount", "cur"),
    "avg_buy_price": ("Average buy price", "cur"),
    "avg_cash": ("Average cash", "cur"),
    "cumulative_fees": ("Cumulative fees", "cur"),
    "invested_capital": ("Invested capital", "cur"),
    "final_value": ("Final value", "cur"),
    "excess_total_return": ("Excess total return vs benchmark", "pct"),
    "excess_cagr": ("Excess CAGR vs benchmark", "pct"),
}


def format_value(value: float, kind: str) -> str:
    """Format a metric value according to its ``kind``."""
    if value != value:  # NaN
        return "n/a"
    match kind:
        case "pct":
            return f"{value:.2%}"
        case "cur":
            return f"{value:,.2f}"
        case "int":
            return f"{int(value):,}"
        case _:
            return f"{value:.3f}"


def metrics_table(result: BacktestResult) -> pd.DataFrame:
    """Build a labelled, formatted comparison table (strategy vs benchmark)."""
    raw = result.comparison_frame()
    rows = []
    for key, (label, kind) in METRIC_LABELS.items():
        if key not in raw.index:
            continue
        rows.append(
            {"Metric": label, **{col: format_value(raw.loc[key, col], kind) for col in raw.columns}}
        )
    return pd.DataFrame(rows).set_index("Metric")


def key_findings(result: BacktestResult) -> list[str]:
    """Return a short list of automatically-derived findings."""
    m = result.strategy_metrics
    findings = [
        f"Final portfolio value of {m.final_value:,.0f} from {m.invested_capital:,.0f} invested "
        f"({m.total_return:.2%} total return).",
        f"CAGR of {m.cagr:.2%} with annualised volatility of {m.annual_volatility:.2%} "
        f"(Sharpe {m.sharpe:.2f}).",
        f"Maximum drawdown of {m.max_drawdown:.2%}; {m.n_orders} orders for "
        f"{m.cumulative_fees:,.0f} in fees.",
    ]
    if result.benchmark_metrics is not None:
        findings.append(
            f"Versus the {result.benchmark.name} benchmark: "
            f"{m.excess_total_return:+.2%} total return and {m.excess_cagr:+.2%} CAGR, "
            f"information ratio {m.information_ratio:.2f}."
        )
    return findings


def auto_conclusion(result: BacktestResult) -> str:
    """Generate a one-paragraph conclusion comparing strategy and benchmark."""
    m = result.strategy_metrics
    if result.benchmark_metrics is None:
        verdict = "no benchmark was supplied for comparison"
    elif m.excess_cagr > 0 and m.sharpe >= result.benchmark_metrics.sharpe:
        verdict = (
            f"**outperformed** the {result.benchmark.name} benchmark on both "
            f"CAGR ({m.excess_cagr:+.2%}) and risk-adjusted return"
        )
    elif m.excess_cagr > 0:
        verdict = (
            f"beat the benchmark on raw return ({m.excess_cagr:+.2%} CAGR) but not on a "
            f"risk-adjusted basis"
        )
    else:
        verdict = (
            f"**underperformed** the {result.benchmark.name} benchmark ({m.excess_cagr:+.2%} CAGR)"
        )
    return (
        f"Over the tested period the {result.strategy.name} strategy {verdict}. "
        f"It produced a {m.cagr:.2%} CAGR with a {m.max_drawdown:.2%} maximum drawdown and a "
        f"Sharpe ratio of {m.sharpe:.2f}. These figures are net of {m.cumulative_fees:,.0f} in "
        f"trading fees across {m.n_orders} orders. As always, past performance does not "
        f"guarantee future results."
    )
