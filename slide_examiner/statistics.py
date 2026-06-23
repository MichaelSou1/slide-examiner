from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist, mean, pstdev
from typing import Iterable, Sequence


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


# --------------------------------------------------------------------------- #
# Multiple-comparison correction (E2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MultipleComparison:
    """Family-wise / FDR correction over a family of p-values.

    ``reject`` and ``adjusted`` are returned in the ORIGINAL input order (not
    sorted), so a caller can zip them straight back onto the tests that produced
    the raw p-values. ``adjusted[i] <= alpha`` iff ``reject[i]`` — the adjusted
    p-value is the single number to footnote in a table."""

    method: str
    alpha: float
    n_tests: int
    reject: tuple[bool, ...]
    adjusted: tuple[float, ...]
    n_reject: int

    def to_dict(self) -> dict:
        return {"method": self.method, "alpha": self.alpha, "n_tests": self.n_tests,
                "reject": list(self.reject), "adjusted": list(self.adjusted),
                "n_reject": self.n_reject}


def holm_bonferroni(pvals: Sequence[float], alpha: float = 0.05) -> MultipleComparison:
    """Holm step-down family-wise-error correction.

    Controls the FWER at ``alpha`` with uniformly more power than plain
    Bonferroni. Adjusted p-value of the rank-i (0-based, ascending) test is
    ``max_{j<=i} (m - j) * p_(j)`` clipped to 1 and made monotone non-decreasing;
    a hypothesis is rejected iff its adjusted p-value <= alpha (equivalent to the
    step-down rule "reject the smallest p's until the first p_(j) > alpha/(m-j)").
    Returns results in the caller's input order. Empty input -> empty result."""

    m = len(pvals)
    if m == 0:
        return MultipleComparison("holm", alpha, 0, (), (), 0)
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])  # enforce monotone non-decreasing
        adjusted[idx] = min(running, 1.0)
    reject = [adjusted[i] <= alpha for i in range(m)]
    return MultipleComparison("holm", alpha, m, tuple(reject), tuple(adjusted), sum(reject))


@dataclass(frozen=True)
class StratifiedMcNemar:
    """Cochran/Mantel-Haenszel stratified McNemar test for 1:1 matched pairs — the
    correct test for a *common* paired effect across strata (e.g. "C3 beats C0 on
    G7 across models"). Pooling discordant pairs is only honest when the effect
    direction is consistent across strata; ``min_c`` surfaces the worst reversal
    count so the caller can confirm there is no Simpson's-paradox cancellation."""

    b_total: int          # Σ "treatment wins" discordant pairs (x-wrong, y-right)
    c_total: int          # Σ "treatment loses" discordant pairs (x-right, y-wrong)
    chi2: float
    p_value: float
    n_strata: int
    max_c_in_stratum: int  # 0 => not a single reversal anywhere (fully consistent)


def stratified_mcnemar(strata: Sequence[tuple[int, int]]) -> StratifiedMcNemar:
    """``strata`` = list of (b, c) discordant counts per stratum. Combines them
    into one 1-df chi-square ``(Σb − Σc)^2 / Σ(b + c)`` (for 1:1 matched pairs the
    Mantel-Haenszel statistic reduces to this pooled McNemar form). Two-sided p."""

    b = sum(s[0] for s in strata)
    c = sum(s[1] for s in strata)
    n = b + c
    max_c = max((s[1] for s in strata), default=0)
    if n == 0:
        return StratifiedMcNemar(b, c, 0.0, 1.0, len(strata), max_c)
    chi2 = (b - c) ** 2 / n
    # chi-square with 1 df: p = 2*(1 - Phi(sqrt(chi2)))
    p = 2 * (1 - NormalDist().cdf(sqrt(chi2)))
    return StratifiedMcNemar(b, c, chi2, p, len(strata), max_c)


def benjamini_hochberg(pvals: Sequence[float], alpha: float = 0.05) -> MultipleComparison:
    """Benjamini-Hochberg step-up false-discovery-rate control.

    Controls the FDR (expected proportion of false rejections among rejections)
    at ``alpha`` — less conservative than Holm, appropriate when dozens of cells
    are screened and a few false positives are tolerable. Adjusted q-value of the
    rank-k (1-based, ascending) test is ``min_{j>=k} (m / j) * p_(j)`` clipped to
    1 and made monotone non-decreasing from the top; reject iff q <= alpha.
    Returns results in the caller's input order. Empty input -> empty result."""

    m = len(pvals)
    if m == 0:
        return MultipleComparison("bh", alpha, 0, (), (), 0)
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [0.0] * m
    running = 1.0
    for rank in reversed(range(m)):           # walk largest p -> smallest
        idx = order[rank]
        running = min(running, (m / (rank + 1)) * pvals[idx])  # k = rank + 1
        adjusted[idx] = min(running, 1.0)
    reject = [adjusted[i] <= alpha for i in range(m)]
    return MultipleComparison("bh", alpha, m, tuple(reject), tuple(adjusted), sum(reject))

