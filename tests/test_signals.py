"""Tests for the interchangeable dip-detection signals."""

from __future__ import annotations

import pytest

from dcatoolbox.config.enums import SignalMethod
from dcatoolbox.strategies.signals import SIGNAL_REGISTRY, build_signal
from dcatoolbox.strategies.signals.price_signals import (
    CloseVsCloseSignal,
    CumulativeReturnSignal,
    DrawdownNDaysSignal,
    OpenVsOpenSignal,
)


def test_registry_covers_every_method() -> None:
    assert set(SIGNAL_REGISTRY) == set(SignalMethod)


def test_open_vs_open(small_frame) -> None:
    sig = OpenVsOpenSignal()
    expected = small_frame["open"].iloc[-1] / small_frame["open"].iloc[-2] - 1
    assert sig.compute(small_frame) == pytest.approx(expected)


def test_close_vs_close(small_frame) -> None:
    sig = CloseVsCloseSignal()
    expected = small_frame["close"].iloc[-1] / small_frame["close"].iloc[-2] - 1
    assert sig.compute(small_frame) == pytest.approx(expected)


def test_drawdown_is_non_positive(small_frame) -> None:
    assert DrawdownNDaysSignal(window=5).compute(small_frame) <= 0.0


def test_cumulative_return_window(small_frame) -> None:
    sig = CumulativeReturnSignal(window=3)
    expected = small_frame["close"].iloc[-1] / small_frame["close"].iloc[-4] - 1
    assert sig.compute(small_frame) == pytest.approx(expected)


def test_signals_handle_insufficient_history(small_frame) -> None:
    empty = small_frame.iloc[:0]
    for method in SignalMethod:
        assert build_signal(method).compute(empty) == 0.0


def test_build_signal_accepts_window() -> None:
    sig = build_signal(SignalMethod.DRAWDOWN_N_DAYS, window=10)
    assert isinstance(sig, DrawdownNDaysSignal)
    assert sig.window == 10


def test_windowed_signal_rejects_bad_window() -> None:
    with pytest.raises(ValueError):
        DrawdownNDaysSignal(window=0)
