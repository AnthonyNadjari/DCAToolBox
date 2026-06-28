"""Generate golden backtest results from the Python engine for JS parity tests.

Produces, under ``web/.parity/``:

* ``data.json``    -- the exact OHLCV series the Python engine ran on,
* ``cases.json``   -- the list of configurations (in the JS engine's shape),
* ``golden.json``  -- the scalar metrics the Python engine produced per case.

The Node test ``web/engine.test.mjs`` replays the same data and cases through the
JavaScript engine and asserts the metrics match within tolerance. This is what
guarantees the in-browser engine never silently diverges from the framework.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dcatoolbox.backtesting.runner import run_backtest
from dcatoolbox.config.enums import ProviderType
from dcatoolbox.config.settings import (
    BacktestConfig,
    BrokerConfig,
    DataConfig,
    StrategyConfig,
)
from dcatoolbox.data.factory import DataService

OUT = Path("web/.parity")

# Each case is expressed in the JS engine's config shape; we translate it to a
# BacktestConfig below so both engines see identical inputs.
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
    # Exposes the cumulative_return boundary: with the accumulate policy the
    # scheduled-day sweep no longer masks a missed signal at i == window.
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
    params = {
        k: v
        for k, v in {
            "threshold": s.get("threshold"),
            "allocation": s.get("allocation"),
            "signal_method": s.get("signalMethod"),
            "signal_window": s.get("signalWindow"),
            "budget_policy": s.get("budgetPolicy"),
            "period": s.get("period"),
            "oversold": s.get("oversold"),
            "window": s.get("window"),
            "margin": s.get("margin"),
        }.items()
        if v is not None
    }
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


def main() -> None:
    """Generate data/cases/golden artefacts for the JS parity test."""
    OUT.mkdir(parents=True, exist_ok=True)
    data_cfg = DataConfig(
        provider=ProviderType.SYNTHETIC,
        tickers=["SPY"],
        start=date(2010, 1, 1),
        end=date(2024, 1, 1),
        use_cache=False,
    )
    market = {"SPY": DataService(data_cfg).load("SPY")}
    frame = market["SPY"].frame
    data_json = {
        "ticker": "SPY",
        "dates": [d.strftime("%Y-%m-%d") for d in frame.index],
        "open": frame["open"].tolist(),
        "high": frame["high"].tolist(),
        "low": frame["low"].tolist(),
        "close": frame["close"].tolist(),
        "volume": frame["volume"].tolist(),
    }
    (OUT / "data.json").write_text(json.dumps(data_json), encoding="utf-8")

    cases_out, golden_out = [], []
    for case in CASES:
        cfg = _to_backtest_config(case, data_cfg)
        result = run_backtest(cfg, market=market)
        js_case = {**_BASE, **case, "start": None, "end": None}
        cases_out.append(js_case)
        golden_out.append(result.strategy_metrics.as_dict())

    (OUT / "cases.json").write_text(json.dumps(cases_out, indent=2), encoding="utf-8")
    (OUT / "golden.json").write_text(json.dumps(golden_out, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases_out)} parity cases to {OUT}/")


if __name__ == "__main__":
    main()
