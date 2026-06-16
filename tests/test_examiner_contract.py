import json

import pytest

from slide_examiner.examiner_contract import (
    DeckExamRequest,
    DefectType,
    ExamLevel,
    Modality,
    PageExamRequest,
    SeverityLevel,
    deck_request_from_sample,
    deck_result_from_labels,
    page_request_from_sample,
    page_result_from_labels,
    parse_deck_result,
    parse_page_result,
    request_from_sample,
)
from slide_examiner.runtime import runtime_payload_from_sample
from slide_examiner.schemas import BBox, Deck, DefectLabel, Element, ManifestSample, Slide
from slide_examiner.taxonomy import DefectType as TaxonomyDefectType


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


def deck_sample() -> ManifestSample:
    deck = Deck(
        "d1",
        (
            Slide("p1", (Element("t1", "title", BBox(0, 0, 200, 40), text="Problem"),)),
            Slide("p2", (Element("t2", "title", BBox(0, 0, 200, 40), text="Solution"),)),
        ),
    )
    return ManifestSample(
        sample_id="deck1",
        deck=deck,
        labels=(DefectLabel("S2_NARRATIVE_ORDER_BREAK", 1, ("p2", "p1"), {"swapped_indices": [0, 1]}),),
    )


def test_contract_imports_defect_type_from_taxonomy() -> None:
    assert DefectType is TaxonomyDefectType
    assert {item.value for item in DefectType} >= {"G1_TEXT_OVERFLOW", "S5_MISSING_LOGIC_SECTION"}


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


def test_deck_request_rejects_page_scoped_defect() -> None:
    with pytest.raises(ValueError):
        deck_request_from_sample(
            deck_sample(),
            modality=Modality.B_STRUCT_ONLY,
            check_scope=[DefectType.S1_TITLE_BODY_MISMATCH],
        )


def test_request_from_sample_preserves_deck_level() -> None:
    request = request_from_sample(deck_sample(), modality=Modality.B_STRUCT_ONLY)
    assert isinstance(request, DeckExamRequest)
    assert request.level == ExamLevel.DECK
    assert [item.value for item in request.check_scope] == [
        "S2_NARRATIVE_ORDER_BREAK",
        "S3_TERMINOLOGY_INCONSISTENCY",
        "S5_MISSING_LOGIC_SECTION",
    ]


def test_page_result_rejects_deck_label_and_deck_result_rejects_page_label() -> None:
    with pytest.raises(ValueError):
        page_result_from_labels(
            ManifestSample(
                sample_id="bad-page",
                slide=slide_sample().slide,
                labels=(DefectLabel("S2_NARRATIVE_ORDER_BREAK", 1, ("p1",)),),
            )
        )

    with pytest.raises(ValueError):
        deck_result_from_labels(
            ManifestSample(
                sample_id="bad-deck",
                deck=deck_sample().deck,
                labels=(DefectLabel("S1_TITLE_BODY_MISMATCH", 1, ("p1",)),),
            )
        )


def test_deck_result_parse_roundtrip() -> None:
    result = deck_result_from_labels(deck_sample())
    parsed = parse_deck_result(result.model_dump_json())
    assert parsed.deck_id == "d1"
    assert parsed.findings[0].locator.level == ExamLevel.DECK


def test_runtime_payload_always_uses_modality_c(tmp_path) -> None:
    image = tmp_path / "slide.png"
    image.write_bytes(b"png")
    manifest = ManifestSample(
        sample_id="runtime1",
        slide=slide_sample().slide,
        image_path=str(image),
        labels=slide_sample().labels,
    )
    request = request_from_sample(manifest, modality=Modality.C_BOTH)
    assert isinstance(request, PageExamRequest)

    payload = runtime_payload_from_sample(manifest)
    assert payload["modality"] == "C"
    content = payload["messages"][1]["content"]
    assert any(item["type"] == "image_url" for item in content)
    assert any(item["type"] == "text" and "ELEMENTS:" in item["text"] for item in content)


def test_page_result_rejects_bad_has_defect_invariant() -> None:
    result = page_result_from_labels(slide_sample()).model_dump(mode="json")
    result["has_defect"] = False
    with pytest.raises(ValueError):
        parse_page_result(result)
