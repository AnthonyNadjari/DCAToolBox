"""Research harness: evaluate strategy variants on REAL data with IS/OOS splits.

Loads the bundled real market JSONs from ``data_real/`` (downloaded from the
deployed site, source: Yahoo), runs a named grid of strategy configurations on
several markets, and writes one JSON result per run covering three segments:
in-sample (IS), out-of-sample (OOS) and the full period. The OOS segment starts
cold (no pre-split history), which handicaps every candidate equally.

Usage::

    PYTHONPATH=. python scripts/research.py --filter adaptive --out results.json
    PYTHONPATH=. python scripts/research.py --list          # enumerate run ids
    PYTHONPATH=. python scripts/research.py --ids id1,id2   # run a subset
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from dcatoolbox.backtesting.engine import BacktestEngine
from dcatoolbox.config.enums import Frequency, ProviderType
from dcatoolbox.config.settings import BacktestConfig, BrokerConfig, DataConfig, StrategyConfig
from dcatoolbox.data.models import MarketData
from dcatoolbox.strategies import builtin  # noqa: F401 - registers strategies
from dcatoolbox.strategies.registry import build_strategy

DATA = Path("data_real")
_FEES = (0.005, 0.0005)  # (fee_rate, slippage) -- overridable via CLI for stress tests

# market name -> (tickers [primary first], IS range, OOS range)
MARKETS: dict[str, dict] = {
    "US": {
        "tickers": ["SPY", "QQQ"],
        "is": ("2000-01-01", "2014-12-31"),
        "oos": ("2015-01-01", "2026-12-31"),
    },
    "FR": {
        "tickers": ["ESE.PA", "PUST.PA"],
        "is": ("2014-06-01", "2020-12-31"),
        "oos": ("2021-01-01", "2026-12-31"),
    },
    "FR3": {
        "tickers": ["CW8.PA", "PUST.PA", "C40.PA"],
        "is": ("2014-06-01", "2020-12-31"),
        "oos": ("2021-01-01", "2026-12-31"),
    },
}


def load_series(ticker: str) -> pd.DataFrame:
    """Load one real series from ``data_real/`` as an OHLCV frame."""
    raw = json.loads((DATA / f"{ticker}.json").read_text())
    idx = pd.DatetimeIndex(pd.to_datetime(raw["dates"]), name="date")
    return pd.DataFrame(
        {
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": 1.0,
        },
        index=idx,
    )


def build_market(tickers: list[str], start: str, end: str) -> dict[str, MarketData]:
    """Slice every ticker to [start, end] and wrap as MarketData."""
    out = {}
    for t in tickers:
        frame = load_series(t).loc[start:end]
        out[t] = MarketData(ticker=t, frequency=Frequency.DAILY, frame=frame)
    return out


def experiments() -> list[dict]:
    """The full named run grid: baselines + adaptive momentum variants."""
    runs: list[dict] = []
    for mkt in MARKETS:
        primary = MARKETS[mkt]["tickers"][0]
        # -- baselines ---------------------------------------------------------
        runs.append({"id": f"{mkt}:dca", "market": mkt, "strategy": "monthly_dca", "params": {}})
        for t in MARKETS[mkt]["tickers"][1:]:
            runs.append(
                {
                    "id": f"{mkt}:dca_{t}",
                    "market": mkt,
                    "strategy": "monthly_dca",
                    "params": {},
                    "primary": t,  # DCA into the other asset (hindsight bar)
                }
            )
        for rotate in (False, True):
            runs.append(
                {
                    "id": f"{mkt}:rot126{'_switch' if rotate else ''}",
                    "market": mkt,
                    "strategy": "momentum_rotation",
                    "params": {"lookback": 126, "absolute": True, "rotate": rotate},
                }
            )
        # -- adaptive grid -----------------------------------------------------
        for check, hi, dip, rotate in itertools.product(
            (1, 5, 21), (0.05, 0.10, 0.15), (0.0, 0.10, 0.15), (False, True)
        ):
            runs.append(
                {
                    "id": f"{mkt}:ada_c{check}_h{int(hi * 100)}_d{int(dip * 100)}"
                    + ("_switch" if rotate else ""),
                    "market": mkt,
                    "strategy": "adaptive_momentum",
                    "params": {
                        "check_every": check,
                        "hi_threshold": hi,
                        "dip_boost": dip,
                        "rotate": rotate,
                        "lo_threshold": 0.0,
                    },
                }
            )
        _ = primary
    return runs


def run_one(exp: dict) -> dict:
    """Run one experiment over IS / OOS / FULL and return scalar metrics."""
    mkt = MARKETS[exp["market"]]
    tickers = list(mkt["tickers"])
    if exp.get("primary"):  # reorder so the requested ticker is primary
        tickers = [exp["primary"]] + [t for t in tickers if t != exp["primary"]]
    segments = {
        "is": mkt["is"],
        "oos": mkt["oos"],
        "full": (mkt["is"][0], mkt["oos"][1]),
    }
    out = {
        "id": exp["id"],
        "market": exp["market"],
        "strategy": exp["strategy"],
        "params": exp["params"],
    }
    for seg, (start, end) in segments.items():
        market = build_market(tickers, start, end)
        cfg = BacktestConfig(
            data=DataConfig(
                provider=ProviderType.SYNTHETIC,  # unused: market passed explicitly
                tickers=tickers,
                start=pd.Timestamp(start).date(),
                end=pd.Timestamp(end).date(),
                frequency=Frequency.DAILY,
                use_cache=False,
            ),
            broker=BrokerConfig(fee_rate=_FEES[0], slippage_rate=_FEES[1]),
            strategy=StrategyConfig(name=exp["strategy"], params=exp["params"]),
            benchmark=StrategyConfig(name="monthly_dca"),
            monthly_budget=1000.0,
            day_of_month=26,
            risk_free_rate=0.02,
        )
        engine = BacktestEngine(cfg)
        strategy = build_strategy(cfg.strategy)
        benchmark = build_strategy(StrategyConfig(name="monthly_dca"))
        result = engine.run(strategy, market, benchmark=benchmark)
        m = result.strategy_metrics.as_dict()
        b = result.benchmark_metrics.as_dict()
        out[seg] = {
            "final": round(m["final_value"], 0),
            "invested": round(m["invested_capital"], 0),
            "cagr": round(m["cagr"], 4),
            "xirr": round(m["xirr"], 4) if m["xirr"] == m["xirr"] else None,
            "sharpe": round(m["sharpe"], 3),
            "max_dd": round(m["max_drawdown"], 4),
            "orders": int(m["n_orders"]),
            "fees": round(m["cumulative_fees"], 0),
            "bench_final": round(b["final_value"], 0),
            "bench_cagr": round(b["cagr"], 4),
            "vs_dca_money": round(m["final_value"] / b["final_value"] - 1, 4),
        }
    return out


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default="", help="substring filter on run ids")
    ap.add_argument("--ids", default="", help="comma-separated exact run ids")
    ap.add_argument("--list", action="store_true", help="print run ids and exit")
    ap.add_argument("--out", default="", help="output JSON path (default stdout)")
    ap.add_argument("--fee", type=float, default=0.005, help="fee rate override (stress tests)")
    ap.add_argument("--slippage", type=float, default=0.0005, help="slippage override")
    ap.add_argument(
        "--oos-shift", type=int, default=0, help="shift the IS/OOS boundary by N months"
    )
    args = ap.parse_args()

    if args.oos_shift:
        for mkt in MARKETS.values():
            boundary = pd.Timestamp(mkt["oos"][0]) + pd.DateOffset(months=args.oos_shift)
            mkt["is"] = (mkt["is"][0], (boundary - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
            mkt["oos"] = (boundary.strftime("%Y-%m-%d"), mkt["oos"][1])
    global _FEES
    _FEES = (args.fee, args.slippage)

    runs = experiments()
    if args.ids:
        wanted = set(args.ids.split(","))
        runs = [r for r in runs if r["id"] in wanted]
    elif args.filter:
        runs = [r for r in runs if args.filter in r["id"]]
    if args.list:
        print("\n".join(r["id"] for r in runs))
        return

    results = []
    for i, exp in enumerate(runs):
        results.append(run_one(exp))
        print(f"[{i + 1}/{len(runs)}] {exp['id']} done", flush=True)
    payload = json.dumps(results, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload)
        print(f"wrote {args.out} ({len(results)} runs)")
    else:
        print(payload)


if __name__ == "__main__":
    main()
