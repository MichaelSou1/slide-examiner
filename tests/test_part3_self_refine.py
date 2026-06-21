"""Tests for the P10 self-refine vehicle (offline; fake generator + offline linter)."""
import json

from slide_examiner.feedback_sources import build_feedback_source
from slide_examiner.optim_runtime import OptimizerRunConfig
from slide_examiner.self_refine import refinement_summary, run_self_refine
from slide_examiner.skill_doc import WEAK_PROMPT_MODULES


def _gen(slides):
    payload = json.dumps({"deck_id": "d", "scenario": "launch", "slides": slides})
    return lambda messages: payload


def _cfg():
    return OptimizerRunConfig(condition="linter", carrier="gepa", train_tasks="x", val_tasks="x", render=False).generator_config()


def test_self_refine_runs_and_records_per_iteration(tmp_path):
    task = {"task_id": "t", "rubric": {"required_sections": ["background", "solution"], "target_slides": 2}}
    slides = [{"title": "Background", "bullets": ["a"], "section": "background"},
              {"title": "Solution", "bullets": ["b"], "section": "solution"}]
    feedback = build_feedback_source("linter")  # offline
    hist = run_self_refine(task, WEAK_PROMPT_MODULES, _cfg(), feedback, n_iters=3,
                           complete=_gen(slides), render=False, out_dir=tmp_path / "sr", seed=0)
    assert len(hist) == 3
    for h in hist:
        assert "quality" in h and 0.0 <= h["quality"] <= 1.0
        assert "selection_score" in h and h["iter"] in (0, 1, 2)
    s = refinement_summary(hist, q_threshold=0.5)
    assert set(("initial", "final", "best", "gain", "iters_to_threshold", "quality_curve")).issubset(s)
    assert len(s["quality_curve"]) == 3


def test_self_refine_degenerate_is_handled(tmp_path):
    task = {"task_id": "t", "rubric": {"required_sections": ["background"]}}
    feedback = build_feedback_source("linter")
    hist = run_self_refine(task, WEAK_PROMPT_MODULES, _cfg(), feedback, n_iters=2,
                           complete=lambda m: "not json", render=False, out_dir=tmp_path / "sr2", seed=0)
    assert len(hist) == 2
    assert all(h["degenerate"] for h in hist)
    assert all(h["quality"] == 0.0 for h in hist)
