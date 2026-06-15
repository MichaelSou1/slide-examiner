import json

import pytest

from slide_examiner.examiner_contract import (
    DefectType,
    ExamLevel,
    Modality,
    SeverityLevel,
    page_request_from_sample,
    page_result_from_labels,
    parse_page_result,
)
from slide_examiner.schemas import BBox, DefectLabel, Element, ManifestSample, Slide


def slide_sample() -> ManifestSample:
    slide = Slide(
        "p1",
        (
            Element(
                "title",
                "title",
                BBox(10, 20, 200, 40),
                text="Quarterly update",
                style={"font_size_pt": 24, "color": "#111111"},
                metadata={"role": "title", "expected_bbox": {"x": 0, "y": 0, "width": 200, "height": 40}},
            ),
        ),
        width=1920,
        height=1080,
    )
    return ManifestSample(
        sample_id="s1",
        slide=slide,
        labels=(DefectLabel("G3_ALIGNMENT_OFFSET", 16, ("title",)),),
    )


def test_page_request_filters_oracle_leakage_fields() -> None:
    request = page_request_from_sample(slide_sample(), modality=Modality.B_STRUCT_ONLY)
    assert request.elements is not None
    element = request.elements[0].model_dump(mode="json")
    assert "metadata" not in element
    assert element["placeholder_role"] == "title"
    assert "expected_bbox" not in json.dumps(element)


def test_page_result_uses_ordinal_severity_and_parse_roundtrip() -> None:
    result = page_result_from_labels(slide_sample())
    assert result.findings[0].severity == SeverityLevel.MODERATE
    parsed = parse_page_result(result.model_dump_json())
    assert parsed.page_id == "p1"
    assert parsed.findings[0].locator.level == ExamLevel.PAGE


def test_page_request_rejects_deck_scoped_defect() -> None:
    with pytest.raises(ValueError):
        page_request_from_sample(
            slide_sample(),
            modality=Modality.B_STRUCT_ONLY,
            check_scope=[DefectType.S2_NARRATIVE_ORDER_BREAK],
        )


def test_page_result_rejects_bad_has_defect_invariant() -> None:
    result = page_result_from_labels(slide_sample()).model_dump(mode="json")
    result["has_defect"] = False
    with pytest.raises(ValueError):
        parse_page_result(result)
