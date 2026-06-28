"""Tests for calendar helpers (scheduled days, month starts, holidays)."""

from __future__ import annotations

import pandas as pd

from dcatoolbox.utils.calendar import (
    is_scheduled_day,
    month_start_days,
    next_scheduled_day,
    scheduled_days,
    trading_days,
)


def _calendar() -> pd.DatetimeIndex:
    # Business days across three months of 2021.
    return pd.bdate_range("2021-01-01", "2021-03-31", name="date")


def test_trading_days_sorted_unique() -> None:
    idx = pd.DatetimeIndex(["2021-01-02", "2021-01-01", "2021-01-01"])
    out = trading_days(idx)
    assert list(out) == [pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-02")]


def test_scheduled_day_rolls_forward_over_weekend() -> None:
    cal = _calendar()
    # The 26th of January 2021 is a Tuesday (a trading day).
    assert is_scheduled_day(pd.Timestamp("2021-01-26"), cal, 26)


def test_scheduled_days_one_per_month() -> None:
    cal = _calendar()
    days = scheduled_days(cal, 26)
    assert len({(d.year, d.month) for d in days}) == 3


def test_month_start_days_count() -> None:
    cal = _calendar()
    assert len(month_start_days(cal)) == 3


def test_next_scheduled_day_after_returns_future() -> None:
    cal = _calendar()
    nxt = next_scheduled_day(pd.Timestamp("2021-01-27"), cal, 26)
    assert nxt is not None and nxt.month == 2


def test_scheduled_day_uses_last_day_when_target_too_high() -> None:
    cal = _calendar()
    # Day 31 in February -> falls back to last trading day of February.
    feb_days = scheduled_days(cal, 31)
    february = [d for d in feb_days if d.month == 2][0]
    assert february.month == 2
