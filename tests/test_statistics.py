from slide_examiner.statistics import variance_gated_effect


def test_variance_gated_effect_conclusive() -> None:
    gate = variance_gated_effect([0, 0, 0], [1, 1, 1])
    assert gate.effect == 1
    assert gate.decision == "conclusive"


def test_variance_gated_effect_inconclusive() -> None:
    gate = variance_gated_effect([0.4, 0.6], [0.5, 0.5])
    assert gate.decision == "inconclusive"

