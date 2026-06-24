"""Tests for E5 pixel-structure recovery (offline, pure geometry).

Covers the parts that run without a GPU / model weights: class-agnostic NMS,
the pixel-box -> IR-slide projection (frame normalisation), the recovery-fidelity
IoU matcher, and the end-to-end property that the *recovered* linter fires on a
genuine overlap but stays silent on the metadata-only classes (G3/G4/G5) — the
pre-registered falsification branch. The detector forward pass is exercised by the
live eval script ``scripts/part3_e5_recovered.py``.
"""
from slide_examiner.geometry import lint_slide
from slide_examiner.schemas import Slide
from slide_examiner.structure_recovery import (
    NORM_WIDTH, nms_class_agnostic, normalize_gt_slide, recover_slide,
    recovery_fidelity,
)


def _det(img_w=1500, img_h=1125, boxes=()):
    return {"img_w": img_w, "img_h": img_h,
            "dets": [{"bbox_xyxy": list(b), "score": s, "label": lbl}
                     for (b, s, lbl) in boxes]}


def test_nms_drops_cross_class_duplicates() -> None:
    # two near-identical boxes with different labels (the doc_title/paragraph_title
    # duplicate PP-DocLayout emits) must collapse to the higher-scoring one.
    dets = [
        {"bbox_xyxy": [10, 10, 100, 50], "score": 0.9, "label": "doc_title"},
        {"bbox_xyxy": [11, 11, 101, 51], "score": 0.7, "label": "paragraph_title"},
        {"bbox_xyxy": [10, 200, 100, 240], "score": 0.8, "label": "text"},
    ]
    kept = nms_class_agnostic(dets, iou_thr=0.7)
    assert len(kept) == 2
    assert {k["label"] for k in kept} == {"doc_title", "text"}  # higher-scoring dup kept


def test_recover_slide_normalises_to_canonical_frame() -> None:
    det = _det(1500, 1125, boxes=[([150, 0, 750, 562.5], 0.9, "text")])
    slide = recover_slide(det)
    assert slide["width"] == NORM_WIDTH                 # 960
    assert slide["height"] == 720                       # 1125 * 960/1500
    el = slide["elements"][0]
    # 1500 px -> 960 px is a 0.64 scale; x=150 -> 96, w=600 -> 384
    assert abs(el["bbox"]["x"] - 96.0) < 1e-6
    assert abs(el["bbox"]["width"] - 384.0) < 1e-6
    assert slide["metadata"]["structure_recovered"] is True
    assert el["metadata"]["recovered_label"] == "text"


def test_recovered_linter_catches_overlap_but_is_silent_on_fine_geometry() -> None:
    # two clearly overlapping recovered boxes -> linter must flag G2; nothing
    # supplies expected-position / font / colour, so G3/G4/G5 never fire.
    det = _det(960, 720, boxes=[([100, 100, 400, 300], 0.9, "text"),
                                ([250, 150, 550, 350], 0.9, "text")])
    slide = recover_slide(det)
    types = {x.type for x in lint_slide(Slide.from_mapping(slide))}
    assert "G2_ELEMENT_OVERLAP" in types
    assert "G3_ALIGNMENT_OFFSET" not in types
    assert "G4_FONT_SIZE_INCONSISTENCY" not in types
    assert "G5_BRAND_COLOR_VIOLATION" not in types
    assert "G1_TEXT_OVERFLOW" not in types  # no text/capacity on recovered boxes


def test_recovered_linter_silent_when_boxes_separated() -> None:
    det = _det(960, 720, boxes=[([100, 100, 300, 200], 0.9, "text"),
                                ([500, 400, 700, 500], 0.9, "text")])
    slide = recover_slide(det)
    types = {x.type for x in lint_slide(Slide.from_mapping(slide))}
    assert "G2_ELEMENT_OVERLAP" not in types


def test_recovery_fidelity_perfect_and_partial() -> None:
    gt = {"slide_id": "g", "width": 960, "height": 720,
          "elements": [{"element_id": "a", "type": "text",
                        "bbox": {"x": 96, "y": 0, "width": 384, "height": 360}}]}
    gt_norm = normalize_gt_slide(gt)
    # exact-overlap recovered box -> IoU 1.0, recall 1.0
    perfect = recover_slide(_det(960, 720, boxes=[([96, 0, 480, 360], 0.9, "text")]))
    fid = recovery_fidelity(perfect, gt_norm)
    assert fid["recall_at_iou"] == 1.0 and fid["mean_iou_matched"] >= 0.99
    # disjoint recovered box -> no match
    miss = recover_slide(_det(960, 720, boxes=[([600, 500, 700, 600], 0.9, "text")]))
    fid2 = recovery_fidelity(miss, gt_norm)
    assert fid2["recall_at_iou"] == 0.0 and fid2["n_matched"] == 0
