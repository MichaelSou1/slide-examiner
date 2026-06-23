from slide_examiner.statistics import (
    balanced_accuracy_ci,
    benjamini_hochberg,
    holm_bonferroni,
    stratified_mcnemar,
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


# --- multiple-comparison correction (E2) ----------------------------------- #
def _close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_holm_known_vector() -> None:
    # p = .01 .02 .03 .04 .05 -> Holm adj = .05 .08 .09 .09 .09; only the first
    # survives at alpha=.05 (step-down stops at the first failure).
    mc = holm_bonferroni([0.01, 0.02, 0.03, 0.04, 0.05])
    assert all(_close(a, e) for a, e in zip(mc.adjusted, [0.05, 0.08, 0.09, 0.09, 0.09]))
    assert mc.reject == (True, False, False, False, False)
    assert mc.n_reject == 1 and mc.n_tests == 5


def test_bh_known_vector() -> None:
    # same vector under BH collapses to q=.05 everywhere -> all five reject.
    mc = benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05])
    assert all(_close(a, 0.05) for a in mc.adjusted)
    assert mc.reject == (True, True, True, True, True)
    assert mc.n_reject == 5


def test_holm_preserves_input_order() -> None:
    # shuffled inputs: adjusted/reject must come back aligned to the caller's order.
    mc = holm_bonferroni([0.04, 0.01, 0.05, 0.02, 0.03])
    assert all(_close(a, e) for a, e in zip(mc.adjusted, [0.09, 0.05, 0.09, 0.08, 0.09]))
    assert mc.reject == (False, True, False, False, False)


def test_holm_large_margin_survives_many_tests() -> None:
    # the paper's headline (p≈4.5e-7) must survive Holm against ~30 null cells.
    pvals = [4.5e-7] + [0.5] * 30
    mc = holm_bonferroni(pvals)
    assert mc.reject[0] is True
    assert not any(mc.reject[1:])
    assert mc.adjusted[0] <= 0.05


def test_correction_adjusted_dominates_raw_and_matches_reject() -> None:
    pvals = [0.001, 0.2, 0.012, 0.04, 0.6, 0.009]
    for mc in (holm_bonferroni(pvals), benjamini_hochberg(pvals)):
        for raw, adj, rej in zip(pvals, mc.adjusted, mc.reject):
            assert adj >= raw - 1e-12          # correction never shrinks a p-value
            assert adj <= 1.0
            assert rej == (adj <= mc.alpha)    # reject flag is exactly adjusted<=alpha


def test_correction_empty_input() -> None:
    for mc in (holm_bonferroni([]), benjamini_hochberg([])):
        assert mc.n_tests == 0 and mc.n_reject == 0
        assert mc.reject == () and mc.adjusted == ()


# --- stratified McNemar (the G7 cross-model pooled test) -------------------- #
def test_stratified_mcnemar_pools_g7_recovery() -> None:
    # The real G7 C3-vs-C0 discordant counts for the four capable models: every
    # flip favors C3, not one reversal -> overwhelmingly significant when pooled,
    # even though the small qwen35-27b stratum (9,0) is only p=0.004 alone.
    res = stratified_mcnemar([(52, 0), (9, 0), (58, 0), (30, 0)])
    assert res.b_total == 149 and res.c_total == 0
    assert res.max_c_in_stratum == 0          # no reversal in any stratum
    assert res.p_value < 1e-30
    assert res.n_strata == 4


def test_stratified_mcnemar_no_discordant_is_ns() -> None:
    res = stratified_mcnemar([(0, 0), (0, 0)])
    assert res.p_value == 1.0 and res.chi2 == 0.0


def test_stratified_mcnemar_cancellation_flagged() -> None:
    # opposite-direction strata cancel in the pooled statistic, and max_c flags it
    res = stratified_mcnemar([(20, 0), (0, 20)])
    assert res.b_total == 20 and res.c_total == 20
    assert res.chi2 == 0.0 and res.p_value == 1.0
    assert res.max_c_in_stratum == 20         # caller can see the reversal stratum

