"""DipBuyingStrategy: deploy the monthly budget preferentially into dips.

Each month a fixed budget is available. On any day where the chosen dip signal
breaches a threshold, a fraction (``allocation``) of the *remaining* budget is
invested. Whatever is left on the scheduled day is invested in full, guaranteeing
the budget is always fully deployed and never exceeded.

This strategy is only an *example*: it is a plain registry entry built on the
generic :class:`BudgetDeploymentStrategy` base and carries no special status
inside the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dcatoolbox.config.enums import SignalMethod
from dcatoolbox.strategies.budget_deployment import BudgetDeploymentStrategy, Signal
from dcatoolbox.strategies.registry import register_strategy
from dcatoolbox.strategies.signals import build_signal

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["DipBuyingStrategy"]

_WINDOWED = (SignalMethod.DRAWDOWN_N_DAYS, SignalMethod.CUMULATIVE_RETURN)


@register_strategy
class DipBuyingStrategy(BudgetDeploymentStrategy):
    """Buy a fraction of the remaining budget on each detected dip.

    Parameters (via ``params``):
        threshold: Minimum decline (positive fraction, e.g. ``0.02`` = -2%) that
            triggers a purchase. Default ``0.02``.
        allocation: Fraction of the remaining budget per signal. Default ``0.25``.
        signal_method: Dip-detection method. Default ``open_vs_open``.
        signal_window: Look-back for windowed signals. Default ``20``.
    """

    name = "dip_buying"

    def _configure(self) -> None:
        self.threshold = float(self.params.get("threshold", 0.02))
        if self.threshold <= 0.0:
            raise ValueError("threshold must be positive")
        method = SignalMethod(self.params.get("signal_method", SignalMethod.OPEN_VS_OPEN))
        kwargs = (
            {"window": int(self.params.get("signal_window", 20))} if method in _WINDOWED else {}
        )
        self.signal = build_signal(method, **kwargs)

    def _signal(self, context: MarketContext) -> Signal:
        move = self.signal.compute(context.history)
        return (move <= -self.threshold, self.signal.execution_price_field)
