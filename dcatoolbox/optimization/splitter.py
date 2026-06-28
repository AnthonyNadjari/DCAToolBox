"""Train / validation / test splitting for anti-overfitting analysis.

The optimizer fits parameters on the *train* window only; performance is then
reported separately on validation and test. Reporting a single global number is
deliberately avoided, since it hides over-fitting.
"""

from __future__ import annotations

import pandas as pd

from dcatoolbox.config.settings import SplitConfig
from dcatoolbox.data.models import MarketData

__all__ = ["DataSplitter", "default_split"]


class DataSplitter:
    """Slice a market-data mapping into named date windows."""

    def __init__(self, split: SplitConfig) -> None:
        """Initialise with the train/validation/test boundaries."""
        self.split = split

    def split_market(self, market: dict[str, MarketData]) -> dict[str, dict[str, MarketData]]:
        """Return ``{window_name: {ticker: MarketData}}`` for each split window."""
        result: dict[str, dict[str, MarketData]] = {}
        for name, (start, end) in self.split.as_dict().items():
            window = {
                ticker: data.slice(pd.Timestamp(start), pd.Timestamp(end))
                for ticker, data in market.items()
            }
            result[name] = window
        return result


def default_split(start_year: int, end_year: int) -> SplitConfig:
    """Build a chronological 60/20/20 train/validation/test split by year.

    Args:
        start_year: First year of available data.
        end_year: Last year of available data.

    Returns:
        A :class:`SplitConfig` with three contiguous, non-overlapping windows.
    """
    from datetime import date

    span = max(end_year - start_year, 3)
    train_end = start_year + int(span * 0.6)
    val_end = start_year + int(span * 0.8)
    return SplitConfig(
        train=(date(start_year, 1, 1), date(train_end, 1, 1)),
        validation=(date(train_end, 1, 1), date(val_end, 1, 1)),
        test=(date(val_end, 1, 1), date(end_year, 1, 1)),
    )
