# 📈 DCAToolBox

> A professional, extensible **quantitative research framework** for designing,
> backtesting and comparing **Dollar-Cost-Averaging (DCA)** investment strategies.

DCAToolBox is **not** a single trading strategy — it is a *research engine*. A
strategy is just an interchangeable module: adding a new one requires **zero
changes** to the backtest engine, the broker, the portfolio or the metrics. The
codebase is built to the standards of a bank quant team and designed to be
maintained for years.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen.svg)](tests/)

🌐 **Live interactive backtester:** https://anthonynadjari.github.io/DCAToolBox/ — change any
parameter (asset, dates, budget, threshold, allocation, signal, budget policy, fees…) and the
backtest **recomputes instantly in your browser** on real market data. Auto-deployed from `main`.

---

## Table of contents

- [Why DCAToolBox](#why-dcatoolbox)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Command-line interface](#command-line-interface)
- [Web interface](#web-interface)
- [Configuration](#configuration)
- [Strategies](#strategies)
- [Adding a new strategy](#adding-a-new-strategy)
- [Metrics](#metrics)
- [Anti-overfitting](#anti-overfitting)
- [Results](#results)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Why DCAToolBox

Most "DCA backtesters" hard-code one strategy. DCAToolBox inverts the design:
the **engine is generic** and strategies are plug-ins. This makes it possible to
test *hundreds* of strategy variations and rank them objectively against a single
benchmark — **MonthlyDCA** (invest the full monthly budget on a fixed day).

Core design principles:

- **Strict layer separation** — data, broker, portfolio, strategies, engine,
  metrics, optimization, reporting and UI never leak into one another.
- **SOLID, DRY, low coupling, high cohesion** — small classes, single
  responsibilities, dependency injection.
- **No look-ahead bias** — by construction a strategy only ever receives data up
  to and including the current bar.
- **Provider-agnostic** — switching from Yahoo Finance to a CSV file or Bloomberg
  is a one-line config change.
- **Fully typed, documented and tested** — 96% test coverage, ruff-clean.

## Features

- 🔌 **Pluggable strategies** via a self-registering registry.
- 🧱 **Interchangeable dip-detection signals** (open-vs-open, close-vs-close,
  drawdown over N days, cumulative return, …).
- 🏦 **Realistic simulated broker** with fees, slippage and a trade journal.
- 📊 **Comprehensive metrics** (CAGR, Sharpe, Sortino, Calmar, max drawdown,
  XIRR, tracking error, information ratio, …) grouped in one dedicated class.
- 🔭 **Parallel grid-search optimizer** (joblib) with automatic ranking.
- 🛡️ **Anti-overfitting** train / validation / test evaluation, always reported
  separately.
- 📈 **Interactive Plotly charts** and **Markdown / HTML / PDF reports**.
- 🖥️ **Typer CLI** and a **Streamlit web UI** usable with zero programming
  knowledge.
- 🌐 **In-browser live backtester** (GitHub Pages): a dependency-free JavaScript
  engine that is **parity-tested against the Python framework** (`web/engine.test.mjs`),
  so what you tweak in the browser matches the real engine to the last decimal.
- 🧪 **Deterministic synthetic provider** so everything runs and tests offline.

## Architecture

```
dcatoolbox/
├── config/          # Pydantic settings, enums, YAML/JSON (de)serialisation
├── data/            # MarketData model, cache, validation
│   └── providers/   # MarketDataProvider ABC + Yahoo / CSV / Bloomberg / Synthetic
├── broker/          # Order/Trade objects + SimulatedBroker (fees, slippage)
├── portfolio/       # Position + Portfolio (cash, history, contributions)
├── strategies/      # Strategy ABC, registry, MonthlyDCA, DipBuying, RSI, MA…
│   └── signals/     # Interchangeable dip-detection modules
├── backtesting/     # MarketContext, generic BacktestEngine, runner, results
├── metrics/         # PerformanceMetrics + return/XIRR analytics
├── optimization/    # GridSearchOptimizer + train/val/test splitter
├── visualization/   # Plotly charts + figure export
├── reports/         # Markdown / HTML / PDF generators
└── utils/           # logging, calendar, decorators
main.py              # Typer CLI
app.py               # Streamlit web UI
tests/               # pytest suite (96% coverage)
examples/            # quickstart script + example config
```

**Data flow:** `DataService` (provider + cache + validation) → `MarketData` →
`BacktestEngine` walks the calendar → hands each bar's `MarketContext` to the
`Strategy` → orders go to the `SimulatedBroker` → fills update the `Portfolio` →
`PerformanceMetrics` analyses the daily history → `visualization` / `reports`
present it.

The engine depends only on the abstract `Strategy` interface — it never imports a
concrete strategy. `DipBuyingStrategy` is just one registry entry among many.

## Installation

Requires **Python 3.12+**.

```bash
git clone https://github.com/AnthonyNadjari/DCAToolBox.git
cd DCAToolBox

# Core install
pip install -e .

# With the web UI and report extras, plus dev tools
pip install -e ".[web,report,dev]"
```

Or just the runtime dependencies:

```bash
pip install -r requirements.txt
```

## Quick start

```python
from datetime import date
from dcatoolbox.backtesting import run_backtest
from dcatoolbox.config.enums import ProviderType
from dcatoolbox.config.settings import BacktestConfig, DataConfig, StrategyConfig

config = BacktestConfig(
    data=DataConfig(provider=ProviderType.YAHOO, tickers=["SPY"],
                    start=date(2010, 1, 1), end=date(2026, 1, 1)),
    strategy=StrategyConfig(name="dip_buying",
                            params={"threshold": 0.02, "allocation": 0.25}),
    benchmark=StrategyConfig(name="monthly_dca"),
    monthly_budget=1000.0, day_of_month=26,
)

result = run_backtest(config)
print(result.comparison_frame().round(4))
```

Run the bundled offline example:

```bash
python examples/quickstart.py
```

## Command-line interface

```bash
python main.py strategies                       # list registered strategies
python main.py download-data --ticker SPY       # fetch & cache data
python main.py run --ticker SPY --strategy dip_buying --threshold 0.02
python main.py optimize --ticker SPY --splits   # grid search + train/val/test
python main.py report  --ticker SPY --format html --output reports_output/r.html
```

Every command accepts `--provider synthetic` to run fully offline.

## Web interface

```bash
streamlit run app.py
```

The dashboard lets a **non-programmer**:

- pick one or several ETFs and a date range,
- configure every parameter (budget, threshold, allocation, fees, slippage, DCA
  day, signal method, …),
- run a backtest or a grid-search optimization in one click,
- compare several strategies side by side,
- view all interactive charts,
- export results as **CSV / HTML / PDF / Markdown**,
- save and reload configurations.

## Configuration

Everything is a validated Pydantic model and can be saved/loaded as YAML or JSON
(see [`examples/example_config.yaml`](examples/example_config.yaml)):

```python
from dcatoolbox.config.io import load_config, save_config
config = load_config("examples/example_config.yaml")
save_config(config, "my_run.yaml")
```

| Setting | Where | Default |
|---|---|---|
| Provider | `data.provider` | `yahoo` |
| Tickers | `data.tickers` | `["SPY"]` |
| Date range | `data.start` / `data.end` | 2010 → 2026 |
| Frequency | `data.frequency` | `daily` |
| Fees | `broker.fee_rate` | `0.005` (0.50%) |
| Slippage | `broker.slippage_rate` | `0.0005` (0.05%) |
| Monthly budget | `monthly_budget` | `1000` |
| DCA day | `day_of_month` | `26` |
| Strategy + params | `strategy` | `dip_buying` |
| Benchmark | `benchmark` | `monthly_dca` |

## Strategies

| Name | Description |
|---|---|
| `monthly_dca` | **Benchmark.** Invests 100% of the monthly budget on the scheduled day. |
| `dip_buying` | Deploys a fraction of the remaining budget on each detected dip; sweeps the rest on the scheduled day. |
| `rsi` | Buys into oversold conditions (RSI below a threshold). |
| `moving_average` | Buys when price trades below its moving average by a margin. |

**Dip-detection signals** (interchangeable via `signal_method`): `open_vs_open`,
`close_vs_close`, `open_vs_close`, `close_vs_open`, `drawdown_n_days`,
`cumulative_return`.

**Budget policy** (`budget_policy`, for the deploying strategies):

- `reset` (default) — any cash left on the scheduled day is fully invested, so
  each month's budget is always deployed (matches the original DCA mandate).
- `accumulate` — unspent cash carries over to hunt for larger, rarer dips (a true
  "buy the dip" mandate). This is what makes a dip strategy meaningfully diverge
  from the benchmark instead of just front-running the monthly purchase.

### Live in-browser backtester

`web/` contains a self-contained JavaScript port of the engine (`web/engine.js`)
plus an interactive UI (`web/index.html`, `web/app.js`). `scripts/build_site.py`
bundles real market data to JSON (`scripts/bundle_data.py`) and assembles the
static site that GitHub Pages serves. Numerical fidelity is enforced by a parity
test (`scripts/gen_golden.py` → `web/engine.test.mjs`) that runs in CI: the JS
engine must match the Python engine on every metric across many configurations.

## Adding a new strategy

Drop one self-contained file and decorate the class — **no engine changes**:

```python
from dcatoolbox.strategies.budget_deployment import BudgetDeploymentStrategy, Signal
from dcatoolbox.strategies.registry import register_strategy

@register_strategy
class MyStrategy(BudgetDeploymentStrategy):
    name = "my_strategy"

    def _configure(self) -> None:
        self.lookback = int(self.params.get("lookback", 10))

    def _signal(self, context) -> Signal:
        history = context.history
        fired = history["close"].iloc[-1] < history["close"].iloc[-self.lookback:].mean()
        return (fired, "close")
```

It is now available to the CLI, the optimizer and the web UI automatically.

## Metrics

All metrics live in the single `PerformanceMetrics` class: total return, CAGR,
annualised return & volatility, Sharpe, Sortino, Calmar, maximum drawdown, time
under water, rolling drawdown/return, IRR, XIRR, tracking error, information
ratio, number of orders, average order amount, average buy price, average cash,
cumulative fees, and performance vs benchmark. Returns are **time-weighted** so
that monthly contributions do not distort risk statistics.

## Anti-overfitting

The optimizer never reports a single global number. It fits parameters on the
**train** window and reports performance **separately** on validation and test:

```bash
python main.py optimize --ticker SPY --start 2000-01-01 --end 2026-01-01 --splits
```

```python
from dcatoolbox.optimization import GridSearchOptimizer, default_split
opt = GridSearchOptimizer(config)
evaluation = opt.evaluate_splits(market, default_split(2000, 2026))
print(evaluation.per_window)   # one row per train / validation / test
```

## Results

Example comparison (deterministic synthetic data, 2017–2021):

| Metric | dip_buying | monthly_dca |
|---|---|---|
| Total return | 76.36% | 76.18% |
| CAGR | 26.95% | 26.93% |
| Sharpe | 1.27 | 1.28 |
| Max drawdown | -12.61% | -12.53% |
| Number of orders | 81 | 49 |
| Excess total return | +0.18% | — |

> ⚠️ Figures are illustrative (synthetic data). Past performance does not
> guarantee future results. This project is for research and education only and
> is **not** investment advice.

### Captures

Generate an interactive HTML report (equity curve, drawdown, cash, fees, buy
signals, purchase distribution, …):

```bash
python main.py report --provider synthetic --format html --output reports_output/report.html
```

## Roadmap

Built to absorb these without touching the engine:

- [ ] Bollinger Bands strategy
- [ ] Volatility / VIX strategies
- [ ] Multi-ETF allocation strategy
- [ ] Momentum & mean-reversion strategies
- [ ] Dynamic cash / crash-buying strategies
- [ ] Walk-forward optimization
- [ ] Live Bloomberg provider implementation
- [ ] Plugin entry points for third-party strategies

## FAQ

**Does it require an internet connection?** No. The deterministic
`synthetic` provider runs everything (including the full test suite) offline.

**How do I use my own data?** Set `provider: csv` and `csv_dir`, with one
`<TICKER>.csv` file per instrument.

**Is there look-ahead bias?** No. Strategies receive a `MarketContext` whose
history is truncated at the current bar; orders execute against current-bar
prices only.

**Can I test hundreds of strategies?** Yes — that is the whole point. Register
them and grid-search across parameters in parallel.

## Contributing

Contributions are welcome! Please:

1. Keep the layer separation intact (no strategy-specific code in the engine).
2. Add type hints and docstrings everywhere.
3. Keep functions short and avoid duplication.
4. Run the quality gate before submitting:

```bash
ruff check . && ruff format --check . && pytest --cov=dcatoolbox
```

## License

[MIT](LICENSE) © 2026 Anthony Nadjari
