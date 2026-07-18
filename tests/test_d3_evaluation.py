import json
import subprocess

import pytest

from scripts.part3_d3_evaluate import assert_final_test_unlocked, materialize_paired_images
from slide_examiner.d3_evaluation import (
    exact_mcnemar, generated_route_action, holm_family, normalize_runtime_row, pareto_frontier,
    parse_generated_contract, prompt_row, score_arm, route_requires_heads, validate_deployment,
)


def _row(sample, defect, clean, predicted, **extra):
    return {"sample_id": sample, "pair_id": sample.removesuffix("_clean"),
            "defect": defect, "is_clean": clean, "predicted_types": predicted,
            "has_defect": bool(predicted), "failure": False, **extra}


def test_score_arm_reports_paired_metrics_ci_routing_and_cost():
    rows = [
        _row("a", "G7_X", False, ["G7_X"], localization_valid=True,
             predicted_action="ANSWER", target_action="ANSWER", confidence=.9,
             model_calls=1, external_calls=0, total_tokens=100, latency_seconds=1),
        _row("a_clean", "G7_X", True, [], predicted_action="ANSWER",
             target_action="ANSWER", confidence=.8, model_calls=1, external_calls=0,
             total_tokens=80, latency_seconds=.8),
        _row("b", "G7_X", False, [], predicted_action="DEFER",
             target_action="ANSWER", deferred=True, confidence=.2, model_calls=1,
             external_calls=0, total_tokens=50, latency_seconds=.5),
        _row("b_clean", "G7_X", True, ["G7_X"], predicted_action="ANSWER",
             target_action="ANSWER", confidence=.7, model_calls=1, external_calls=0,
             total_tokens=70, latency_seconds=.7),
    ]
    result = score_arm(rows)
    cell = result["per_class"]["G7_X"]
    assert (cell["tp"], cell["fn"], cell["fp"], cell["tn"]) == (1, 1, 1, 1)
    assert cell["balanced_accuracy"]["estimate"] == .5
    assert cell["named_localization"]["estimate"] == 1.0
    assert result["routing_and_cost"]["action_accuracy"] == .75
    assert result["routing_and_cost"]["coverage"] == .75
    assert result["routing_and_cost"]["mean_total_tokens"] == 75


def test_exact_mcnemar_and_holm_family():
    left = [{"pair_id": str(i), "correct": i < 8} for i in range(10)]
    right = [{"pair_id": str(i), "correct": i < 2} for i in range(10)]
    test = exact_mcnemar(left, right)
    assert test["left_wins"] == 6 and test["right_wins"] == 0
    assert test["p_value"] == 0.03125
    family = holm_family([{"name": "a", "p_value": .01},
                          {"name": "b", "p_value": .2}])
    assert family["tests"][0]["adjusted_p"] == .02
    assert family["tests"][0]["reject"] is True


def test_pareto_frontier_drops_dominated_arm():
    points = [{"arm": "a", "accuracy": .8, "cost": 2},
              {"arm": "b", "accuracy": .8, "cost": 1},
              {"arm": "c", "accuracy": .9, "cost": 3}]
    assert {point["arm"] for point in pareto_frontier(points)} == {"b", "c"}


def test_normalize_runtime_row_uses_post_escalation_answer():
    row = normalize_runtime_row({
        "sample_id": "pair-a-positive", "pair_id": "pair-a", "defect": "G2_X",
        "is_clean": False, "predicted_action": "CALL_LINTER", "route_confidence": .8,
        "parsed": {"has_defect": False, "findings": []},
        "escalation": {"performed": True, "final_action": "ANSWER", "final_parsed": {
            "has_defect": True, "findings": [{"type": "G2_X", "locator": {"page_id": "p1"}}],
        }}, "model_calls": 1, "external_calls": 1,
    }, arm="d3_generic")
    assert row["predicted_action"] == "ANSWER"
    assert row["predicted_types"] == ["G2_X"]
    assert row["localization_valid"] is True
    assert row["correct"] is True


def test_normalize_runtime_row_marks_parser_fallback_as_failure():
    row = normalize_runtime_row({
        "sample_id": "bad", "defect": "G7_X", "predicted_action": "DEFER",
        "parse_error": "ValueError: no JSON object", "parsed": {"findings": []},
    })
    assert row["failure"] is True


def test_prompt_modes_are_detached_and_c3_is_atomic():
    row = {"defect": "G7_UNREADABLE_TEXT", "messages": [{"role": "user", "content": [
        {"type": "image", "image": "slide.png"}, {"type": "text", "text": "Inspect."},
    ]}]}
    generic = prompt_row(row, "generic")
    c3 = prompt_row(row, "c3")
    assert generic == row and generic is not row
    assert row["messages"][0]["content"][1]["text"] == "Inspect."
    assert "ATOMIC_CHECK" in c3["messages"][0]["content"][1]["text"]
    assert "G7_UNREADABLE_TEXT" in c3["messages"][0]["content"][1]["text"]


def test_parse_contract_repairs_non_answer_routing_envelope_without_findings():
    parsed, error, repaired = parse_generated_contract(json.dumps({
        "action": "CALL_LINTER", "confidence": .95,
        "requested_context": "presentation_quality", "evidence_source": "image_only",
        "has_defect": None, "findings": None, "clean_dimensions": None,
    }), {"sample_id": "sample-a", "defect": "G2_ELEMENT_OVERLAP"})
    assert error is None and repaired is True
    assert parsed["page_id"] == "sample-a"
    assert parsed["action"] == "CALL_LINTER"
    assert parsed["has_defect"] is False and parsed["findings"] == []
    assert parsed["requested_context"] == ["structure"]
    assert parsed["evidence_source"] == "none"


