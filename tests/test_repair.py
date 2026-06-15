from slide_examiner.geometry import lint_slide
from slide_examiner.injection import (
    inject_alignment_offset,
    inject_brand_color_violation,
    inject_font_size_inconsistency,
    inject_margin_violation,
    inject_text_overflow,
)
from slide_examiner.repair import repair_passes_linter, repair_slide
from slide_examiner.schemas import BBox, Element, Slide


def base_slide() -> Slide:
    return Slide(
        slide_id="repair",
        elements=(
            Element("title", "title", BBox(100, 50, 300, 60), text="Title text", style={"font_size_pt": 24, "color": "#000000"}, metadata={"role": "title"}),
            Element("body", "text", BBox(100, 150, 400, 80), text="Body text", style={"font_size_pt": 22}, metadata={"role": "body"}),
            Element("shape", "shape", BBox(900, 150, 120, 120)),
        ),
    )


def assert_repaired(injected) -> None:
    assert repair_passes_linter(injected.defective, (injected.label,))
    repaired = repair_slide(injected.defective, (injected.label,))
    assert injected.label.type not in {label.type for label in lint_slide(repaired)}


def test_repair_text_overflow() -> None:
    assert_repaired(inject_text_overflow(base_slide(), element_id="title", overflow_px=16))


def test_repair_alignment_font_color_margin() -> None:
    assert_repaired(inject_alignment_offset(base_slide(), element_id="shape", offset_px=16))
    assert_repaired(inject_font_size_inconsistency(base_slide(), element_id="title", delta_pt=4))
    assert_repaired(inject_brand_color_violation(base_slide(), element_id="title", color="#ff00ff"))
    assert_repaired(inject_margin_violation(base_slide(), element_id="shape", side="left", bleed_px=16))

