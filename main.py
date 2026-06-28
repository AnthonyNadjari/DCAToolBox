"""DCAToolBox command-line interface.

Examples:
    python main.py strategies
    python main.py download-data --ticker SPY --provider yahoo
    python main.py run --ticker SPY --strategy dip_buying --threshold 0.02
    python main.py optimize --ticker SPY --splits
    python main.py report --ticker SPY --format html --output reports_output/report.html
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dcatoolbox.backtesting.runner import load_market, run_backtest
from dcatoolbox.config.enums import Frequency, ProviderType, ReportFormat
from dcatoolbox.config.io import load_config
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
from dcatoolbox.strategies.registry import STRATEGY_REGISTRY, available_strategies
from dcatoolbox.utils.logging import configure_logging
from dcatoolbox.visualization import save_figures
from dcatoolbox.visualization.charts import build_dashboard

app = typer.Typer(add_completion=False, help="Quantitative research toolbox for DCA strategies.")
console = Console()


def _parse_date(value: str) -> date:
    """Parse an ISO ``YYYY-MM-DD`` string into a :class:`date`."""
    return date.fromisoformat(value)


def _make_config(
    *,
    config_path: Path | None,
    ticker: str,
    provider: ProviderType,
    strategy: str,
    start: str,
    end: str,
    budget: float,
    day: int,
    fee: float,
    slippage: float,
    threshold: float | None,
    allocation: float | None,
) -> BacktestConfig:
    """Build a config from a file or from individual CLI options."""
    if config_path is not None:
        return load_config(config_path)
    params: dict[str, float] = {}
    if threshold is not None:
        params["threshold"] = threshold
    if allocation is not None:
        params["allocation"] = allocation
    return BacktestConfig(
        data=DataConfig(
            provider=provider,
            tickers=[ticker],
            start=_parse_date(start),
            end=_parse_date(end),
        ),
        broker=BrokerConfig(fee_rate=fee, slippage_rate=slippage),
        strategy=StrategyConfig(name=strategy, params=params),
        monthly_budget=budget,
        day_of_month=day,
    )


def _render_metrics(result) -> None:
    """Pretty-print the strategy/benchmark metrics comparison to the console."""
    frame = metrics_table(result)
    table = Table(title="Performance metrics", show_lines=False)
    table.add_column("Metric", style="bold")
    for column in frame.columns:
        table.add_column(str(column), justify="right")
    for metric, row in frame.iterrows():
        table.add_row(str(metric), *[str(v) for v in row.values])
    console.print(table)


@app.command()
def strategies() -> None:
    """List all registered strategies."""
    table = Table(title="Registered strategies")
    table.add_column("Name", style="bold cyan")
    table.add_column("Class")
    for name in available_strategies():
        table.add_row(name, STRATEGY_REGISTRY[name].__name__)
    console.print(table)


@app.command("download-data")
def download_data(
    ticker: str = typer.Option("SPY", help="Ticker symbol to download."),
    provider: ProviderType = typer.Option(ProviderType.YAHOO, help="Data provider."),
    start: str = typer.Option("2010-01-01", help="Start date (YYYY-MM-DD)."),
    end: str = typer.Option("2026-01-01", help="End date (YYYY-MM-DD)."),
    frequency: Frequency = typer.Option(Frequency.DAILY, help="Bar frequency."),
    log_level: str = typer.Option("INFO", help="Logging level."),
) -> None:
    """Download and cache market data for a ticker."""
    configure_logging(log_level)
    config = DataConfig(
        provider=provider,
        tickers=[ticker],
        start=_parse_date(start),
        end=_parse_date(end),
        frequency=frequency,
    )
    market = load_market(BacktestConfig(data=config))
    for symbol, data in market.items():
        console.print(
            f"[green]{symbol}[/green]: {len(data)} rows ({data.start.date()} to {data.end.date()})"
        )


@app.command()
def run(
    config: Path | None = typer.Option(None, help="Load a saved config file."),
    ticker: str = typer.Option("SPY"),
    provider: ProviderType = typer.Option(ProviderType.YAHOO),
    strategy: str = typer.Option("dip_buying"),
    start: str = typer.Option("2010-01-01"),
    end: str = typer.Option("2026-01-01"),
    budget: float = typer.Option(1000.0),
    day: int = typer.Option(26),
    fee: float = typer.Option(0.005),
    slippage: float = typer.Option(0.0005),
    threshold: float | None = typer.Option(None),
    allocation: float | None = typer.Option(None),
    charts_dir: Path | None = typer.Option(None, help="Save interactive charts here."),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Run a single backtest of a strategy against the benchmark."""
    configure_logging(log_level)
    cfg = _make_config(
        config_path=config,
        ticker=ticker,
        provider=provider,
        strategy=strategy,
        start=start,
        end=end,
        budget=budget,
        day=day,
        fee=fee,
        slippage=slippage,
        threshold=threshold,
        allocation=allocation,
    )
    result = run_backtest(cfg)
    _render_metrics(result)
    if charts_dir is not None:
        paths = save_figures(build_dashboard(result), charts_dir)
        console.print(f"[green]Saved {len(paths)} charts to {charts_dir}[/green]")


@app.command()
def optimize(
    ticker: str = typer.Option("SPY"),
    provider: ProviderType = typer.Option(ProviderType.YAHOO),
    strategy: str = typer.Option("dip_buying"),
    start: str = typer.Option("2010-01-01"),
    end: str = typer.Option("2026-01-01"),
    metric: str = typer.Option("sharpe", help="Metric to rank by."),
    n_jobs: int = typer.Option(-1, help="Parallel workers (-1 = all cores)."),
    splits: bool = typer.Option(False, help="Also run train/validation/test evaluation."),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Grid-search a strategy's parameters and rank the results."""
    configure_logging(log_level)
    cfg = BacktestConfig(
        data=DataConfig(
            provider=provider, tickers=[ticker], start=_parse_date(start), end=_parse_date(end)
        ),
        strategy=StrategyConfig(name=strategy),
    )
    market = load_market(cfg)
    optimizer = GridSearchOptimizer(cfg, OptimizationConfig(rank_metric=metric, n_jobs=n_jobs))
    result = optimizer.run(market)
    console.print(result.leaderboard(10).round(4).to_string())
    if splits:
        years = (_parse_date(start).year, _parse_date(end).year)
        evaluation = optimizer.evaluate_splits(market, default_split(*years))
        console.print("\n[bold]Best params:[/bold]", evaluation.best_params)
        console.print(
            evaluation.per_window[["cagr", "sharpe", "max_drawdown", "total_return"]]
            .round(4)
            .to_string()
        )


@app.command()
def report(
    ticker: str = typer.Option("SPY"),
    provider: ProviderType = typer.Option(ProviderType.YAHOO),
    strategy: str = typer.Option("dip_buying"),
    start: str = typer.Option("2010-01-01"),
    end: str = typer.Option("2026-01-01"),
    fmt: ReportFormat = typer.Option(ReportFormat.HTML, "--format", help="Report format."),
    output: Path = typer.Option(Path("reports_output/report.html")),
    log_level: str = typer.Option("INFO"),
) -> None:
    """Run a backtest and generate a Markdown/HTML/PDF report."""
    configure_logging(log_level)
    cfg = BacktestConfig(
        data=DataConfig(
            provider=provider, tickers=[ticker], start=_parse_date(start), end=_parse_date(end)
        ),
        strategy=StrategyConfig(name=strategy),
    )
    result = run_backtest(cfg)
    path = ReportGenerator(result).generate(fmt, output)
    console.print(f"[green]Report written to {path}[/green]")


if __name__ == "__main__":
    app()
