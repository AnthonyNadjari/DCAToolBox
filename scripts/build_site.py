"""Build the static GitHub Pages site for DCAToolBox.

Generates, into the ``site/`` directory:

* ``index.html``  -- a landing page with the headline metrics and links,
* ``report.html`` -- the full interactive backtest report,
* one HTML file per dashboard chart.

The demo uses the deterministic synthetic provider so the build is reproducible
and needs no network access (Yahoo Finance is often unreachable from CI).

Run locally with::

    python scripts/build_site.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from dcatoolbox.backtesting import run_backtest
from dcatoolbox.config.enums import ProviderType, ReportFormat
from dcatoolbox.config.settings import BacktestConfig, DataConfig, StrategyConfig
from dcatoolbox.reports.generator import ReportGenerator
from dcatoolbox.reports.text import auto_conclusion
from dcatoolbox.visualization import charts, save_figures

SITE_DIR = Path("site")

_INDEX_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DCAToolBox</title>
<style>
 :root {{ --blue:#2563eb; }}
 * {{ box-sizing: border-box; }}
 body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin:0;
        color:#0f172a; background:#f8fafc; }}
 header {{ background:linear-gradient(135deg,#1e3a8a,#2563eb); color:#fff;
          padding:4rem 1.5rem; text-align:center; }}
 header h1 {{ font-size:3rem; margin:0; }}
 header p {{ font-size:1.2rem; opacity:.9; max-width:680px; margin:1rem auto 0; }}
 main {{ max-width:1000px; margin:0 auto; padding:2rem 1.5rem; }}
 .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
          gap:1rem; margin:2rem 0; }}
 .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px;
         padding:1.2rem; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,.05); }}
 .card .v {{ font-size:1.8rem; font-weight:700; color:var(--blue); }}
 .card .k {{ color:#64748b; font-size:.85rem; margin-top:.3rem; }}
 .btn {{ display:inline-block; background:var(--blue); color:#fff; text-decoration:none;
        padding:.8rem 1.5rem; border-radius:8px; margin:.3rem; font-weight:600; }}
 .btn.secondary {{ background:#fff; color:var(--blue); border:1px solid var(--blue); }}
 .note {{ color:#64748b; font-size:.85rem; margin-top:2rem; }}
 footer {{ text-align:center; color:#94a3b8; padding:2rem; font-size:.85rem; }}
</style></head><body>
<header>
  <h1>📈 DCAToolBox</h1>
  <p>An extensible quantitative research framework for designing, backtesting and
     comparing Dollar-Cost-Averaging strategies.</p>
</header>
<main>
  <h2>Live demo backtest</h2>
  <p>{strategy} vs the MonthlyDCA benchmark, {start}&ndash;{end} (synthetic data).</p>
  <div class="cards">
    <div class="card"><div class="v">{cagr}</div><div class="k">CAGR</div></div>
    <div class="card"><div class="v">{total}</div><div class="k">Total return</div></div>
    <div class="card"><div class="v">{sharpe}</div><div class="k">Sharpe</div></div>
    <div class="card"><div class="v">{mdd}</div><div class="k">Max drawdown</div></div>
    <div class="card"><div class="v">{orders}</div><div class="k">Orders</div></div>
  </div>
  <p>{conclusion}</p>
  <p>
    <a class="btn" href="report.html">📊 Full interactive report</a>
    <a class="btn secondary"
       href="https://github.com/AnthonyNadjari/DCAToolBox">⭐ Source on GitHub</a>
  </p>
  <h2>Charts</h2>
  <p>{chart_links}</p>
  <p class="note">⚠️ Figures use deterministic synthetic data and are for
     illustration only. This is research/education software, not investment advice.</p>
</main>
<footer>Generated automatically by DCAToolBox &middot; MIT License</footer>
</body></html>"""


def _demo_config() -> BacktestConfig:
    """The configuration used for the public demo backtest."""
    return BacktestConfig(
        data=DataConfig(
            provider=ProviderType.SYNTHETIC,
            tickers=["SPY"],
            start=date(2010, 1, 1),
            end=date(2024, 1, 1),
        ),
        strategy=StrategyConfig(
            name="dip_buying",
            params={"threshold": 0.02, "allocation": 0.25, "signal_method": "open_vs_open"},
        ),
        benchmark=StrategyConfig(name="monthly_dca"),
        monthly_budget=1000.0,
        day_of_month=26,
    )


def build() -> Path:
    """Generate the full static site and return the output directory."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    config = _demo_config()
    result = run_backtest(config)

    dashboard = charts.build_dashboard(result)
    save_figures(dashboard, SITE_DIR)
    ReportGenerator(result, figures=dashboard).generate(ReportFormat.HTML, SITE_DIR / "report.html")

    chart_links = " &middot; ".join(
        f'<a href="{name}.html">{name.replace("_", " ")}</a>' for name in dashboard
    )
    m = result.strategy_metrics
    (SITE_DIR / "index.html").write_text(
        _INDEX_TEMPLATE.format(
            strategy=result.strategy.name,
            start=config.data.start,
            end=config.data.end,
            cagr=f"{m.cagr:.1%}",
            total=f"{m.total_return:.1%}",
            sharpe=f"{m.sharpe:.2f}",
            mdd=f"{m.max_drawdown:.1%}",
            orders=m.n_orders,
            conclusion=auto_conclusion(result).replace("**", ""),
            chart_links=chart_links,
        ),
        encoding="utf-8",
    )
    # Prevent GitHub Pages' Jekyll from ignoring files that start with "_".
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    return SITE_DIR


if __name__ == "__main__":
    out = build()
    print(f"Site written to {out.resolve()}")
