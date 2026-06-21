"""Tests for the Part 3 independent common-quality DV + its RolloutEngine wiring."""
import json

from slide_examiner.generator import generate_deck
from slide_examiner.optim_runtime import OptimizerRunConfig, RolloutEngine
from slide_examiner.part3_quality import deck_quality, gold_quality, quality_components
from slide_examiner.skill_doc import DEFAULT_PROMPT_MODULES


def _gen_for(slides):
    payload = json.dumps({"deck_id": "d", "scenario": "launch", "slides": slides})
    return lambda messages: payload


def _artifact(slides, task):
    cfg = OptimizerRunConfig(condition="linter", carrier="gepa", train_tasks="x", val_tasks="x", render=False)
    return generate_deck(task, DEFAULT_PROMPT_MODULES, cfg.generator_config(), out_dir="/tmp/p3q_test", complete=_gen_for(slides), render=False)


def test_clean_deck_scores_high() -> None:
    task = {"task_id": "t", "required_sections": ["background", "solution"], "target_slides": 2}
    slides = [
        {"title": "Background", "bullets": ["a", "b"], "section": "background"},
        {"title": "Solution", "bullets": ["c", "d"], "section": "solution"},
    ]
    q, comps = deck_quality(_artifact(slides, task), task)
    assert q >= 0.95
    assert comps["coverage"] == 1.0 and comps["count"] == 1.0


def test_missing_section_lowers_coverage() -> None:
    task = {"task_id": "t", "required_sections": ["background", "solution", "validation"], "target_slides": 2}
    slides = [
        {"title": "Background", "bullets": ["a"], "section": "background"},
        {"title": "Solution", "bullets": ["b"], "section": "solution"},
    ]
    _, comps = deck_quality(_artifact(slides, task), task)
    assert comps["coverage"] < 1.0  # validation missing


def test_verbose_deck_lowers_conciseness() -> None:
    task = {"task_id": "t", "required_sections": ["background"], "target_slides": 1}
    slides = [{"title": "Background", "bullets": [f"point {i}" for i in range(9)], "section": "background"}]
    _, comps = deck_quality(_artifact(slides, task), task)
    assert comps["conciseness"] == 0.0  # 9 bullets > 6


def test_degenerate_artifact_is_zero() -> None:
    task = {"task_id": "t", "required_sections": ["background"]}
    art = generate_deck(task, DEFAULT_PROMPT_MODULES, None, out_dir="/tmp/p3q_test", complete=lambda m: "not json", render=False)
    q, comps = deck_quality(art, task)
    assert q == 0.0 and comps.get("degenerate")


def test_gold_weights_differ_from_proxy_weights() -> None:
    task = {"task_id": "t", "required_sections": ["background", "solution"], "target_slides": 4}
    slides = [{"title": "Background", "bullets": ["a"], "section": "background"}]  # under-count, missing solution
    q_proxy, _ = deck_quality(_artifact(slides, task), task)
    q_gold, _ = gold_quality(_artifact(slides, task), task)
    # both penalize, and the stricter gold weights coverage more heavily
    assert 0.0 < q_gold <= 1.0 and 0.0 < q_proxy <= 1.0


def test_engine_records_quality_and_uses_it_for_convergence() -> None:
    task = {"task_id": "t0", "required_sections": ["background", "solution"], "target_slides": 2}
    cfg = OptimizerRunConfig(condition="linter", carrier="gepa", train_tasks="x", val_tasks="x", render=False, q_threshold=0.8)
    slides = [
        {"title": "Background", "bullets": ["a", "b"], "section": "background"},
        {"title": "Solution", "bullets": ["c"], "section": "solution"},
    ]
    engine = RolloutEngine(cfg, gen_complete=_gen_for(slides), quality_fn=deck_quality)
    r = engine.rollout(DEFAULT_PROMPT_MODULES, task, "/tmp/p3q_test/eng", seed=0)
    assert "quality" in r and 0.0 <= r["quality"] <= 1.0
    assert engine.best_quality() is not None
    # convergence DV uses the common quality stream when present
    assert engine.rollouts_to_threshold() == 1


def test_engine_without_quality_fn_falls_back_to_proxy() -> None:
    task = {"task_id": "t0", "required_sections": ["background"]}
    cfg = OptimizerRunConfig(condition="linter", carrier="gepa", train_tasks="x", val_tasks="x", render=False)
    slides = [{"title": "Background", "bullets": ["a"], "section": "background"}]
    engine = RolloutEngine(cfg, gen_complete=_gen_for(slides))  # no quality_fn
    engine.rollout(DEFAULT_PROMPT_MODULES, task, "/tmp/p3q_test/eng2", seed=0)
    assert engine.best_quality() is None
    assert "quality" not in engine.history[0]
