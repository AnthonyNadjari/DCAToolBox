"""DCAToolBox interactive web interface (Streamlit).

Run with::

    streamlit run app.py

The UI lets a non-programmer select assets, configure every parameter, run
backtests and optimizations, compare strategies and export results -- all without
writing any code.
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from dcatoolbox.backtesting.runner import load_market, run_backtest
from dcatoolbox.config.enums import ProviderType, ReportFormat, SignalMethod
from dcatoolbox.config.io import save_config
from dcatoolbox.config.settings import (
    BacktestConfig,
    BrokerConfig,
    DataConfig,
    OptimizationConfig,
    StrategyConfig,
)
from dcatoolbox.optimization.grid_search import GridSearchOptimizer
from dcatoolbox.optimization.splitter import default_split
from dcatoolbox.reports.generator import ReportGenerator
from dcatoolbox.reports.text import metrics_table
from dcatoolbox.strategies.registry import available_strategies
from dcatoolbox.visualization import charts

st.set_page_config(page_title="DCAToolBox", page_icon="📈", layout="wide")


def _sidebar() -> BacktestConfig:
    """Render the sidebar controls and return the assembled configuration."""
    st.sidebar.title("📈 DCAToolBox")
    st.sidebar.caption("Research, build and compare DCA strategies.")

    uploaded = st.sidebar.file_uploader("Load configuration", type=["yaml", "yml", "json"])
    if uploaded is not None:
        tmp = io.BytesIO(uploaded.getvalue())
        st.session_state["loaded_config"] = load_config_from_bytes(tmp, uploaded.name)

    with st.sidebar.expander("Data", expanded=True):
        tickers = st.text_input("Tickers (comma-separated)", "SPY").upper()
        provider = st.selectbox(
            "Provider", list(ProviderType), index=list(ProviderType).index(ProviderType.SYNTHETIC)
        )
        start = st.date_input("Start", date(2015, 1, 1))
        end = st.date_input("End", date(2024, 1, 1))

    with st.sidebar.expander("Strategy", expanded=True):
        strategy = st.selectbox(
            "Strategy", available_strategies(), index=available_strategies().index("dip_buying")
        )
        threshold = st.slider("Dip threshold", 0.005, 0.10, 0.02, 0.005, format="%.3f")
        allocation = st.slider("Allocation per signal", 0.05, 1.0, 0.25, 0.05)
        signal_method = st.selectbox("Signal method", list(SignalMethod))

    with st.sidebar.expander("Plan & costs", expanded=False):
        budget = st.number_input("Monthly budget", min_value=1.0, value=1000.0, step=100.0)
        day = st.slider("Day of month", 1, 31, 26)
        fee = st.number_input("Fee rate", 0.0, 0.05, 0.005, 0.0005, format="%.4f")
        slippage = st.number_input("Slippage rate", 0.0, 0.05, 0.0005, 0.0005, format="%.4f")

    return BacktestConfig(
        data=DataConfig(
            provider=provider,
            tickers=[t.strip() for t in tickers.split(",") if t.strip()],
            start=start,
            end=end,
        ),
        broker=BrokerConfig(fee_rate=fee, slippage_rate=slippage),
        strategy=StrategyConfig(
            name=strategy,
            params={
                "threshold": threshold,
                "allocation": allocation,
                "signal_method": signal_method.value,
            },
        ),
        monthly_budget=budget,
        day_of_month=day,
    )


def load_config_from_bytes(buffer: io.BytesIO, name: str) -> BacktestConfig:
    """Parse an uploaded config file (helper to keep the sidebar tidy)."""
    import json

    import yaml

    text = buffer.read().decode("utf-8")
    payload = yaml.safe_load(text) if name.endswith((".yaml", ".yml")) else json.loads(text)
    return BacktestConfig.model_validate(payload)


def _metric_cards(result) -> None:
    """Show the headline metrics as Streamlit metric cards."""
    m = result.strategy_metrics
    cols = st.columns(5)
    cols[0].metric("CAGR", f"{m.cagr:.2%}")
    cols[1].metric(
        "Total return", f"{m.total_return:.2%}", f"{m.excess_total_return:+.2%} vs bench"
    )
    cols[2].metric("Sharpe", f"{m.sharpe:.2f}")
    cols[3].metric("Max drawdown", f"{m.max_drawdown:.2%}")
    cols[4].metric("Final value", f"{m.final_value:,.0f}")


def _render_backtest(config: BacktestConfig) -> None:
    """Run a single backtest and render its dashboard + exports."""
    with st.spinner("Loading data and running backtest..."):
        result = run_backtest(config)
    st.session_state["result"] = result
    _metric_cards(result)
    st.subheader("Metrics")
    st.dataframe(metrics_table(result), use_container_width=True)
    dashboard = charts.build_dashboard(result)
    for left, right in _pairs(list(dashboard.values())):
        c1, c2 = st.columns(2)
        c1.plotly_chart(left, use_container_width=True)
        if right is not None:
            c2.plotly_chart(right, use_container_width=True)
    _exports(result, config)


def _render_comparison(config: BacktestConfig, strategy_names: list[str]) -> None:
    """Run several strategies and overlay their equity curves and metrics."""
    equity = pd.DataFrame()
    rows = {}
    for name in strategy_names:
        variant = config.model_copy(
            update={"strategy": StrategyConfig(name=name, params=config.strategy.params)}
        )
        result = run_backtest(variant)
        equity[name] = result.strategy.history["total_value"]
        rows[name] = result.strategy_metrics.as_dict()
    equity["benchmark"] = run_backtest(config).benchmark.history["total_value"]
    st.subheader("Equity curves")
    st.line_chart(equity)
    st.subheader("Metrics comparison")
    st.dataframe(pd.DataFrame(rows).T, use_container_width=True)


def _render_optimization(config: BacktestConfig, metric: str) -> None:
    """Run a grid search with train/validation/test evaluation."""
    with st.spinner("Running grid search..."):
        market = load_market(config)
        optimizer = GridSearchOptimizer(config, OptimizationConfig(rank_metric=metric, n_jobs=1))
        result = optimizer.run(market)
        evaluation = optimizer.evaluate_splits(
            market, default_split(config.data.start.year, config.data.end.year)
        )
    st.subheader("Leaderboard")
    st.dataframe(result.leaderboard(15), use_container_width=True)
    if {"threshold", "allocation"}.issubset(result.results.columns):
        st.plotly_chart(
            charts.optimization_heatmap(result, "threshold", "allocation"), use_container_width=True
        )
    st.subheader("Train / Validation / Test (anti-overfitting)")
    st.caption(f"Best params: {evaluation.best_params}")
    st.dataframe(
        evaluation.per_window[["cagr", "sharpe", "max_drawdown", "total_return"]],
        use_container_width=True,
    )


def _exports(result, config: BacktestConfig) -> None:
    """Render download buttons for CSV / Markdown / HTML / PDF / config."""
    st.subheader("Export")
    gen = ReportGenerator(result)
    cols = st.columns(5)
    cols[0].download_button(
        "CSV (history)", result.strategy.history.to_csv(), "history.csv", "text/csv"
    )
    cols[1].download_button("Markdown", gen.to_markdown(), "report.md", "text/markdown")
    cols[2].download_button("HTML", gen.to_html(), "report.html", "text/html")
    import tempfile
    from pathlib import Path

    pdf_path = Path(tempfile.gettempdir()) / "dcatoolbox_report.pdf"
    gen.generate(ReportFormat.PDF, pdf_path)
    cols[3].download_button("PDF", pdf_path.read_bytes(), "report.pdf", "application/pdf")
    cfg_path = Path(tempfile.gettempdir()) / "dcatoolbox_config.yaml"
    save_config(config, cfg_path)
    cols[4].download_button("Config (YAML)", cfg_path.read_text(), "config.yaml", "text/yaml")


def _pairs(items: list) -> list[tuple]:
    """Group a list into consecutive pairs, padding the last with ``None``."""
    return [
        (items[i], items[i + 1] if i + 1 < len(items) else None) for i in range(0, len(items), 2)
    ]


def main() -> None:
    """Application entry point."""
    config = _sidebar()
    st.title("DCA Strategy Research Dashboard")
    tab_run, tab_compare, tab_optimize = st.tabs(["🚀 Backtest", "⚖️ Compare", "🔧 Optimize"])

    with tab_run:
        if st.button("Run backtest", type="primary"):
            _render_backtest(config)

    with tab_compare:
        chosen = st.multiselect(
            "Strategies to compare", available_strategies(), default=["dip_buying", "monthly_dca"]
        )
        if st.button("Compare strategies") and chosen:
            _render_comparison(config, chosen)

    with tab_optimize:
        metric = st.selectbox("Rank metric", ["sharpe", "cagr", "calmar", "total_return"])
        if st.button("Run optimization"):
            _render_optimization(config, metric)


if __name__ == "__main__":
    main()
