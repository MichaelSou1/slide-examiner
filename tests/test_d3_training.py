import json
from pathlib import Path

from slide_examiner.d3_training import ACTION_TO_ID, _answer_for, relocate_path


def test_relocate_frozen_machine_path(tmp_path: Path):
    target = tmp_path / "data/x/a.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"png")
    value = "/home/gpus/slide-examiner/data/x/a.png"
    assert relocate_path(value, tmp_path) == target.resolve()


def test_action_ids_cover_contract_actions():
    assert set(ACTION_TO_ID) == {"ANSWER", "CALL_LINTER", "REQUEST_REFERENCE", "REQUEST_DECK", "DEFER"}
    assert len(set(ACTION_TO_ID.values())) == 5


def test_distill_target_preserves_teacher_locator_and_evidence():
    sample = {
        "sample_id": "g7", "slide": {"slide_id": "g7", "width": 1280, "height": 720,
        "elements": []}, "labels": [{"type": "G7_RENDER_CONTAINMENT_OVERFLOW", "severity": 1,
        "target_element_ids": ["card_main"]}], "metadata": {}, "pair": {},
    }
    target = {
        "target_action": "ANSWER", "availability": "image_only", "target_kind": "distill",
        "distillation_weight": 0.8, "target_finding": {"has_defect": True,
        "locator": {"element": "bottom bullet list", "region": "bottom"}},
    }
    result = _answer_for(sample, target)
    assert result["evidence_source"] == "pixels"
    assert result["findings"][0]["locator"]["element_id"] == "bottom bullet list"
    assert "Teacher-localized" in result["findings"][0]["evidence"]


def test_answer_evidence_source_tracks_available_context():
    sample = {
        "sample_id": "clean", "slide": {"slide_id": "clean", "width": 1280, "height": 720,
        "elements": []}, "labels": [], "metadata": {}, "pair": {},
    }
    target = {"target_action": "ANSWER", "availability": "reference_available",
              "target_kind": "negative", "distillation_weight": 1.0}
    assert _answer_for(sample, target)["evidence_source"] == "reference"
