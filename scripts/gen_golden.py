"""Generate golden backtest results from the Python engine for JS parity tests.

Produces, under ``web/.parity/``:

* ``data_<dataset>.json`` -- the exact OHLC(V) series each case ran on,
* ``cases.json``          -- the configurations (in the JS engine's shape),
* ``golden.json``         -- the scalar metrics the Python engine produced.

Covers both daily and intraday (hourly) frequencies so the in-browser engine is
guaranteed to match the framework at every granularity. The Node test
``web/engine.test.mjs`` replays the same data and cases and asserts equality.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dcatoolbox.backtesting.engine import periods_per_year
from dcatoolbox.backtesting.runner import run_backtest
from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import (
    BacktestConfig,
    BrokerConfig,
    DataConfig,
    StrategyConfig,
)
from dcatoolbox.data.factory import DataService

OUT = Path("web/.parity")

DATASETS = {
    "daily": DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2010, 1, 1),
        end=date(2024, 1, 1),
        frequency=Frequency.DAILY,
        use_cache=False,
    ),
    "hourly": DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2022, 1, 1),
        end=date(2024, 1, 1),
        frequency=Frequency.HOURLY,
        use_cache=False,
    ),
}

# Each case is in the JS engine's config shape; "dataset" selects the series.
CASES: list[dict] = [
    {"strategy": {"name": "monthly_dca"}},
    {
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.02,
            "allocation": 0.25,
            "signalMethod": "open_vs_open",
        }
    },
    {
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.03,
            "allocation": 0.5,
            "signalMethod": "close_vs_close",
        }
    },
    {
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.02,
            "allocation": 0.4,
            "signalMethod": "drawdown_n_days",
            "signalWindow": 20,
            "budgetPolicy": "accumulate",
        }
    },
    {
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.05,
            "allocation": 0.3,
            "signalMethod": "cumulative_return",
            "signalWindow": 5,
        }
    },
    {"strategy": {"name": "rsi", "allocation": 0.5, "period": 14, "oversold": 35}},
    {"strategy": {"name": "moving_average", "allocation": 0.4, "window": 50, "margin": 0.02}},
    {
        "strategy": {"name": "dip_buying", "threshold": 0.02, "allocation": 0.25},
        "feeRate": 0.0,
        "slippageRate": 0.0,
    },
    {
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.02,
            "allocation": 0.4,
            "signalMethod": "cumulative_return",
            "signalWindow": 5,
            "budgetPolicy": "accumulate",
        }
    },
    # Intraday (hourly) parity: signals fire bar-over-bar within the day.
    {"dataset": "hourly", "strategy": {"name": "monthly_dca"}},
    {
        "dataset": "hourly",
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.005,
            "allocation": 0.25,
            "signalMethod": "close_vs_close",
        },
    },
    {
        "dataset": "hourly",
        "strategy": {
            "name": "dip_buying",
            "threshold": 0.01,
            "allocation": 0.5,
            "signalMethod": "drawdown_n_days",
            "signalWindow": 14,
            "budgetPolicy": "accumulate",
        },
    },
]

_BASE = {
    "monthlyBudget": 1000.0,
    "dayOfMonth": 26,
    "initialCash": 0.0,
    "riskFreeRate": 0.02,
    "feeRate": 0.005,
    "slippageRate": 0.0005,
    "minFee": 0.0,
    "benchmark": {"name": "monthly_dca"},
}


def _to_backtest_config(case: dict, data_cfg: DataConfig) -> BacktestConfig:
    """Translate a JS-shaped case into a Python :class:`BacktestConfig`."""
    s = case["strategy"]
    keymap = {
        "threshold": "threshold",
        "allocation": "allocation",
        "signalMethod": "signal_method",
        "signalWindow": "signal_window",
        "budgetPolicy": "budget_policy",
        "period": "period",
        "oversold": "oversold",
        "window": "window",
        "margin": "margin",
    }
    params = {py: s[js] for js, py in keymap.items() if js in s}
    return BacktestConfig(
        data=data_cfg,
        broker=BrokerConfig(
            fee_rate=case.get("feeRate", _BASE["feeRate"]),
            slippage_rate=case.get("slippageRate", _BASE["slippageRate"]),
        ),
        strategy=StrategyConfig(name=s["name"], params=params),
        benchmark=StrategyConfig(name="monthly_dca"),
        monthly_budget=_BASE["monthlyBudget"],
        day_of_month=_BASE["dayOfMonth"],
        risk_free_rate=_BASE["riskFreeRate"],
    )


def _series_json(data_cfg: DataConfig) -> dict:
    """Load a dataset and serialise it in the shape the JS engine consumes."""
    frame = DataService(data_cfg).load("SPY").frame
    fmt = "%Y-%m-%d" if data_cfg.frequency is Frequency.DAILY else "%Y-%m-%dT%H:%M"
    return {
        "ticker": "SPY",
        "dates": [d.strftime(fmt) for d in frame.index],
        "open": frame["open"].tolist(),
        "high": frame["high"].tolist(),
        "low": frame["low"].tolist(),
        "close": frame["close"].tolist(),
    }


def main() -> None:
    """Generate data/cases/golden artefacts for the JS parity test."""
    OUT.mkdir(parents=True, exist_ok=True)
    markets, ppy = {}, {}
    for name, cfg in DATASETS.items():
        (OUT / f"data_{name}.json").write_text(json.dumps(_series_json(cfg)), encoding="utf-8")
        markets[name] = {"SPY": DataService(cfg).load("SPY")}
        ppy[name] = periods_per_year(cfg.frequency)

    cases_out, golden_out = [], []
    for case in CASES:
        dataset = case.get("dataset", "daily")
        cfg = _to_backtest_config(case, DATASETS[dataset])
        result = run_backtest(cfg, market=markets[dataset])
        cases_out.append(
            {
                **_BASE,
                **case,
                "dataset": dataset,
                "periodsPerYear": ppy[dataset],
                "start": None,
                "end": None,
            }
        )
        golden_out.append(result.strategy_metrics.as_dict())

    (OUT / "cases.json").write_text(json.dumps(cases_out, indent=2), encoding="utf-8")
    (OUT / "golden.json").write_text(json.dumps(golden_out, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases_out)} parity cases ({len(DATASETS)} datasets) to {OUT}/")


if __name__ == "__main__":
    main()
