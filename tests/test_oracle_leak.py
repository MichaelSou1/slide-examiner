"""End-to-end regression for the oracle-leak fix (review findings #1 + #5).

Ground-truth / injection-bookkeeping metadata MUST stay on the internal Slide/Deck
IR (the geometry linter and repair read it), but MUST be stripped from the
modality-B / modality-C "oracle" a model perceives. This test builds real injected
manifest samples through the normal dataset path and asserts the forbidden keys are
absent from the modality-B oracle, while the internal IR remains full.
"""

from __future__ import annotations

import json

from slide_examiner.adapters import build_probe_payload
from slide_examiner.dataset import (
    deck_sample_from_injection,
    slide_sample_from_injection,
)
from slide_examiner.geometry import lint_slide
from slide_examiner.injection import (
    inject_font_size_inconsistency,
    inject_narrative_order_break,
)
from slide_examiner.schemas import BBox, Deck, Element, Slide


# Forbidden substrings: a subset of the ground-truth keys that the chosen
# injections actually plant, plus container/element keys seeded on the fixtures.
FORBIDDEN_SUBSTRINGS = (
    "narrative_order_broken",
    "expected_font_size_pt",
    "expected_color",
    "expected_bbox",
    "required_sections",
    "canonical_term",
    "variant_term",
)


def _slide() -> Slide:
    return Slide(
        slide_id="s1",
        elements=(
            Element(
                element_id="title",
                type="title",
                bbox=BBox(100, 40, 240, 50),
                text="Product Overview",
                style={"font_size_pt": 24, "color": "#0a0a0a"},
                # Seed element-level ground-truth keys to prove they get stripped
                # from the oracle but stay on the IR.
                metadata={
                    "role": "title",
                    "expected_color": "#0a0a0a",
                    "expected_bbox": {"x": 100, "y": 40, "width": 240, "height": 50},
                },
            ),
            Element(
                element_id="body",
                type="text",
                bbox=BBox(100, 120, 300, 200),
                text="Bullet one and two",
                style={"font_size_pt": 18},
                metadata={"role": "body"},
            ),
        ),
    )


def _deck() -> Deck:
    return Deck(
        deck_id="d1",
        slides=(
            Slide(
                slide_id="intro",
                elements=(Element("itext", "text", BBox(100, 100, 300, 80), text="Intro"),),
                metadata={"section": "intro"},
            ),
            Slide(
                slide_id="validation",
                elements=(Element("vtext", "text", BBox(100, 100, 300, 80), text="Validation"),),
                metadata={"section": "validation"},
            ),
        ),
        metadata={
            "required_sections": ["intro", "validation"],
            "canonical_term": "Product",
            "variant_term": "Widget",
        },
    )


def test_modality_b_oracle_has_no_groundtruth_leak(tmp_path) -> None:
    # S2 narrative-order injection on a deck, full path through dataset.
    injected_deck = inject_narrative_order_break(_deck(), first_index=0, second_index=1)
    deck_sample = deck_sample_from_injection(
        injected_deck, sample_id="deck0", output_dir=tmp_path
    )

    # G4 font-size injection on a slide, full path through dataset.
    injected_slide = inject_font_size_inconsistency(_slide(), element_id="title", delta_pt=6.0)
    slide_sample = slide_sample_from_injection(
        injected_slide, sample_id="slide0", output_dir=tmp_path
    )

    for sample in (deck_sample, slide_sample):
        payload = build_probe_payload(sample, modality="B", task="T1")
        assert payload["oracle"] is not None
        serialized = json.dumps(payload["oracle"])
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in serialized, (
                f"{forbidden!r} leaked into modality-B oracle for {sample.sample_id}"
            )


def test_internal_ir_still_full_and_g4_still_linted(tmp_path) -> None:
    injected_slide = inject_font_size_inconsistency(_slide(), element_id="title", delta_pt=6.0)
    slide_sample = slide_sample_from_injection(
        injected_slide, sample_id="slide1", output_dir=tmp_path
    )

    # The internal IR (the defective slide on the sample) still carries the
    # ground-truth bookkeeping the linter/repair rely on.
    defective = slide_sample.slide
    title = defective.get("title")
    assert title.metadata.get("expected_font_size_pt") == 24
    assert title.metadata.get("expected_color") == "#0a0a0a"
    assert title.metadata.get("expected_bbox") is not None

    # The linter reads the full IR, NOT the oracle, so it still flags the G4 defect.
    labels = lint_slide(defective)
    g4 = [label for label in labels if label.type == "G4_FONT_SIZE_INCONSISTENCY"]
    assert g4, "lint_slide should still detect the injected G4 defect on the defective slide"
    assert "title" in g4[0].target_element_ids


def test_internal_deck_ir_still_full(tmp_path) -> None:
    injected_deck = inject_narrative_order_break(_deck(), first_index=0, second_index=1)
    deck_sample = deck_sample_from_injection(
        injected_deck, sample_id="deck1", output_dir=tmp_path
    )

    # Deck-level ground-truth bookkeeping survives on the IR.
    assert deck_sample.deck.metadata.get("narrative_order_broken") is True
    assert deck_sample.deck.metadata.get("required_sections") == ["intro", "validation"]


def test_bprime_caption_is_populated(tmp_path) -> None:
    injected_slide = inject_font_size_inconsistency(_slide(), element_id="title", delta_pt=6.0)
    slide_sample = slide_sample_from_injection(
        injected_slide, sample_id="slide2", output_dir=tmp_path
    )
    assert isinstance(slide_sample.caption, str)
    assert slide_sample.caption != ""

    payload = build_probe_payload(slide_sample, modality="B_prime", task="T1")
    assert payload["caption"]
