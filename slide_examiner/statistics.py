from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class VarianceGate:
    effect: float
    sigma: float
    threshold: float
    decision: str


def variance_gated_effect(left: Iterable[float], right: Iterable[float], *, sigma_multiplier: float = 2.0) -> VarianceGate:
    left_values = list(left)
    right_values = list(right)
    if not left_values or not right_values:
        return VarianceGate(effect=0.0, sigma=0.0, threshold=0.0, decision="insufficient_data")
    effect = mean(right_values) - mean(left_values)
    sigma = pooled_standard_error(left_values, right_values)
    threshold = sigma_multiplier * sigma
    if sigma == 0.0:
        decision = "conclusive" if effect != 0.0 else "inconclusive"
    else:
        decision = "conclusive" if abs(effect) >= threshold else "inconclusive"
    return VarianceGate(effect=effect, sigma=sigma, threshold=threshold, decision=decision)


def pooled_standard_error(left: list[float], right: list[float]) -> float:
    left_sigma = pstdev(left) if len(left) > 1 else 0.0
    right_sigma = pstdev(right) if len(right) > 1 else 0.0
    return sqrt((left_sigma**2 / max(1, len(left))) + (right_sigma**2 / max(1, len(right))))

