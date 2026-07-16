import json
from pathlib import Path

import pytest

from slide_examiner.d3_training import (
    ACTION_TO_ID, _answer_for, action_class_weights, action_sample_weights,
    authoritative_result, balanced_smoke_rows, build_d3_training_records,
    evaluate_semantic_gate, relocate_path, run_linter,
)


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


def test_action_class_weights_upweight_rare_routes():
    rows = ([{"action_id": ACTION_TO_ID["ANSWER"]}] * 16
            + [{"action_id": action_id} for action, action_id in ACTION_TO_ID.items()
               if action != "ANSWER"])
    weights = action_class_weights(rows)
    assert weights[ACTION_TO_ID["CALL_LINTER"]] > weights[ACTION_TO_ID["ANSWER"]]
    assert abs(sum(weights) / len(weights) - 1.0) < 1e-8


def test_action_class_weights_require_every_route():
    with pytest.raises(ValueError, match="missing route actions"):
        action_class_weights([{"action_id": ACTION_TO_ID["ANSWER"]}])


def test_action_sample_weights_equalise_class_mass():
    rows = ([{"action_id": ACTION_TO_ID["ANSWER"]}] * 4
            + [{"action_id": action_id} for action, action_id in ACTION_TO_ID.items()
               if action != "ANSWER"])
    weights = action_sample_weights(rows)
    mass = {action_id: sum(weight for row, weight in zip(rows, weights, strict=True)
                           if row["action_id"] == action_id) for action_id in ACTION_TO_ID.values()}
    assert set(mass.values()) == {1.0}


def test_route_head_is_authoritative_and_strips_generated_finding():
    generated = {
        "page_id": "p1", "has_defect": True,
        "findings": [{"type": "G2_ELEMENT_OVERLAP", "severity": "moderate",
                      "locator": {"level": "page", "page_id": "p1", "element_id": "a",
                                  "bbox": None, "related_page_ids": []},
                      "evidence": "Elements a and b visibly overlap on page p1.",
                      "fix_suggestion": "Move element b away from element a."}],
        "clean_dimensions": [], "action": "ANSWER", "confidence": 0.9,
        "requested_context": [], "evidence_source": "pixels",
    }
    result, mismatch, error = authoritative_result(generated, "CALL_LINTER")
    assert mismatch is True
    assert error is None
    assert result["action"] == "CALL_LINTER"
    assert result["findings"] == []
    assert result["requested_context"] == ["structure"]


def test_call_linter_executes_structure_and_returns_final_answer():
    context = {
        "availability": "image_structure",
        "structure": {
            "slide_id": "p1", "width": 100, "height": 100,
            "elements": [
                {"element_id": "a", "type": "shape",
                 "bbox": {"x": 0, "y": 0, "width": 50, "height": 50}},
                {"element_id": "b", "type": "shape",
                 "bbox": {"x": 10, "y": 10, "width": 50, "height": 50}},
            ],
        },
    }
    row = {"sample_id": "s1", "messages": [{"content": [
        {"type": "text", "text": "generic\nINPUT_CONTEXT=" + json.dumps(context)}]}]}
    result = run_linter(row)
    assert result["action"] == "ANSWER"
    assert result["evidence_source"] == "linter"
    assert any(finding["type"] == "G2_ELEMENT_OVERLAP" for finding in result["findings"])


def test_balanced_rows_reserves_smoke_semantic_cells():
    rows = []
    cells = [
        ("G7_RENDER_CONTAINMENT_OVERFLOW", "image_only", "ANSWER", False),
        ("G2_ELEMENT_OVERLAP", "image_only", "DEFER", False),
        ("G3_ALIGNMENT_OFFSET", "image_only", "DEFER", False),
        ("G4_FONT_SIZE_INCONSISTENCY", "image_only", "DEFER", False),
        ("G5_BRAND_COLOR_VIOLATION", "image_only", "DEFER", False),
        ("G6_MARGIN_VIOLATION", "image_only", "DEFER", False),
        ("G2_ELEMENT_OVERLAP", "image_structure", "CALL_LINTER", False),
        ("S6_IMAGE_TEXT_CONTRADICTION", "image_only", "REQUEST_REFERENCE", False),
        ("S2_NARRATIVE_ORDER_BREAK", "image_structure", "REQUEST_DECK", False),
        ("NO_DEFECT", "deck_context_available", "ANSWER", True),
        ("NO_DEFECT", "image_only", "ANSWER", False),
    ]
    for index, (defect, availability, action, clean_deck) in enumerate(cells):
        rows.append({"record_id": str(index), "defect": defect, "availability": availability,
                     "target_action": action, "task": "route", "is_clean_deck": clean_deck})
    selected = balanced_smoke_rows(rows, len(rows))
    assert {row["record_id"] for row in selected} == {row["record_id"] for row in rows}


def test_semantic_gate_requires_eligible_cells_and_zero_runtime_failures():
    counts = {name: 0 for name in ("parser_failure", "action_loop", "teacher_failure",
                                   "consistency_failure", "escalation_failure")}
    results = [
        {"defect": "G7_RENDER_CONTAINMENT_OVERFLOW", "availability": "image_only",
         "predicted_action": "ANSWER", "parsed": {"findings": [{}]}, "target_action": "ANSWER",
         "escalation": None, "is_clean_deck": False},
        {"defect": "G2_ELEMENT_OVERLAP", "availability": "image_only",
         "predicted_action": "DEFER", "parsed": {"findings": []}, "target_action": "DEFER",
         "escalation": None, "is_clean_deck": False},
        {"defect": "S6_IMAGE_TEXT_CONTRADICTION", "availability": "image_only",
         "predicted_action": "REQUEST_REFERENCE", "parsed": {"findings": []},
         "target_action": "REQUEST_REFERENCE", "is_clean_deck": False,
         "escalation": {"final_action": "ANSWER"}},
        {"defect": "S2_NARRATIVE_ORDER_BREAK", "availability": "image_structure",
         "predicted_action": "REQUEST_DECK", "parsed": {"findings": []},
         "target_action": "REQUEST_DECK", "is_clean_deck": False,
         "escalation": {"final_action": "DEFER"}},
        {"defect": "NO_DEFECT", "availability": "deck_context_available",
         "predicted_action": "ANSWER", "parsed": {"findings": []}, "target_action": "ANSWER",
         "escalation": None, "is_clean_deck": True},
    ]
    assert evaluate_semantic_gate(results, counts)["passed"] is True


def test_pair_records_include_both_orders_with_opposite_targets():
    repo = Path(__file__).resolve().parents[1]
    records, _ = build_d3_training_records(repo, max_per_cell=2)
    grouped = {}
    for row in records:
        if row.get("pair_order") in {"clean_defective", "defective_clean"}:
            grouped.setdefault(row["sample_id"], []).append(row)
    pair = next(rows for rows in grouped.values() if len(rows) == 2)
    assert {row["pair_order"] for row in pair} == {"clean_defective", "defective_clean"}
    assert {row["pair_target"] for row in pair} == {0.0, 1.0}
    assert pair[0]["images"] == list(reversed(pair[1]["images"]))
