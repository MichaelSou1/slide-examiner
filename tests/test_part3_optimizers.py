import json

import pytest

from slide_examiner.optim_runtime import OptimizerRunConfig, RolloutEngine
from slide_examiner.skill_doc import DEFAULT_PROMPT_MODULES, MODULE_FIELDS, render_skill_doc


def _write_tasks(path, n=2):
    tasks = [{"task_id": f"t{i}", "brief": f"make deck {i}", "required_sections": ["background", "solution"]} for i in range(n)]
    path.write_text("".join(json.dumps(t) + "\n" for t in tasks), encoding="utf-8")
    return str(path)


def _fake_gen(messages):
    return json.dumps(
        {
            "deck_id": "d",
            "scenario": "launch",
            "slides": [
                {"title": "Background", "bullets": ["short", "concise"], "section": "background"},
                {"title": "Solution", "bullets": ["x", "y"], "section": "solution"},
            ],
        }
    )


def _cfg(tmp_path, condition="linter", carrier="gepa"):
    train = _write_tasks(tmp_path / "train.jsonl")
    val = _write_tasks(tmp_path / "val.jsonl")
    return OptimizerRunConfig(
        condition=condition,
        carrier=carrier,
        train_tasks=train,
        val_tasks=val,
        out_root=str(tmp_path / "out"),
        rollout_budget=6,
        seed=0,
        render=False,
    )


def test_control_signature_isolates_feedback_source(tmp_path) -> None:
    a = _cfg(tmp_path, condition="linter", carrier="skillopt")
    b = _cfg(tmp_path, condition="finetuned_8b", carrier="gepa")
    # only the IV (condition) and carrier differ -> the controls are identical
    assert a.control_signature() == b.control_signature()


def test_skillopt_adapter_rollout_offline(tmp_path) -> None:
    from slide_examiner.skillopt_adapter import build_env_adapter

    cfg = _cfg(tmp_path, condition="linter", carrier="skillopt")
    engine = RolloutEngine(cfg, gen_complete=_fake_gen)
    tasks = {"train": [{"task_id": "t0", "brief": "b"}, {"task_id": "t1", "brief": "b"}], "val": [], "test": []}
    adapter = build_env_adapter(engine, tasks, out_root=tmp_path / "ao")
    env = adapter.build_train_env(batch_size=2, seed=0)
    results = adapter.rollout(env, render_skill_doc(DEFAULT_PROMPT_MODULES), str(tmp_path / "ro"))
    assert len(results) == 2
    for r in results:
        assert set(("id", "hard", "soft", "fail_reason")).issubset(r)
        assert 0.0 <= r["soft"] <= 1.0
        assert r["hard"] in (0, 1)
    assert adapter.get_task_types() == ["slide_generation"]


def test_gepa_real_run_offline_optimizes(tmp_path) -> None:
    """Real (non-dry-run) gepa.optimize: the reflective proposer must run and the
    skill must actually improve (default skill -> overflow 0.1; marker -> 1.0)."""
    pytest.importorskip("gepa")
    from slide_examiner.gepa_runner import run_gepa
    from slide_examiner.part3_experiment import smoke_gen_complete, smoke_reflection_lm

    cfg = _cfg(tmp_path, condition="linter", carrier="gepa")
    out = run_gepa(
        cfg,
        gen_complete=smoke_gen_complete,
        reflection_lm=smoke_reflection_lm,
        max_metric_calls=20,
    )
    assert out["carrier"] == "gepa"
    assert set(out["best_candidate"]) == set(MODULE_FIELDS)
    assert out["n_rollouts"] > 0
    # the reflective mutation actually improved the skill above the overflow baseline
    assert out["best_score"] >= 0.9
    assert out["rollouts_to_threshold"] is not None
