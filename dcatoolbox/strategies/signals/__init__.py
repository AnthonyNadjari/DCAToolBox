"""Signal sub-package: pluggable dip-detection methods and their factory."""

from __future__ import annotations

from typing import Any

from dcatoolbox.config.enums import SignalMethod
from dcatoolbox.strategies.signals.base import SignalGenerator
from dcatoolbox.strategies.signals.price_signals import (
    CloseVsCloseSignal,
    CloseVsOpenSignal,
    CumulativeReturnSignal,
    DrawdownNDaysSignal,
    OpenVsCloseSignal,
    OpenVsOpenSignal,
)

__all__ = [
    "SignalGenerator",
    "OpenVsOpenSignal",
    "CloseVsCloseSignal",
    "OpenVsCloseSignal",
    "CloseVsOpenSignal",
    "DrawdownNDaysSignal",
    "CumulativeReturnSignal",
    "build_signal",
    "SIGNAL_REGISTRY",
]

#: Maps each :class:`SignalMethod` to its generator class.
SIGNAL_REGISTRY: dict[SignalMethod, type[SignalGenerator]] = {
    SignalMethod.OPEN_VS_OPEN: OpenVsOpenSignal,
    SignalMethod.CLOSE_VS_CLOSE: CloseVsCloseSignal,
    SignalMethod.OPEN_VS_CLOSE: OpenVsCloseSignal,
    SignalMethod.CLOSE_VS_OPEN: CloseVsOpenSignal,
    SignalMethod.DRAWDOWN_N_DAYS: DrawdownNDaysSignal,
    SignalMethod.CUMULATIVE_RETURN: CumulativeReturnSignal,
}


def build_signal(method: SignalMethod | str, **params: Any) -> SignalGenerator:
    """Instantiate a signal generator from a :class:`SignalMethod`.

    Args:
        method: The detection method (enum or its string value).
        **params: Extra keyword arguments forwarded to the generator
            (e.g. ``window`` for windowed signals).

    Returns:
        A ready-to-use :class:`SignalGenerator`.
    """
    method = SignalMethod(method)
    generator_cls = SIGNAL_REGISTRY[method]
    return generator_cls(**params)
