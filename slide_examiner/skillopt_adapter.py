"""SkillOpt (ReflACT) carrier (primary) for Part 3.

Plugs the shared generator + feedback pipeline into SkillOpt's ``EnvAdapter``:

* ``rollout`` runs ``generate_deck`` + ``FeedbackSource.score`` and returns
  ``{"id","hard","soft","fail_reason"}`` where ``soft`` is the selection_score
  (drives ``gate_metric="soft"``) and ``fail_reason`` is the reflection_text the
  frozen optimizer model reads in ``reflect``.
* ``reflect`` reuses SkillOpt's ``run_minibatch_reflect`` (the optimizer model
  proposes add/insert/replace/delete edits over the skill document).

The optimizer/reflection LLM is the local Qwen3.6-27B endpoint, frozen and
identical across all conditions and both carriers — the only manipulation is the
``FeedbackSource`` (the IV).
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

from .optim_runtime import OptimizerRunConfig, RolloutEngine, load_tasks
from .skill_doc import DEFAULT_PROMPT_MODULES, parse_skill_doc, render_skill_doc, write_skill_doc


def _load_splits(config: OptimizerRunConfig) -> dict[str, list[dict]]:
    splits = {"train": load_tasks(config.train_tasks)}
    splits["val"] = load_tasks(config.val_tasks) if config.val_tasks else list(splits["train"])
    splits["test"] = load_tasks(config.test_tasks) if config.test_tasks else list(splits["val"])
    return splits


def build_dataloader(tasks_by_split: dict[str, list[dict]]):
    """SkillOpt BaseDataLoader yielding our deck-generation tasks as BatchSpecs."""
    from skillopt.datasets.base import BaseDataLoader, BatchSpec

    class SlideTaskDataLoader(BaseDataLoader):
        def __init__(self, tasks: dict[str, list[dict]]) -> None:
            self.tasks = tasks
            self.train_items = list(tasks.get("train", []))
            self.val_items = list(tasks.get("val", []))
            self.test_items = list(tasks.get("test", []))

        def setup(self, cfg: dict) -> None:  # noqa: D401
            self._cfg = cfg

        def get_train_size(self) -> int:
            return len(self.train_items)

        def build_train_batch(self, batch_size: int, seed: int, **kwargs) -> "BatchSpec":
            items = list(self.train_items)
            random.Random(seed).shuffle(items)
            payload = items[:batch_size] if batch_size else items
            return BatchSpec(phase="train", split="train", seed=seed, batch_size=len(payload), payload=payload)

        def build_eval_batch(self, env_num: int, split: str, seed: int, **kwargs) -> "BatchSpec":
            items = list(self.tasks.get(split, self.val_items))
            payload = items[:env_num] if env_num else items
            return BatchSpec(phase="eval", split=split, seed=seed, batch_size=len(payload), payload=payload)

    return SlideTaskDataLoader(tasks_by_split)


# ReflACT/SkillOpt 0.1.0 (PyPI) ships WITHOUT its prompt .md assets (prompts/ has only
# __init__.py; GitHub unreachable). These reconstructed analyst prompts drive SkillOpt's
# *full-rewrite minibatch* mode so the carrier runs: SkillOpt's loop (validation gate +
# edit-economy + minibatch reflection + slow/meta update) is intact; only the analyst
# wording is ours. The carrier is therefore an optimizer-FAMILY robustness check, not a
# verbatim reproduction of the published prompts (stated honestly in the report).
_ANALYST_BASE = (
    "You are a skill optimizer for a slide-deck generator. The SKILL is a markdown "
    "document with exactly four sections: `## scenario_classifier`, "
    "`## page_type_instructions`, `## component_library`, `## quality_checklist`. "
    "It steers a frozen generator that turns a task brief into a deck; only the SKILL "
    "changes. You are given the current skill and a minibatch of recent trajectories "
    "(brief, resulting deck score, and feedback). Diagnose what limits deck quality "
    "(e.g. missing required sections/coverage, verbosity, terminology drift) and write "
    "ONE improved, COMPLETE replacement skill that would raise quality on these and "
    "similar tasks. Keep the four `## <section>` headers; encode reusable, general "
    "conventions (not task-specific text). Output ONLY a JSON object: "
    '{"reasoning": "<brief diagnosis>", "patch": "<full new skill markdown with the '
    'four ## sections>"}.'
)
_ANALYST_ERROR = _ANALYST_BASE + " Focus on fixing the failures shown in the minibatch."
_ANALYST_SUCCESS = _ANALYST_BASE + " Reinforce what worked and make incremental improvements."


def build_env_adapter(engine: RolloutEngine, tasks_by_split: dict[str, list[dict]], *, out_root: str | Path):
    """Construct the SkillOpt EnvAdapter bound to our rollout engine."""
    from skillopt.envs.base import EnvAdapter

    dataloader = build_dataloader(tasks_by_split)

    class SlideGenEnvAdapter(EnvAdapter):
        def __init__(self) -> None:
            self.engine = engine
            self.dataloader = dataloader
            self.out_root = str(out_root)
            self.minibatch_size = 4
            self.edit_budget = 4
            self.analyst_workers = 2
            self.failure_only = False
            self._cfg: dict[str, Any] = {}

        def setup(self, cfg: dict) -> None:
            super().setup(cfg)
            self._cfg = cfg
            self.dataloader.setup(cfg)
            self.edit_budget = int(cfg.get("edit_budget", self.edit_budget))

        def get_dataloader(self):
            return self.dataloader

        def build_env_from_batch(self, batch, **kwargs):
            return list(batch.payload or [])

        def build_train_env(self, batch_size: int, seed: int, **kwargs):
            return self.build_env_from_batch(self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs))

        def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs):
            return self.build_env_from_batch(self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs))

        def rollout(self, env_manager, skill_content: str, out_dir: str, **kwargs) -> list[dict]:
            modules = parse_skill_doc(skill_content)
            results = []
            qualities = []
            for i, task in enumerate(list(env_manager)):
                tid = str(task.get("task_id") or task.get("id") or i)
                r = self.engine.rollout(modules, task, os.path.join(out_dir, tid), seed=kwargs.get("seed", self.engine.config.seed))
                qualities.append(r.get("quality"))
                r.pop("details", None)  # keep results compact/JSON-friendly for SkillOpt
                results.append(r)
            # one candidate (skill) evaluated over this batch -> record mean common-quality
            self.engine.record_candidate_eval(qualities)
            return results

        def reflect(self, results: list[dict], skill_content: str, out_dir: str, **kwargs) -> list[dict | None]:
            from skillopt.gradient.reflect import run_minibatch_reflect

            return run_minibatch_reflect(
                results=results,
                skill_content=skill_content,
                prediction_dir=kwargs.get("prediction_dir", os.path.join(out_dir, "predictions")),
                patches_dir=kwargs.get("patches_dir", os.path.join(out_dir, "patches")),
                workers=self.analyst_workers,
                failure_only=self.failure_only,
                minibatch_size=self.minibatch_size,
                edit_budget=self.edit_budget,
                random_seed=kwargs.get("random_seed"),
                error_system=self.get_error_minibatch_prompt(),
                success_system=self.get_success_minibatch_prompt(),
                step_buffer_context=kwargs.get("step_buffer_context", ""),
                update_mode=self._cfg.get("skill_update_mode", "patch"),
            )

        def get_task_types(self) -> list[str]:
            return ["slide_generation"]

        # supply reconstructed analyst prompts (package ships none) so reflect()
        # uses them instead of trying to load the missing skillopt/prompts/*.md
        def get_error_minibatch_prompt(self) -> str:
            return _ANALYST_ERROR

        def get_success_minibatch_prompt(self) -> str:
            return _ANALYST_SUCCESS

    return SlideGenEnvAdapter()


def build_skillopt_cfg(config: OptimizerRunConfig, *, skill_init: str, out_root: str) -> dict[str, Any]:
    """Flat ReflACT cfg. optimizer (reflector) -> its own endpoint; target (the model
    the skill steers) -> the generator. NB: our EnvAdapter.rollout overrides generation
    with our own engine, so SkillOpt's target backend is registered but not actually
    used to generate — it just has to be a valid, present config."""
    opt_key = os.environ.get(config.optimizer_api_key_env) or os.environ.get("OPENAI_API_KEY", "EMPTY")
    gen_key = os.environ.get(config.gen_api_key_env) or os.environ.get("OPENAI_API_KEY", "EMPTY")
    return {
        # backends: optimizer/model -> reflector endpoint; target -> generator endpoint
        "model_backend": "qwen_chat",
        "optimizer_backend": "qwen_chat",
        "target_backend": "qwen_chat",
        "optimizer_model": config.optimizer_model,
        "target_model": config.gen_model,  # skill's target = the (frozen) generator
        "qwen_chat_base_url": config.optimizer_base_url,
        "qwen_chat_api_key": opt_key,
        "qwen_chat_model": config.optimizer_model,
        "qwen_chat_max_tokens": config.optimizer_max_tokens,
        "optimizer_qwen_chat_base_url": config.optimizer_base_url,
        "optimizer_qwen_chat_api_key": opt_key,
        "optimizer_qwen_chat_max_tokens": config.optimizer_max_tokens,
        "target_qwen_chat_base_url": config.gen_base_url,
        "target_qwen_chat_api_key": gen_key,
        # reasoning models (e.g. mimo) must not burn the token budget on thinking
        "qwen_chat_enable_thinking": False,
        "optimizer_qwen_chat_enable_thinking": False,
        "target_qwen_chat_enable_thinking": False,
        # training loop (small — SkillOpt edit-economy keeps real rollouts low)
        "num_epochs": 1,
        "steps_per_epoch": max(1, config.rollout_budget // 8),
        "batches_per_epoch": max(1, config.rollout_budget // 8),
        "samples_per_epoch": max(1, config.rollout_budget // 8),
        "merge_batch_size": 4,
        "lr_control_mode": "fixed",
        "batch_size": 4,
        "accumulation": 1,
        "train_size": 0,
        # optimizer (edit budget = "learning rate")
        "edit_budget": 4,
        "min_edit_budget": 1,
        "analyst_workers": 2,
        # full-rewrite minibatch: analyst returns one complete replacement skill (simple,
        # faithful to drive with reconstructed prompts; parse_skill_doc reads it back).
        "skill_update_mode": "full_rewrite_minibatch",
        # gate: selection driven by our selection_score (soft)
        "use_gate": True,
        "gate_metric": "soft",
        "gate_mixed_weight": 0.5,
        # eval sets
        "sel_env_num": 0,  # 0 -> use full val split
        "test_env_num": 0,
        "eval_test": False,
        # env / io
        "env": "slide_generation",
        "skill_init": skill_init,
        "out_root": out_root,
        "seed": config.seed,
    }


def run_skillopt(
    config: OptimizerRunConfig,
    *,
    gen_complete=None,
    examiner_complete=None,
    quality_fn=None,
    seed_modules=None,
) -> dict[str, Any]:
    """Run REAL SkillOpt (ReflACT) optimization. Needs the local vLLM endpoint up.

    ``quality_fn`` supplies the independent common-quality DV; ``seed_modules``
    overrides the seed skill (default = DEFAULT_PROMPT_MODULES).
    """
    import skillopt.model as som
    from skillopt.engine.trainer import ReflACTTrainer

    out_root = Path(config.out_root) / "skillopt" / config.condition / f"seed{config.seed}"
    out_root.mkdir(parents=True, exist_ok=True)
    skill_init = out_root / "skill_init.md"
    write_skill_doc(seed_modules or DEFAULT_PROMPT_MODULES, skill_init)

    # ACTIVATE the qwen_chat backend (else chat_optimizer routes to the default
    # openai backend and makes 0 calls — the reflection silently no-ops).
    for _setter in ("set_optimizer_backend", "set_target_backend", "set_model_backend"):
        if hasattr(som, _setter):
            try:
                getattr(som, _setter)("qwen_chat")
            except Exception:  # noqa: BLE001
                pass
    # point the frozen optimizer/target LLM at the local vLLM endpoint
    if hasattr(som, "configure_qwen_chat"):
        som.configure_qwen_chat(
            base_url=config.optimizer_base_url,
            api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
            optimizer_base_url=config.optimizer_base_url,
            optimizer_api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
            target_base_url=config.optimizer_base_url,
            target_api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
        )

    tasks = _load_splits(config)
    engine = RolloutEngine(config, gen_complete=gen_complete, examiner_complete=examiner_complete, quality_fn=quality_fn)
    adapter = build_env_adapter(engine, tasks, out_root=out_root)
    cfg = build_skillopt_cfg(config, skill_init=str(skill_init), out_root=str(out_root))

    trainer = ReflACTTrainer(cfg, adapter)
    summary = trainer.train()

    best_path = out_root / "best_skill.md"
    best_modules = None
    if best_path.exists():
        best_modules = parse_skill_doc(best_path.read_text(encoding="utf-8"))
    return {
        "carrier": "skillopt",
        "condition": config.condition,
        "seed": config.seed,
        "n_rollouts": engine.n_rollouts,
        "rollouts_to_threshold": engine.rollouts_to_threshold(),
        "best_score": engine.best_score(),
        "best_quality": engine.best_quality(),
        "best_candidate_quality": engine.best_candidate_quality(),
        "history": engine.history,
        "out_root": str(out_root),
        "best_skill": best_modules.to_dict() if best_modules else None,
        "trainer_summary": summary if isinstance(summary, dict) else None,
    }
