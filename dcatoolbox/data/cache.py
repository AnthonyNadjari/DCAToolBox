"""Local on-disk cache with incremental update support.

Series are stored as Parquet files (falling back to CSV when ``pyarrow`` is not
available) keyed by ``<ticker>_<frequency>``. Incremental update only fetches the
missing tail of history instead of re-downloading everything.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dcatoolbox.config.enums import Frequency
from dcatoolbox.data.models import MarketData
from dcatoolbox.utils.logging import logger

__all__ = ["DataCache"]


class DataCache:
    """File-system cache for :class:`MarketData` series."""

    def __init__(self, cache_dir: Path | str = "data_cache") -> None:
        """Create the cache, ensuring the backing directory exists."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _stem(self, ticker: str, frequency: Frequency) -> Path:
        return self.cache_dir / f"{ticker.upper()}_{frequency.value}"

    def _path(self, ticker: str, frequency: Frequency) -> Path:
        """Resolve the cache file, preferring Parquet but accepting CSV."""
        stem = self._stem(ticker, frequency)
        parquet, csv = stem.with_suffix(".parquet"), stem.with_suffix(".csv")
        if parquet.exists():
            return parquet
        return csv if csv.exists() else parquet

    def has(self, ticker: str, frequency: Frequency) -> bool:
        """Return ``True`` if a cached series exists for ``ticker``/``frequency``."""
        return self._path(ticker, frequency).exists()

    def load(self, ticker: str, frequency: Frequency) -> MarketData | None:
        """Load a cached series, or ``None`` when absent/unreadable."""
        path = self._path(ticker, frequency)
        if not path.exists():
            return None
        frame = (
            pd.read_parquet(path)
            if path.suffix == ".parquet"
            else pd.read_csv(path, index_col=0, parse_dates=True)
        )
        logger.debug("Cache hit for {} ({} rows)", ticker, len(frame))
        return MarketData.from_frame(ticker, frequency, frame)

    def save(self, data: MarketData) -> None:
        """Persist a series to disk (Parquet, with a CSV fallback)."""
        stem = self._stem(data.ticker, data.frequency)
        try:
            path = stem.with_suffix(".parquet")
            data.frame.to_parquet(path)
        except Exception:  # pragma: no cover - depends on optional pyarrow
            path = stem.with_suffix(".csv")
            data.frame.to_csv(path)
        logger.debug("Cached {} ({} rows) -> {}", data.ticker, len(data), path)

    def merge(self, existing: MarketData, fresh: MarketData) -> MarketData:
        """Combine cached and freshly downloaded data (fresh wins on overlap)."""
        combined = pd.concat([existing.frame, fresh.frame])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        return MarketData(ticker=existing.ticker, frequency=existing.frequency, frame=combined)
