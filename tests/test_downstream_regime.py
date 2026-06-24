"""Tests for E6 floored-vs-unfloored regime analysis (offline, pure arithmetic).

Exercises the pure functions over synthetic self-refine summaries: Pearson,
gradient ordering, per-regime headline stats, and the floored-vs-unfloored verdict
(material bounded-positive vs sharper-negative) plus the coverage-domination
mechanism flag. No GPU, no model, no I/O.
"""
import math

from slide_examiner.downstream_regime import (
    MATERIAL_GAIN, compare_regimes, ordered_conditions, pearson, regime_stats,
)


def _cell(qs, init, gain, best_gain, dim_delta=None, dim_initial=None):
    return {
        "quality_scalar": qs, "mean_initial": init, "mean_headroom": round(1 - init, 4),
        "mean_gain": gain, "mean_best_gain": best_gain,
        "dim_delta": dim_delta or {}, "dim_initial": dim_initial or {},
    }


def _summary(per_condition, regime_mean_initial=None):
    s = {"vehicle": "self_refine", "per_condition": per_condition}
    if regime_mean_initial is not None:
        s["regime_mean_initial"] = regime_mean_initial
    return s


def test_pearson_known_vectors() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == 1.0           # perfect +
    assert pearson([1, 2, 3], [6, 4, 2]) == -1.0          # perfect -
    assert pearson([1, 1, 1], [1, 2, 3]) == 0.0           # zero variance -> 0
    assert pearson([1.0], [2.0]) == 0.0                   # n<2 -> 0
    assert math.isclose(pearson([0.5, 0.7, 1.0], [0.0, 0.01, 0.02]), 0.9934, abs_tol=1e-3)


def test_ordered_conditions_follows_gradient_and_skips_missing() -> None:
    summ = _summary({
        "hybrid": _cell(1.0, 0.7, 0.0, 0.02),
        "linter": _cell(0.5, 0.75, 0.0, 0.0),
        "zero_shot_30b": _cell(0.785, 0.72, 0.01, 0.012),
        "noscalar": {"quality_scalar": None, "mean_initial": 0.7, "mean_best_gain": 0.0},
    })
    # gradient order (linter < 30b < hybrid), the None-scalar cell dropped
    assert ordered_conditions(summ) == ["linter", "zero_shot_30b", "hybrid"]


def test_regime_stats_picks_best_examiner_and_spread() -> None:
    summ = _summary({
        "linter": _cell(0.5, 0.76, -0.004, 0.008),
        "zero_shot_8b": _cell(0.639, 0.78, 0.004, 0.008),
        "zero_shot_30b": _cell(0.785, 0.77, 0.012, 0.012),
        "finetuned_8b": _cell(1.0, 0.75, 0.004, 0.008),
        "hybrid": _cell(1.0, 0.76, 0.011, 0.019),
    }, regime_mean_initial=0.764)
    st = regime_stats(summ)
    assert st["n_conditions"] == 5
    # tie at quality_scalar 1.0 -> hybrid wins (later in the gradient)
    assert st["best_examiner"] == "hybrid"
    assert st["best_examiner_best_gain"] == 0.019
    assert st["gain_spread"] == round(0.019 - 0.008, 4)
    assert st["mean_headroom"] == round(1 - 0.764, 4)
    assert st["corr_quality_vs_best_gain"] > 0  # the +direction holds


def test_compare_regimes_floored_stays_negative() -> None:
    strong = _summary({
        "linter": _cell(0.5, 0.76, -0.004, 0.008),
        "hybrid": _cell(1.0, 0.76, 0.011, 0.019),
    }, regime_mean_initial=0.76)
    # weak regime but the (coverage) headroom never transfers -> still sub-material
    weak = _summary({
        "linter": _cell(0.5, 0.60, 0.0, 0.005,
                        dim_initial={"coverage": 0.2, "geometry": 1.0, "terms": 1.0, "conciseness": 1.0}),
        "hybrid": _cell(1.0, 0.62, 0.004, 0.010,
                        dim_delta={"coverage": 0.0, "geometry": 0.0, "terms": 0.0, "conciseness": 0.0},
                        dim_initial={"coverage": 0.2, "geometry": 1.0, "terms": 1.0, "conciseness": 1.0}),
    }, regime_mean_initial=0.61)
    cmp = compare_regimes(strong, weak)
    assert cmp["verdict"] == "stronger_negative"
    assert cmp["headroom_ratio_weak_over_strong"] > 1.0      # weak has more headroom
    assert cmp["weak_headroom_is_coverage_dominated"] is True


def test_compare_regimes_material_becomes_bounded_positive() -> None:
    strong = _summary({
        "linter": _cell(0.5, 0.76, -0.004, 0.008),
        "hybrid": _cell(1.0, 0.76, 0.011, 0.019),
    }, regime_mean_initial=0.76)
    # weak regime with ADDRESSABLE headroom (low conciseness/geometry) that the strong
    # examiner recovers -> best_gain crosses the material threshold
    weak = _summary({
        "linter": _cell(0.5, 0.55, 0.01, 0.02,
                        dim_initial={"coverage": 0.9, "geometry": 0.6, "terms": 0.7, "conciseness": 0.4}),
        "hybrid": _cell(1.0, 0.55, 0.05, 0.08,
                        dim_delta={"coverage": 0.0, "geometry": 0.1, "terms": 0.1, "conciseness": 0.2},
                        dim_initial={"coverage": 0.9, "geometry": 0.6, "terms": 0.7, "conciseness": 0.4}),
    }, regime_mean_initial=0.55)
    cmp = compare_regimes(strong, weak)
    assert cmp["verdict"] == "bounded_positive"
    assert cmp["weak"]["best_examiner_best_gain"] >= MATERIAL_GAIN
    assert cmp["gain_spread_amplification"] > 1.0           # swapping examiners moves more
    assert cmp["weak_headroom_is_coverage_dominated"] is False
