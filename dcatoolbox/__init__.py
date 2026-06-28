"""DCAToolBox: a quantitative research framework for Dollar-Cost-Averaging strategies.

The package is organised into strictly decoupled layers so that any single layer
can be replaced without touching the others:

* :mod:`dcatoolbox.data`          -- market data providers, cache and validation.
* :mod:`dcatoolbox.broker`        -- simulated order execution (fees, slippage).
* :mod:`dcatoolbox.portfolio`     -- cash, positions and bookkeeping.
* :mod:`dcatoolbox.strategies`    -- interchangeable strategy modules + signals.
* :mod:`dcatoolbox.backtesting`   -- the generic, strategy-agnostic engine.
* :mod:`dcatoolbox.metrics`       -- performance and risk analytics.
* :mod:`dcatoolbox.optimization`  -- grid search and train/validation/test splits.
* :mod:`dcatoolbox.visualization` -- interactive Plotly charts.
* :mod:`dcatoolbox.reports`       -- Markdown / HTML / PDF report generation.

The engine never depends on a concrete strategy; ``DipBuyingStrategy`` is merely
one example among many.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Anthony Nadjari"

__all__ = ["__version__", "__author__"]
