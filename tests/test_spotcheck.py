"""Tests for E8 perceptual spot-check sampling + aggregation (offline, no images).

Exercises the pure logic: stratified sampling (per-class counts, headline boost,
seed determinism, scarcity handling) and the report aggregation (Wilson-CI rate,
class collection over yes/no/blank labels, Cohen's kappa, artifact flags). No GPU,
no model, no real PNG I/O.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import part3_spotcheck_report as rep  # noqa: E402
import part3_spotcheck_sample as samp  # noqa: E402


def _fake_pool(per_class: int = 20):
    return {c: [{"def_path": Path(f"/d/{c}/{i}.png"),
                 "clean_path": Path(f"/c/{c}/{i}.png"),
                 "src_id": f"{c}_{i}"}
                for i in range(per_class)]
            for c in samp.CLASS_ORDER}


def test_sample_stratified_counts_and_headline_boost() -> None:
    picks = samp.sample(_fake_pool(20), n_per_class=6, seed=7)
    by = {}
    for p in picks:
        by[p["class"]] = by.get(p["class"], 0) + 1
    for cls in samp.CLASS_ORDER:
        expected = 6 + (2 if cls in samp.HEADLINE else 0)
        assert by[cls] == expected, (cls, by[cls], expected)
    # every headline class is over-sampled vs a non-headline one
    assert min(by[c] for c in samp.HEADLINE) > 6


def test_sample_is_seed_deterministic() -> None:
    a = samp.sample(_fake_pool(), 6, seed=42)
    b = samp.sample(_fake_pool(), 6, seed=42)
    c = samp.sample(_fake_pool(), 6, seed=43)
    assert [p["src_id"] for p in a] == [p["src_id"] for p in b]
    assert [p["src_id"] for p in a] != [p["src_id"] for p in c]


def test_sample_respects_scarcity() -> None:
    pool = _fake_pool(20)
    pool["S6_IMAGE_TEXT_CONTRADICTION"] = pool["S6_IMAGE_TEXT_CONTRADICTION"][:2]
    picks = samp.sample(pool, n_per_class=6, seed=1)
    s6 = [p for p in picks if p["class"] == "S6_IMAGE_TEXT_CONTRADICTION"]
    assert len(s6) == 2  # cannot exceed what's available


def test_sample_pair_ids_unique_and_sequential() -> None:
    picks = samp.sample(_fake_pool(), 6, seed=3)
    ids = [p["pair_id"] for p in picks]
    assert ids == [f"{i:03d}" for i in range(len(picks))]
    assert len(set(ids)) == len(ids)


def test_yes_parsing() -> None:
    assert rep._yes("yes") is True
    assert rep._yes("no") is False
    assert rep._yes(None) is None
    assert rep._yes("") is None


def test_rate_wilson() -> None:
    k, n, ci = rep.rate([True, True, True, False])
    assert (k, n) == (3, 4)
    assert ci.low < ci.estimate < ci.high
    assert abs(ci.estimate - 0.75) < 1e-9


def test_collect_skips_unanswered() -> None:
    manifest = [{"pair_id": "000", "class": "G1_TEXT_OVERFLOW"},
                {"pair_id": "001", "class": "G1_TEXT_OVERFLOW"},
                {"pair_id": "002", "class": "G7_RENDER_CONTAINMENT_OVERFLOW"}]
    labels = {"000": {"defect_visible": "yes"},
              "001": {"defect_visible": ""},          # blank -> skipped
              "002": {"defect_visible": "no"}}
    by = rep.collect(manifest, labels, "defect_visible")
    assert by["G1_TEXT_OVERFLOW"] == [True]           # 001 dropped
    assert by["G7_RENDER_CONTAINMENT_OVERFLOW"] == [False]


def test_cohen_kappa_perfect_and_chance() -> None:
    assert rep.cohen_kappa([(True, True), (False, False)]) == 1.0
    # total agreement with no variance -> kappa defined as 1.0
    assert rep.cohen_kappa([(True, True), (True, True)]) == 1.0
    # systematic disagreement -> negative kappa
    assert rep.cohen_kappa([(True, False), (False, True)]) < 0
