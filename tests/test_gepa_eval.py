import pytest

from slide_examiner.gepa_eval import evaluate_hybrid_feedback, make_gepa_metric
from slide_examiner.gepa_runner import GEPARunConfig, build_gepa_condition_plan


def examiner_output() -> dict:
    return {
        "defects": [
            {
                "type": "G1_TEXT_OVERFLOW",
                "element_ids": ["title"],
                "severity": 24,
                "fix": "shorten the title or enlarge the text box",
            }
        ],
        "overall_score": 0.5,
    }


def test_evaluate_hybrid_feedback() -> None:
    result = evaluate_hybrid_feedback(linter_score=0.8, examiner_output=examiner_output())
    assert result.score == pytest.approx(0.68)
    assert "G1_TEXT_OVERFLOW" in result.feedback
    assert result.details["defect_count"] == 1


def test_make_gepa_metric() -> None:
    metric = make_gepa_metric(lambda candidate: 1.0, lambda candidate: {"defects": [], "overall_score": 1.0})
    result = metric(object())
    assert result["score"] == 1.0
    assert "feedback" in result


def test_build_gepa_condition_plan() -> None:
    plan = build_gepa_condition_plan(GEPARunConfig("train.jsonl", "val.jsonl", "test.jsonl"))
    assert {item["condition"] for item in plan} == {
        "linter",
        "zero_shot_8b",
        "zero_shot_30b",
        "finetuned_8b",
        "hybrid",
    }
