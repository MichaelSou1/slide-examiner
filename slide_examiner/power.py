from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from statistics import NormalDist


@dataclass(frozen=True)
class PowerEstimate:
    baseline_rate: float
    target_rate: float
    alpha: float
    power: float
    sample_size_per_group: int
    effect: float

    def to_dict(self) -> dict:
        return {
            "baseline_rate": self.baseline_rate,
            "target_rate": self.target_rate,
            "alpha": self.alpha,
            "power": self.power,
            "sample_size_per_group": self.sample_size_per_group,
            "effect": self.effect,
        }


def two_proportion_sample_size(
    *,
    baseline_rate: float,
    target_rate: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> PowerEstimate:
    """Normal-approximation sample size per group for two independent proportions."""

    _validate_probability(baseline_rate, "baseline_rate")
    _validate_probability(target_rate, "target_rate")
    _validate_probability(alpha, "alpha")
    _validate_probability(power, "power")
    effect = abs(target_rate - baseline_rate)
    if effect == 0:
        raise ValueError("target_rate must differ from baseline_rate")
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_beta = NormalDist().inv_cdf(power)
    pooled = (baseline_rate + target_rate) / 2
    term_a = z_alpha * sqrt(2 * pooled * (1 - pooled))
    term_b = z_beta * sqrt(baseline_rate * (1 - baseline_rate) + target_rate * (1 - target_rate))
    n = ((term_a + term_b) / effect) ** 2
    return PowerEstimate(
        baseline_rate=baseline_rate,
        target_rate=target_rate,
        alpha=alpha,
        power=power,
        sample_size_per_group=ceil(n),
        effect=target_rate - baseline_rate,
    )


def _validate_probability(value: float, name: str) -> None:
    if not 0 < value < 1:
        raise ValueError(f"{name} must be between 0 and 1")

