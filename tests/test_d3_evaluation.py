import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]

from scripts.part3_d3_evaluate import (
    _api_messages, _relocatable, assert_final_test_unlocked, drop_availability, materialize_deck_pairs,
    materialize_paired_images, materialize_slideaudit,
)
from slide_examiner.d3_evaluation import (
    endpoint_rows, exact_mcnemar, generated_route_action, holm_family, normalize_runtime_row, pareto_frontier,
    parse_generated_contract, prompt_row, score_arm, selective_risk_at_coverages,
    route_requires_heads, validate_deployment,
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
    left = [{"record_id": str(i), "correct": i < 8} for i in range(10)]
    right = [{"record_id": str(i), "correct": i < 2} for i in range(10)]
    test = exact_mcnemar(left, right)
    assert test["left_wins"] == 6 and test["right_wins"] == 0
    assert test["p_value"] == 0.03125
    family = holm_family([{"name": "a", "p_value": .01},
                          {"name": "b", "p_value": .2}])
    assert family["tests"][0]["adjusted_p"] == .02
    assert family["tests"][0]["reject"] is True


def test_exact_mcnemar_rejects_non_unique_pair_key():
    left = [{"pair_id": "a", "correct": True}, {"pair_id": "a", "correct": False}]
    right = [{"pair_id": "a", "correct": True}]
    with pytest.raises(ValueError, match="duplicate McNemar key"):
        exact_mcnemar(left, right, key="pair_id")


def test_endpoint_rows_uses_only_clean_rows_for_paired_clean_fpr():
    rows = [
        _row("a", "G2_X", False, ["G2_X"], correct=True),
        _row("a_clean", "G2_X", True, ["G2_X"], correct=False),
        _row("b_clean", "G2_X", True, [], correct=True),
    ]
    projected, summary = endpoint_rows(rows, "paired-clean false-positive avoidance")
    assert [row["correct"] for row in projected] == [False, True]
    assert summary == {"canonical_endpoint": "paired_clean_fpr", "eligible_rows": 2,
                       "adverse_events": 1, "adverse_rate": .5}


def test_endpoint_rows_reports_g2_g6_row_risk_as_adverse_rate():
    rows = [_row("a", "G2_X", False, ["G2_X"], correct=True),
            _row("b", "G2_X", False, [], correct=False)]
    projected, summary = endpoint_rows(rows, "G2-G6 row risk")
    assert len(projected) == 2
    assert summary["canonical_endpoint"] == "row_risk"
    assert summary["adverse_rate"] == .5


def test_selective_risk_at_frozen_coverage_grid_reports_unavailable_points():
    rows = [
        {"correct": True, "confidence": .9, "deferred": False, "failure": False},
        {"correct": False, "confidence": .8, "deferred": False, "failure": False},
        {"correct": True, "confidence": .7, "deferred": False, "failure": False},
        {"correct": True, "confidence": .1, "deferred": True, "failure": False},
    ]
    points = selective_risk_at_coverages(rows)
    assert points[0]["covered"] == 2 and points[0]["risk"] == .5
    assert points[1]["covered"] == 3 and points[1]["risk"] == pytest.approx(1 / 3)
    assert points[2]["available"] is False and points[2]["risk"] is None


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


def test_api_messages_embeds_local_image_and_keeps_c3_prompt(tmp_path):
    (tmp_path / "slide.png").write_bytes(b"png")
    row = {"defect": "G7_UNREADABLE_TEXT", "messages": [{"role": "user", "content": [
        {"type": "image", "image": "slide.png"}, {"type": "text", "text": "Inspect."},
    ]}]}
    messages = _api_messages(row, tmp_path, "c3")
    assert messages[0]["role"] == "system"
    image_item, text_item = messages[1]["content"]
    assert image_item["type"] == "image_url"
    assert image_item["image_url"]["url"].startswith("data:image/png;base64,")
    assert "ATOMIC_CHECK" in text_item["text"]


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


def test_materialize_paired_images_supports_disjoint_per_class_offset(tmp_path):
    for index in range(2):
        (tmp_path / f"clean-{index}.json").write_text(json.dumps({"elements": []}))
        (tmp_path / f"defective-{index}.json").write_text(json.dumps({"elements": []}))
    rows = [{
        "sample_id": f"pair-{index}", "labels": [{"type": "G2_ELEMENT_OVERLAP"}],
        "pair": {"clean_image_path": f"clean-{index}.png",
                 "defective_image_path": f"defective-{index}.png",
                 "clean_slide_path": f"clean-{index}.json",
                 "defective_slide_path": f"defective-{index}.json"},
    } for index in range(2)]
    records, summary = materialize_paired_images(rows, tmp_path, 1, offset_per_class=1)
    assert summary["offset_per_class"] == 1
    assert {record["pair_id"] for record in records} == {"pair-1"}


def test_drop_availability_preserves_initial_records_and_other_counterparts():
    rows = [{"record_id": "a", "availability": "image_only"},
            {"record_id": "b", "availability": "image_structure"},
            {"record_id": "c", "availability": "reference_available"}]
    kept, summary = drop_availability(rows, "image_structure")
    assert [row["record_id"] for row in kept] == ["a", "c"]
    assert summary["removed_counterparts"] == 1 and summary["initial_records"] == 1


def test_materialize_deck_pairs_uses_deck_contract_and_paired_clean(tmp_path):
    for name in ("p0.png", "p1.png", "c0.png", "c1.png"):
        (tmp_path / name).write_bytes(b"png")
    positive = {"sample_id": "deck-a", "labels": [{"type": "S2_NARRATIVE_ORDER_BREAK"}],
                "metadata": {"page_image_paths": ["p0.png", "p1.png"]}}
    clean = {"sample_id": "deck-a__CLEAN", "labels": [],
             "metadata": {"page_image_paths": ["c0.png", "c1.png"]}}
    rows, summary = materialize_deck_pairs([positive], [clean], tmp_path, 1)
    assert summary["initial_limit"] == 2 and len(rows) == 4
    assert {row["is_clean"] for row in rows[:2]} == {False, True}
    assert all(row["target_action"] == "REQUEST_DECK" for row in rows[:2])
    assert all(row["availability"] == "deck_context_available" for row in rows[2:])
    messages = _api_messages(rows[2], tmp_path, "generic")
    assert '"deck_id"' in messages[-1]["content"][-1]["text"]
    assert "S2_NARRATIVE_ORDER_BREAK" in messages[-1]["content"][-1]["text"]


def test_materialize_deck_pairs_supports_final_test_pair_pointer(tmp_path):
    positive = {"sample_id": "deck-a", "labels": [{"type": "S5_MISSING_LOGIC_SECTION"}],
                "metadata": {"page_image_paths": ["positive.png"]}}
    clean = {"sample_id": "deck-a_CLEAN_DECK", "labels": [],
             "pair": {"paired_positive_id": "deck-a"},
             "metadata": {"page_image_paths": ["clean.png"]}}
    rows, summary = materialize_deck_pairs(
        [positive], [clean], tmp_path, 1, split="final_test")
    assert summary["selected_pairs_per_class"] == {"S5_MISSING_LOGIC_SECTION": 1}
    assert len(rows) == 4
    assert {row["split"] for row in rows} == {"final_test"}
    assert {row["is_clean"] for row in rows[:2]} == {False, True}


def test_materialize_slideaudit_uses_confident_absent_as_named_negative(tmp_path):
    rows = [
        {"sample_id": "sa-pos", "image_path": "pos.png",
         "labels": [{"type": "G1_TEXT_OVERFLOW"}], "metadata": {"confident_absent": []}},
        {"sample_id": "sa-neg", "image_path": "neg.png", "labels": [],
         "metadata": {"confident_absent": ["G1_TEXT_OVERFLOW"]}},
    ]
    output, summary = materialize_slideaudit(rows, tmp_path, 1)
    assert len(output) == 2 and {row["is_clean"] for row in output} == {False, True}
    assert {row["defect"] for row in output} == {"G1_TEXT_OVERFLOW"}
    assert all(row["availability"] == "image_only" for row in output)
    assert summary["native_ir"] is False and summary["native_reference"] is False


@pytest.mark.parametrize("value", [
    "/data/slide-examiner/data/raw/slideaudit/images/slide.png",
    "/home/gpus/slide-examiner/data/raw/slideaudit/images/slide.png",
])
def test_relocatable_strips_historical_checkout_roots(value, tmp_path):
    assert _relocatable(value, tmp_path) == "data/raw/slideaudit/images/slide.png"


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


def test_final_test_commands_expose_separate_guard_repo():
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts/part3_d3_evaluate.py"),
         "materialize", "--help"], capture_output=True, text=True, check=True)
    assert "--guard-repo" in result.stdout
