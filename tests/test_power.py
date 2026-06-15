import pytest

from slide_examiner.power import two_proportion_sample_size


def test_two_proportion_sample_size() -> None:
    estimate = two_proportion_sample_size(baseline_rate=0.5, target_rate=0.7)
    assert estimate.sample_size_per_group > 0
    assert estimate.effect == pytest.approx(0.2)


def test_two_proportion_sample_size_rejects_zero_effect() -> None:
    with pytest.raises(ValueError):
        two_proportion_sample_size(baseline_rate=0.5, target_rate=0.5)