def test_generated_external_action_is_not_renamed_by_zero_escalation_budget():
    parsed, error, _ = parse_generated_contract(json.dumps({
        "action": "REQUEST_REFERENCE", "confidence": .9,
        "requested_context": ["reference"], "evidence_source": "none",
        "has_defect": False, "findings": [], "clean_dimensions": [],
    }), {"record_id": "row-a", "defect": "S4_DENSITY"})
    assert error is None and parsed["action"] == "REQUEST_REFERENCE"
    assert generated_route_action(parsed["action"]) == "REQUEST_REFERENCE"
    assert generated_route_action(parsed["action"], terminal=True) == "DEFER"


def test_parse_contract_repairs_common_zero_shot_answer_shape():
    parsed, error, repaired = parse_generated_contract(json.dumps({
        "action": "ANSWER", "confidence": 1.0, "requested_context": "",
        "evidence_source": "image_only", "has_defect": False, "findings": [],
        "clean_dimensions": {"width": 1920, "height": 1080},
    }), {"sample_id": "page-a", "defect": "G2_ELEMENT_OVERLAP"})
    assert error is None and repaired is True
    assert parsed["page_id"] == "page-a"
    assert parsed["action"] == "ANSWER"
    assert parsed["requested_context"] == []
    assert parsed["evidence_source"] == "pixels"
    assert parsed["clean_dimensions"] == []


def test_parse_contract_repairs_part2_legacy_clean_dimensions():
    parsed, error, repaired = parse_generated_contract(json.dumps({
        "has_defect": False, "findings": [],
        "clean_dimensions": ["visible_text", "alignment", "typography",
                             "title_fit", "figure_quality", "brand_element"],
    }), {"record_id": "page-b", "defect": "G7_RENDER_CONTAINMENT_OVERFLOW"})
    assert error is None and repaired is True
    assert parsed["page_id"] == "page-b"
    assert parsed["action"] == "ANSWER"
    assert parsed["clean_dimensions"] == ["text_fit", "alignment", "typography"]


@pytest.mark.parametrize(("run", "merged", "adapter", "mode", "error"), [
    (None, None, None, "sample", "--run is required"),
    (None, "merged", None, "answer", "--merged-model requires --run"),
    ("d3", None, "part2", "answer", "--lm-adapter is only valid"),
    (None, None, "part2", "answer", None),
    ("d3", None, None, "sample", None),
])
def test_lm_only_deployment_guards(run, merged, adapter, mode, error):
    from pathlib import Path

    actual = validate_deployment(
        Path(run) if run else None, Path(merged) if merged else None,
        Path(adapter) if adapter else None, mode)
    if error:
        assert error in actual
    else:
        assert actual is None


@pytest.mark.parametrize(("mode", "expected"), [
    ("sample", True), ("class", False), ("fixed", False), ("answer", False),
])
def test_only_sample_router_requires_heads(mode, expected):
    assert route_requires_heads(mode) is expected


def test_materialize_paired_images_preserves_defect_on_clean_twin(tmp_path):
    clean = {"slide_id": "clean", "width": 10, "height": 10, "elements": []}
    defective = {"slide_id": "defective", "width": 10, "height": 10, "elements": []}
    (tmp_path / "clean.json").write_text(json.dumps(clean))
    (tmp_path / "defective.json").write_text(json.dumps(defective))
    row = {"sample_id": "pair-1", "labels": [{"type": "G2_ELEMENT_OVERLAP", "severity": 1}],
           "pair": {"clean_image_path": "clean.png", "defective_image_path": "defective.png",
                    "clean_slide_path": "clean.json", "defective_slide_path": "defective.json"}}
    records, summary = materialize_paired_images([row], tmp_path, 1)
    initial = records[:summary["initial_limit"]]
    assert len(initial) == 2 and {item["is_clean"] for item in initial} == {False, True}
    assert {item["defect"] for item in initial} == {"G2_ELEMENT_OVERLAP"}
    assert {item["pair_id"] for item in initial} == {"pair-1"}
    assert all(item["availability"] == "image_only" for item in initial)
    assert len(records) == 4 and records[-1]["availability"] == "image_structure"


def test_materialize_paired_images_uses_requested_split(tmp_path):
    (tmp_path / "clean.json").write_text(json.dumps({"elements": []}))
    (tmp_path / "defective.json").write_text(json.dumps({"elements": []}))
    row = {"sample_id": "pair-1", "labels": [{"type": "G2_ELEMENT_OVERLAP"}],
           "pair": {"clean_image_path": "clean.png", "defective_image_path": "defective.png",
                    "clean_slide_path": "clean.json", "defective_slide_path": "defective.json"}}
    records, _ = materialize_paired_images([row], tmp_path, 1, split="final_test")
    assert {record["split"] for record in records} == {"final_test"}


def test_final_test_guard_requires_committed_clean_registry(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    registry = tmp_path / "freeze.json"
    payload = {key: "x" for key in ("checkpoint", "policy", "primary_comparisons",
                                     "table_schema", "one_shot_command",
                                     "final_test_protocol_sha256")}
    payload["freeze_commit"] = "not-a-commit"
    registry.write_text(json.dumps(payload))
    subprocess.run(["git", "add", "freeze.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "freeze"], cwd=tmp_path, check=True)
    with pytest.raises(RuntimeError, match="freeze_commit"):
        assert_final_test_unlocked(tmp_path, registry)
