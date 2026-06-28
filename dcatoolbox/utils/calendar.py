"""Calendar helpers used by strategies and the backtest engine.

These functions operate purely on a sorted sequence of trading timestamps (the
actual market calendar derived from the data) so that strategies never need to
hard-code holidays: a "scheduled" day is resolved to the *first available
trading day on or after* the target day-of-month.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

__all__ = [
    "trading_days",
    "month_key",
    "is_scheduled_day",
    "next_scheduled_day",
    "scheduled_days",
    "month_start_days",
]


def trading_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return a sorted, de-duplicated, tz-naive copy of a datetime index."""
    idx = pd.DatetimeIndex(index).tz_localize(None) if index.tz is not None else index
    return idx.sort_values().unique()


def month_key(timestamp: pd.Timestamp) -> tuple[int, int]:
    """Return the ``(year, month)`` tuple identifying the calendar month."""
    return (timestamp.year, timestamp.month)


def _scheduled_days_in_month(
    days: pd.DatetimeIndex, year: int, month: int, day_of_month: int
) -> pd.DatetimeIndex:
    """Trading days of a month that qualify as the scheduled investment day.

    The scheduled day is the first trading day on or after ``day_of_month``. If
    no trading day exists on/after that day (e.g. month ends earlier), the last
    trading day of the month is used instead.
    """
    in_month = days[(days.year == year) & (days.month == month)]
    if len(in_month) == 0:
        return in_month
    on_or_after = in_month[in_month.day >= day_of_month]
    chosen = on_or_after[0] if len(on_or_after) > 0 else in_month[-1]
    return pd.DatetimeIndex([chosen])


def is_scheduled_day(
    timestamp: pd.Timestamp,
    calendar: pd.DatetimeIndex,
    day_of_month: int,
) -> bool:
    """Return ``True`` if ``timestamp`` is the scheduled investment day of its month.

    Args:
        timestamp: The candidate timestamp (must belong to ``calendar``).
        calendar: The full trading calendar.
        day_of_month: Target day-of-month for the scheduled investment.
    """
    scheduled = _scheduled_days_in_month(calendar, timestamp.year, timestamp.month, day_of_month)
    return len(scheduled) > 0 and timestamp.normalize() == scheduled[0].normalize()


def next_scheduled_day(
    timestamp: pd.Timestamp,
    calendar: pd.DatetimeIndex,
    day_of_month: int,
) -> pd.Timestamp | None:
    """Return the next scheduled investment day on or after ``timestamp``."""
    future = calendar[calendar >= timestamp.normalize()]
    for day in _unique_months(future):
        scheduled = _scheduled_days_in_month(calendar, day.year, day.month, day_of_month)
        if len(scheduled) > 0 and scheduled[0] >= timestamp.normalize():
            return scheduled[0]
    return None


def scheduled_days(calendar: pd.DatetimeIndex, day_of_month: int) -> set[pd.Timestamp]:
    """Pre-compute the set of scheduled investment days across the whole calendar.

    Computing this once is far cheaper than calling :func:`is_scheduled_day` for
    every bar during a backtest.
    """
    result: set[pd.Timestamp] = set()
    for representative in _unique_months(calendar):
        chosen = _scheduled_days_in_month(
            calendar, representative.year, representative.month, day_of_month
        )
        if len(chosen) > 0:
            result.add(chosen[0].normalize())
    return result


def month_start_days(calendar: pd.DatetimeIndex) -> set[pd.Timestamp]:
    """Return the first trading day of each calendar month, normalised."""
    result: dict[tuple[int, int], pd.Timestamp] = {}
    for day in calendar:
        key = month_key(day)
        if key not in result:
            result[key] = day.normalize()
    return set(result.values())


def _unique_months(days: Iterable[pd.Timestamp]) -> list[pd.Timestamp]:
    """Return one representative timestamp per distinct ``(year, month)``."""
    seen: dict[tuple[int, int], pd.Timestamp] = {}
    for day in days:
        seen.setdefault(month_key(day), day)
    return list(seen.values())
