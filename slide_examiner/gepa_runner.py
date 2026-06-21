"""GEPA carrier (secondary) for Part 3.

Keeps the original dry-run condition planner (used by the CLI + tests) and adds a
REAL ``gepa.api.optimize`` path wired to the shared :class:`RolloutEngine`, so
GEPA and SkillOpt consume the identical generator/feedback pipeline with the
``FeedbackSource`` as the only variable. The frozen reflection LM is the local
Qwen3.6-27B endpoint, identical across all conditions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .gepa_eval import evaluate_hybrid_feedback  # noqa: F401  (kept for back-compat importers)
from .optim_runtime import Completion, OptimizerRunConfig, RolloutEngine, load_tasks, openai_text_complete
from .skill_doc import DEFAULT_PROMPT_MODULES, MODULE_FIELDS, components_to_modules, modules_to_components


@dataclass(frozen=True)
class GEPARunConfig:
    train_tasks: str
    val_tasks: str
    test_tasks: str
    rollout_budget: int = 200
    seeds: tuple[int, ...] = (0, 1, 2)
    feedback_condition: str = "hybrid"


# Canonical 5 conditions (zero_shot_30b replaces the old zero_shot_strong label).
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
    "zero_shot_30b": {
        "selection_signal": "qwen3_vl_30b_zero_shot",
        "reflection_signal": "qwen3_vl_30b_zero_shot_json",
        "description": "Zero-shot 30B examiner signal (cross-size upper bound).",
    },
    "finetuned_8b": {
        "selection_signal": "finetuned_qwen3_vl_8b",
        "reflection_signal": "finetuned_qwen3_vl_8b_json",
        "description": "Synthetic-defect-trained 8B examiner.",
    },
    "hybrid": {
        "selection_signal": "geometry_linter",
        "reflection_signal": "finetuned_qwen3_vl_8b_json",
        "description": "Linter drives selection gate; finetuned VLM supplies ASI.",
    },
}


# --------------------------------------------------------------------------- #
# dry-run condition planner (CLI + tests; unchanged behavior)
# --------------------------------------------------------------------------- #
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
        plans.append({"condition": condition, "metadata": metadata, "dry_run": run_gepa_experiment(config, dry_run=True)})
    return plans


def run_gepa_experiment(config: GEPARunConfig, *, dry_run: bool = True, **kwargs: Any) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "config": config.__dict__, "planned_rollouts": config.rollout_budget * len(config.seeds)}
    raise RuntimeError("Use run_gepa(OptimizerRunConfig, ...) for real GEPA optimization.")


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


# --------------------------------------------------------------------------- #
# REAL GEPA optimization (gepa.api.optimize)
# --------------------------------------------------------------------------- #
class SlideGenGEPAAdapter:
    """GEPA adapter: candidate = the 4 skill modules (one component each).

    ``evaluate`` runs the shared rollout pipeline (score = selection_score);
    ``make_reflective_dataset`` exposes the feedback source's reflection_text as
    the per-component Feedback the frozen reflection LM reads.
    """

    # GEPA's reflective-mutation proposer reads this attribute; None -> use GEPA's
    # built-in reflection proposer (which calls our frozen reflection_lm).
    propose_new_texts = None

    def __init__(self, engine: RolloutEngine, *, out_root: str | Path) -> None:
        self.engine = engine
        self.out_root = Path(out_root)
        self._step = 0

    def evaluate(self, batch: list[dict[str, Any]], candidate: dict[str, str], capture_traces: bool = False):
        from gepa.core.adapter import EvaluationBatch

        modules = components_to_modules(candidate)
        outputs: list[dict[str, Any]] = []
        scores: list[float] = []
        trajectories: list[dict[str, Any]] | None = [] if capture_traces else None
        self._step += 1
        qualities: list[float | None] = []
        for i, task in enumerate(batch):
            out_dir = self.out_root / f"eval_{self._step:04d}" / f"{i:03d}"
            r = self.engine.rollout(modules, task, out_dir, seed=self.engine.config.seed)
            outputs.append({"task_id": r["id"], "selection_score": r["selection_score"], "degenerate": r["degenerate"]})
            scores.append(float(r["selection_score"]))
            qualities.append(r.get("quality"))
            if trajectories is not None:
                trajectories.append({"task": task, "feedback": r["reflection"], "score": r["selection_score"]})
        # one candidate evaluated over this batch -> record its mean common-quality
        self.engine.record_candidate_eval(qualities)
        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
        dataset: dict[str, list[dict[str, Any]]] = {}
        traces = eval_batch.trajectories or []
        for component in components_to_update:
            examples = []
            for traj in traces:
                examples.append(
                    {
                        "Inputs": str(traj["task"].get("brief", traj["task"].get("task_id", ""))),
                        "Generated Outputs": f"deck selection_score={traj['score']:.3f}",
                        "Feedback": traj["feedback"],
                    }
                )
            dataset[component] = examples[:5]
        return dataset


def gepa_reflection_lm(config: OptimizerRunConfig) -> Callable[[Any], str]:
    """Frozen reflection LM callable (local Qwen3.6-27B); identical across conditions."""
    base = openai_text_complete(
        config.optimizer_model,
        config.optimizer_base_url,
        api_key_env=config.optimizer_api_key_env,   # reflector's OWN service key
        api_style=config.optimizer_api_style,       # ...and its own endpoint style
        max_tokens=config.optimizer_max_tokens,
    )

    def lm(prompt: Any) -> str:
        messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
        return base(messages)

    return lm


def run_gepa(
    config: OptimizerRunConfig,
    *,
    gen_complete: Completion | None = None,
    examiner_complete: Completion | None = None,
    reflection_lm: Callable[[Any], str] | None = None,
    max_metric_calls: int | None = None,
    quality_fn: Callable[[Any, dict[str, Any]], tuple[float, dict[str, Any]]] | None = None,
    seed_modules: Any | None = None,
) -> dict[str, Any]:
    """Run REAL GEPA optimization over the 4 skill modules. Non-dry-run.

    ``quality_fn`` (live runs) supplies the independent common-quality DV;
    ``seed_modules`` overrides the seed skill (default = DEFAULT_PROMPT_MODULES).
    """
    import gepa

    engine = RolloutEngine(config, gen_complete=gen_complete, examiner_complete=examiner_complete, quality_fn=quality_fn)
    out_root = Path(config.out_root) / "gepa" / config.condition / f"seed{config.seed}"
    out_root.mkdir(parents=True, exist_ok=True)
    adapter = SlideGenGEPAAdapter(engine, out_root=out_root)
    trainset = load_tasks(config.train_tasks)
    valset = load_tasks(config.val_tasks) if config.val_tasks else trainset
    reflection = reflection_lm or gepa_reflection_lm(config)
    seed_modules = seed_modules or DEFAULT_PROMPT_MODULES

    result = gepa.optimize(
        seed_candidate=modules_to_components(seed_modules),
        trainset=trainset,
        valset=valset,
        adapter=adapter,
        reflection_lm=reflection,
        max_metric_calls=max_metric_calls or config.rollout_budget,
        seed=config.seed,
        run_dir=str(out_root),
        display_progress_bar=False,
    )
    best = getattr(result, "best_candidate", None) or modules_to_components(seed_modules)
    return {
        "carrier": "gepa",
        "condition": config.condition,
        "seed": config.seed,
        "best_candidate": {k: best.get(k, "") for k in MODULE_FIELDS},
        "n_rollouts": engine.n_rollouts,
        "rollouts_to_threshold": engine.rollouts_to_threshold(),
        "best_score": engine.best_score(),
        "best_quality": engine.best_quality(),
        "best_candidate_quality": engine.best_candidate_quality(),
        "history": engine.history,
        "out_root": str(out_root),
    }
