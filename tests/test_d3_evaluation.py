import json
import subprocess

import pytest

from scripts.part3_d3_evaluate import assert_final_test_unlocked
from slide_examiner.d3_evaluation import (
    exact_mcnemar, holm_family, normalize_runtime_row, pareto_frontier, prompt_row, score_arm,
    validate_deployment,
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
