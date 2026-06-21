from slide_examiner.statistics import (
    balanced_accuracy_ci,
    two_proportion_z_test,
    variance_gated_effect,
    wilson_interval,
)


def test_wilson_interval_boundary_is_non_degenerate() -> None:
    # recall = 0 / 61 must NOT collapse to [0, 0]; Wilson gives a real upper bound.
    ci = wilson_interval(0, 61)
    assert ci.estimate == 0.0
    assert ci.low == 0.0
    assert 0.0 < ci.high < 0.1


def test_wilson_interval_brackets_estimate() -> None:
    ci = wilson_interval(30, 40)
    assert ci.low < ci.estimate < ci.high
    assert 0.0 <= ci.low and ci.high <= 1.0


def test_wilson_interval_empty_is_full_range() -> None:
    ci = wilson_interval(0, 0)
    assert (ci.low, ci.high) == (0.0, 1.0)


def test_balanced_accuracy_ci_abstain_cell() -> None:
    # tp=0/60 (recall 0) + tn=432/432 (spec 1) -> bal_acc 0.5 with a real interval.
    bci = balanced_accuracy_ci(0, 60, 432, 432)
    assert bci.estimate == 0.5
    assert bci.low < 0.5 <= bci.high


def test_two_proportion_z_test_detects_large_gap() -> None:
    # 0.99 vs 0.785 on reasonable n should be significant.
    res = two_proportion_z_test(99, 100, 157, 200)
    assert res.diff > 0
    assert res.p_value < 0.001


def test_two_proportion_z_test_no_difference() -> None:
    res = two_proportion_z_test(50, 100, 50, 100)
    assert res.p_value == 1.0


def test_variance_gated_effect_conclusive() -> None:
    gate = variance_gated_effect([0, 0, 0], [1, 1, 1])
    assert gate.effect == 1
    assert gate.decision == "conclusive"


def test_variance_gated_effect_inconclusive() -> None:
    gate = variance_gated_effect([0.4, 0.6], [0.5, 0.5])
    assert gate.decision == "inconclusive"

