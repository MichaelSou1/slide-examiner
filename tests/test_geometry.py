from slide_examiner.geometry import (
    detect_alignment_offsets,
    detect_brand_color_violations,
    detect_font_size_inconsistencies,
    detect_margin_violations,
    detect_overlaps,
    detect_text_overflow,
    lint_slide,
)
from slide_examiner.schemas import BBox, Element, Slide


def make_slide() -> Slide:
    return Slide(
        slide_id="s1",
        elements=(
            Element(
                element_id="title",
                type="text",
                bbox=BBox(100, 80, 200, 40),
                text="A very long title that should not fit",
                style={"text_box_capacity": 8},
            ),
            Element(element_id="box1", type="shape", bbox=BBox(400, 200, 200, 100)),
            Element(element_id="box2", type="shape", bbox=BBox(450, 220, 200, 100)),
            Element(
                element_id="aligned",
                type="shape",
                bbox=BBox(120, 240, 100, 80),
                metadata={"expected_bbox": {"x": 100, "y": 240, "width": 100, "height": 80}},
            ),
            Element(element_id="edge", type="shape", bbox=BBox(8, 500, 100, 80)),
            Element(
                element_id="font_bad",
                type="text",
                bbox=BBox(200, 600, 160, 60),
                text="Peer",
                style={"font_size_pt": 32},
                metadata={"expected_font_size_pt": 24},
            ),
            Element(
                element_id="color_bad",
                type="shape",
                bbox=BBox(400, 600, 120, 80),
                style={"color": "#ff00ff"},
                metadata={"expected_color": "#000000"},
            ),
        ),
    )


def test_bbox_iou() -> None:
    assert round(BBox(0, 0, 100, 100).iou(BBox(50, 0, 100, 100)), 3) == 0.333


def test_detect_text_overflow() -> None:
    labels = detect_text_overflow(make_slide())
    assert labels[0].type == "G1_TEXT_OVERFLOW"
    assert labels[0].target_element_ids == ("title",)


def test_detect_overlaps() -> None:
    labels = detect_overlaps(make_slide(), min_iou=0.05)
    assert labels
    assert labels[0].target_element_ids == ("box1", "box2")


def test_detect_alignment_offsets() -> None:
    labels = detect_alignment_offsets(make_slide(), min_offset_px=4)
    assert labels[0].type == "G3_ALIGNMENT_OFFSET"
    assert labels[0].severity == 20


def test_detect_margin_violations() -> None:
    labels = detect_margin_violations(make_slide(), margin_px=32)
    assert labels[0].target_element_ids == ("edge",)
    assert labels[0].metadata["left"] == 24


def test_detect_font_size_inconsistencies() -> None:
    labels = detect_font_size_inconsistencies(make_slide(), min_delta_pt=1)
    assert labels[0].type == "G4_FONT_SIZE_INCONSISTENCY"
    assert labels[0].target_element_ids == ("font_bad",)


def test_detect_brand_color_violations() -> None:
    labels = detect_brand_color_violations(make_slide(), min_delta_e=3)
    assert labels[0].type == "G5_BRAND_COLOR_VIOLATION"
    assert labels[0].target_element_ids == ("color_bad",)


def test_lint_slide_aggregates() -> None:
    labels = lint_slide(make_slide())
    assert {label.type for label in labels} >= {
        "G1_TEXT_OVERFLOW",
        "G2_ELEMENT_OVERLAP",
        "G3_ALIGNMENT_OFFSET",
        "G4_FONT_SIZE_INCONSISTENCY",
        "G5_BRAND_COLOR_VIOLATION",
        "G6_MARGIN_VIOLATION",
    }
