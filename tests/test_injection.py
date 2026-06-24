from slide_examiner.geometry import (
    detect_alignment_offsets,
    detect_brand_color_violations,
    detect_font_size_inconsistencies,
    detect_margin_violations,
    detect_overlaps,
    detect_text_overflow,
)
from slide_examiner.injection import (
    inject_brand_color_violation,
    inject_density_rule_violation,
    inject_font_size_inconsistency,
    inject_image_text_contradiction,
    inject_alignment_offset,
    inject_margin_violation,
    inject_missing_logic_section,
    inject_narrative_order_break,
    inject_overlap,
    inject_terminology_inconsistency,
    inject_text_overflow,
    inject_title_body_mismatch,
)
from slide_examiner.schemas import BBox, Deck, Element, Slide


def base_slide() -> Slide:
    return Slide(
        slide_id="base",
        elements=(
            Element(
                element_id="text1",
                type="text",
                bbox=BBox(100, 100, 240, 80),
                text="Short",
                style={"text_box_capacity": 100},
                metadata={"role": "body"},
            ),
            Element(
                element_id="title",
                type="title",
                bbox=BBox(100, 40, 240, 50),
                text="Product Overview",
                style={"font_size_pt": 24, "color": "#000000"},
                metadata={"role": "title"},
            ),
            Element(element_id="a", type="shape", bbox=BBox(500, 200, 100, 100)),
            Element(element_id="b", type="shape", bbox=BBox(800, 200, 100, 100)),
            Element(
                element_id="diagram",
                type="diagram",
                bbox=BBox(500, 400, 200, 120),
                metadata={"role": "diagram", "diagram_claim": "three-layer architecture"},
            ),
        ),
    )


def base_deck() -> Deck:
    return Deck(
        deck_id="deck",
        slides=(
            base_slide(),
            Slide(
                slide_id="validation",
                elements=(Element("vtext", "text", BBox(100, 100, 300, 80), text="Product validation"),),
                metadata={"section": "validation"},
            ),
        ),
        metadata={"required_sections": ["intro", "validation"], "canonical_term": "Product", "variant_term": "Widget"},
    )


def test_inject_text_overflow_is_detectable() -> None:
    injected = inject_text_overflow(base_slide(), element_id="text1", overflow_px=24, seed=1)
    assert injected.label.type == "G1_TEXT_OVERFLOW"
    assert detect_text_overflow(injected.defective)


def test_inject_overlap_is_detectable() -> None:
    injected = inject_overlap(base_slide(), source_element_id="a", target_element_id="b")
    labels = detect_overlaps(injected.defective, min_iou=0.01)
    assert labels
    assert labels[0].target_element_ids == ("a", "b")


def test_inject_alignment_offset_is_detectable() -> None:
    injected = inject_alignment_offset(base_slide(), element_id="a", offset_px=16)
    labels = detect_alignment_offsets(injected.defective, min_offset_px=4)
    assert labels[0].target_element_ids == ("a",)


def test_inject_margin_violation_is_detectable() -> None:
    injected = inject_margin_violation(base_slide(), element_id="a", bleed_px=20, side="left")
    labels = detect_margin_violations(injected.defective, margin_px=32)
    assert labels[0].severity == 20


def test_inject_font_size_inconsistency_is_detectable() -> None:
    injected = inject_font_size_inconsistency(base_slide(), element_id="title", delta_pt=4)
    labels = detect_font_size_inconsistencies(injected.defective)
    assert labels[0].type == "G4_FONT_SIZE_INCONSISTENCY"


def test_inject_brand_color_violation_is_detectable() -> None:
    injected = inject_brand_color_violation(base_slide(), element_id="title", color="#ff00ff")
    labels = detect_brand_color_violations(injected.defective)
    assert labels[0].type == "G5_BRAND_COLOR_VIOLATION"


def test_semantic_slide_injections_label_expected_defects() -> None:
    injections = [
        inject_title_body_mismatch(base_slide()),
        inject_density_rule_violation(base_slide(), element_id="text1"),
        inject_image_text_contradiction(base_slide()),
    ]
    assert [item.label.type for item in injections] == [
        "S1_TITLE_BODY_MISMATCH",
        "S4_DENSITY_RULE_VIOLATION",
        "S6_IMAGE_TEXT_CONTRADICTION",
    ]


def test_semantic_deck_injections_label_expected_defects() -> None:
    injections = [
        inject_narrative_order_break(base_deck()),
        inject_terminology_inconsistency(base_deck(), canonical="Product", variant="Widget"),
        inject_missing_logic_section(base_deck(), section="validation"),
    ]
    assert [item.label.type for item in injections] == [
        "S2_NARRATIVE_ORDER_BREAK",
        "S3_TERMINOLOGY_INCONSISTENCY",
        "S5_MISSING_LOGIC_SECTION",
    ]


# --------------------------------------------------------------------------- #
# E8 re-operationalisation: G3/G5 as INTERNAL contrast (one item out of line /
# off-colour vs its sibling list — decidable from the slide alone). The linter's
# internal rules (alignment_group / color_group) detect the defective; the clean
# twin lints clean.
# --------------------------------------------------------------------------- #
from slide_examiner.geometry import detect_color_inconsistency, lint_slide  # noqa: E402
from slide_examiner.schemas import BBox, Element, Slide  # noqa: E402


def _bullet_slide() -> Slide:
    return Slide(slide_id="b1", elements=tuple(
        Element(element_id=f"body{i}", type="text", bbox=BBox(144, 180 + i * 90, 1512, 72),
                text=f"Bullet {i}", style={"color": "#111111", "font_size_pt": 18})
        for i in range(3)))


def test_internal_alignment_offset_is_detected_internally() -> None:
    inj = inject_alignment_offset(_bullet_slide(), offset_px=40)
    assert inj.label.metadata["mode"] == "internal"
    g3 = lambda s: [l for l in lint_slide(s) if l.type == "G3_ALIGNMENT_OFFSET"]
    assert not g3(inj.clean)                       # clean column lints clean
    hit = g3(inj.defective)
    assert hit and hit[0].target_element_ids == inj.label.target_element_ids


def test_internal_color_inconsistency_is_detected_internally() -> None:
    inj = inject_brand_color_violation(_bullet_slide(), delta_e=40)
    assert inj.label.metadata["mode"] == "internal"
    assert not detect_color_inconsistency(inj.clean)          # all siblings same colour
    hit = detect_color_inconsistency(inj.defective)
    assert hit and hit[0].target_element_ids == inj.label.target_element_ids


def test_no_sibling_column_falls_back_to_absolute() -> None:
    one = Slide(slide_id="x", elements=(Element(element_id="t", type="text",
                bbox=BBox(96, 72, 800, 60), text="solo", style={"color": "#111111"}),))
    assert inject_alignment_offset(one, offset_px=16).label.metadata["mode"] == "absolute_fallback"
    assert inject_brand_color_violation(one, delta_e=24).label.metadata["mode"] == "absolute_fallback"
