from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist, mean, pstdev
from typing import Iterable


@dataclass(frozen=True)
class ProportionCI:
    """A binomial proportion estimate with a Wilson score interval."""

    k: int
    n: int
    estimate: float
    low: float
    high: float

    def to_dict(self) -> dict:
        return {"estimate": self.estimate, "low": self.low, "high": self.high, "n": self.n}


def wilson_interval(k: int, n: int, *, confidence: float = 0.95) -> ProportionCI:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation for small n and for proportions
    near 0 or 1 (e.g. recall=0/61 or specificity=1.0) where the naive interval
    collapses to a degenerate point. ``n == 0`` returns the full [0, 1] range.
    """

    if n < 0 or k < 0 or k > n:
        raise ValueError("require 0 <= k <= n")
    if n == 0:
        return ProportionCI(k=0, n=0, estimate=0.0, low=0.0, high=1.0)
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ProportionCI(k=k, n=n, estimate=p, low=max(0.0, center - half), high=min(1.0, center + half))


@dataclass(frozen=True)
class BalancedAccuracyCI:
    """Balanced accuracy = (recall + specificity) / 2 with a CI built from the
    two component Wilson intervals (recall on ``n_pos`` positives, specificity on
    ``n_neg`` negatives). Conservative but boundary-safe — it stays non-degenerate
    when recall=0 and specificity=1 (the common 0.50/abstain cell)."""

    estimate: float
    low: float
    high: float
    n_pos: int
    n_neg: int

    def to_dict(self) -> dict:
        return {"estimate": self.estimate, "low": self.low, "high": self.high,
                "n_pos": self.n_pos, "n_neg": self.n_neg}


def balanced_accuracy_ci(
    tp: int, n_pos: int, tn: int, n_neg: int, *, confidence: float = 0.95
) -> BalancedAccuracyCI:
    rec = wilson_interval(tp, n_pos, confidence=confidence)
    spec = wilson_interval(tn, n_neg, confidence=confidence)
    return BalancedAccuracyCI(
        estimate=(rec.estimate + spec.estimate) / 2,
        low=(rec.low + spec.low) / 2,
        high=(rec.high + spec.high) / 2,
        n_pos=n_pos,
        n_neg=n_neg,
    )


@dataclass(frozen=True)
class TwoProportionTest:
    p1: float
    p2: float
    diff: float
    z: float
    p_value: float


def two_proportion_z_test(k1: int, n1: int, k2: int, n2: int) -> TwoProportionTest:
    """Two-sided z-test for the difference of two independent proportions
    (pooled-variance). Used for headline contrasts (e.g. ft-8b vs zs-30b recall)
    where the two groups are scored on disjoint items, so a paired McNemar test
    does not apply. ``p_value`` is 1.0 when either group is empty or the pooled
    variance is degenerate."""

    if n1 <= 0 or n2 <= 0:
        return TwoProportionTest(0.0, 0.0, 0.0, 0.0, 1.0)
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    se = sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0.0:
        return TwoProportionTest(p1, p2, p1 - p2, 0.0, 1.0)
    z = (p1 - p2) / se
    p_value = 2 * (1 - NormalDist().cdf(abs(z)))
    return TwoProportionTest(p1=p1, p2=p2, diff=p1 - p2, z=z, p_value=p_value)


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

