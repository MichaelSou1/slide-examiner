from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .gepa_eval import evaluate_hybrid_feedback


@dataclass(frozen=True)
class GEPARunConfig:
    train_tasks: str
    val_tasks: str
    test_tasks: str
    rollout_budget: int = 200
    seeds: tuple[int, ...] = (0, 1, 2)
    feedback_condition: str = "hybrid"


FEEDBACK_CONDITIONS: dict[str, dict[str, str]] = {
    "linter": {
        "selection_signal": "geometry_linter",
        "reflection_signal": "none",
        "description": "Pure symbolic geometry signal.",
    },
    "zero_shot_8b": {
        "selection_signal": "qwen3_vl_8b_zero_shot",
        "reflection_signal": "qwen3_vl_8b_zero_shot_json",
        "description": "Zero-shot 8B examiner signal.",
    },
    "zero_shot_strong": {
        "selection_signal": "qwen3_vl_strong_or_api",
        "reflection_signal": "qwen3_vl_strong_or_api_json",
        "description": "Strong zero-shot model or API examiner signal.",
    },
    "finetuned_8b": {
        "selection_signal": "finetuned_qwen3_vl_8b",
        "reflection_signal": "finetuned_qwen3_vl_8b_json",
        "description": "Synthetic-defect-trained 8B examiner.",
    },
    "hybrid": {
        "selection_signal": "geometry_linter",
        "reflection_signal": "finetuned_qwen3_vl_8b_json",
        "description": "Linter drives Pareto/selection; finetuned VLM supplies ASI.",
    },
}


def build_gepa_condition_plan(base_config: GEPARunConfig) -> list[dict[str, Any]]:
    plans = []
    for condition, metadata in FEEDBACK_CONDITIONS.items():
        config = GEPARunConfig(
            train_tasks=base_config.train_tasks,
            val_tasks=base_config.val_tasks,
            test_tasks=base_config.test_tasks,
            rollout_budget=base_config.rollout_budget,
            seeds=base_config.seeds,
            feedback_condition=condition,
        )
        plans.append(
            {
                "condition": condition,
                "metadata": metadata,
                "dry_run": run_gepa_experiment(config, dry_run=True),
            }
        )
    return plans


def run_gepa_experiment(
    config: GEPARunConfig,
    *,
    generator: Callable[[dict[str, Any]], Any] | None = None,
    linter_fn: Callable[[Any], float] | None = None,
    examiner_fn: Callable[[Any], dict[str, Any]] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "config": config.__dict__, "planned_rollouts": config.rollout_budget * len(config.seeds)}
    try:
        import gepa
    except ImportError as exc:
        raise RuntimeError("Install GEPA to run non-dry-run prompt optimization.") from exc
    if generator is None or linter_fn is None or examiner_fn is None:
        raise ValueError("generator, linter_fn, and examiner_fn are required for a real GEPA run")

    def metric(candidate, task):
        artifact = generator(task)
        evaluation = evaluate_hybrid_feedback(
            linter_score=linter_fn(artifact),
            examiner_output=examiner_fn(artifact),
        )
        return {"score": evaluation.score, "feedback": evaluation.feedback}

    return gepa.optimize_anything(metric=metric, rollout_budget=config.rollout_budget)


def write_gepa_plan(config: GEPARunConfig, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(run_gepa_experiment(config, dry_run=True), indent=2), encoding="utf-8")
    return output


def write_gepa_condition_plan(config: GEPARunConfig, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"conditions": build_gepa_condition_plan(config)}, indent=2), encoding="utf-8")
    return output
