"""Shift-share (volume / mix) decomposition of a group's change in units.

    group units = total units x group share
    change = (T1 - T0) s0          volume effect: everyone buys more or less ice cream
           + T0 (s1 - s0)          mix effect: customers switch towards or away from the group
           + (T1 - T0)(s1 - s0)    interaction
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decomposition:
    total_before: float
    total_now: float
    share_before: float
    share_now: float
    volume: float
    mix: float
    interaction: float

    @property
    def change(self) -> float:
        return self.volume + self.mix + self.interaction

    @property
    def dominant(self) -> str:
        return "mix" if abs(self.mix) >= abs(self.volume) else "volume"


def decompose(total_before: float, group_before: float, total_now: float, group_now: float) -> Decomposition:
    s0 = group_before / total_before if total_before else 0.0
    s1 = group_now / total_now if total_now else 0.0
    return Decomposition(
        total_before=total_before,
        total_now=total_now,
        share_before=s0,
        share_now=s1,
        volume=(total_now - total_before) * s0,
        mix=total_before * (s1 - s0),
        interaction=(total_now - total_before) * (s1 - s0),
    )
