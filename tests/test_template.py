from slide_examiner.generator import deck_from_content_json
from slide_examiner.experiment import inject_slide_defect
from slide_examiner.geometry import detect_overlaps, detect_text_overflow
from slide_examiner.template import snap_slide_to_master


def _slide():
    deck = deck_from_content_json(
        {"deck_id": "t", "slides": [{"title": "Quarterly revenue overview", "bullets": ["a", "b", "c"]}]}
    )
    return deck.slides[0]


def test_template_absorbs_overlap():
    inj = inject_slide_defect(_slide(), "G2_ELEMENT_OVERLAP", severity=0.4)
    assert detect_overlaps(inj.defective, min_iou=0.01)  # defect present freeform
    snapped = snap_slide_to_master(inj.defective)
    assert not detect_overlaps(snapped, min_iou=0.01)  # template absorbs it


def test_template_absorbs_overflow():
    inj = inject_slide_defect(_slide(), "G1_TEXT_OVERFLOW", severity=64.0)
    assert detect_text_overflow(inj.defective)  # defect present freeform
    snapped = snap_slide_to_master(inj.defective)
    assert not detect_text_overflow(snapped)  # template snaps the box back


def test_template_keeps_semantic_defect_text():
    inj = inject_slide_defect(_slide(), "S1_TITLE_BODY_MISMATCH")
    title = next(e for e in inj.defective.elements if e.element_id.endswith("title"))
    snapped = snap_slide_to_master(inj.defective)
    snapped_title = next(e for e in snapped.elements if e.element_id.endswith("title"))
    # The mismatched title text survives the template (only geometry is snapped).
    assert snapped_title.text == title.text
    assert "Unrelated" in snapped_title.text
