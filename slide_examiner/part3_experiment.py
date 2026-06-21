"""Part 3 experiment driver — runs the optimizer matrix and records convergence.

For each (condition, carrier, seed) it runs the optimizer (GEPA or SkillOpt) over
the shared generator+feedback pipeline (feedback source = the IV) and records the
convergence-efficiency metric (rollouts-to-threshold) + best skill.

``smoke=True`` uses fake LLMs (no server): a fake generator whose output
cleanliness responds to skill quality, the real offline linter, and a fake
reflection LM — so the whole P5–P9 pipeline produces real artifacts offline.
``smoke=False`` uses the live local vLLM endpoints. SkillOpt requires a live
reflection endpoint, so smoke mode runs the GEPA carrier only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .feedback_sources import DEFAULT_INTRINSIC_QUALITY
from .gepa_runner import run_gepa
from .optim_runtime import OptimizerRunConfig


# --------------------------------------------------------------------------- #
# smoke fakes (offline; output quality responds to skill quality)
# --------------------------------------------------------------------------- #
_LONG = (
    "This bullet is intentionally far too long to fit inside its container and will overflow the text box "
    "badly because it keeps going well past any reasonable width with redundant filler clauses that no concise "
    "slide would ever contain, repeating the point again and again until the line clearly exceeds the box."
)


def smoke_gen_complete(messages: list[dict[str, Any]]) -> str:
    """Fake generator: a 'good' skill (concise/<=4) yields a clean deck; the
    default skill yields overflowing bullets the linter catches."""
    text = " ".join(str(m.get("content", "")) for m in messages).lower()
    good = ("concise" in text and "<= 4" in text) or "keep each slide to <= 4" in text
    if good:
        slides = [
            {"title": "Background", "bullets": ["short point", "second point", "third"], "section": "background"},
            {"title": "Solution", "bullets": ["clear value", "easy rollout"], "section": "solution"},
        ]
    else:
        slides = [
            {"title": "Background", "bullets": [_LONG, _LONG, _LONG, _LONG, _LONG, _LONG], "section": "background"},
            {"title": "Solution", "bullets": [_LONG, _LONG, _LONG, _LONG, _LONG, _LONG], "section": "solution"},
        ]
    return json.dumps({"deck_id": "smoke", "scenario": "launch", "slides": slides})


def smoke_examiner_complete(messages: list[dict[str, Any]]) -> str:
    return json.dumps({"page_id": "p", "has_defect": False, "findings": []})


def smoke_reflection_lm(prompt: Any) -> str:
    # nudges the skill toward the 'good' marker the smoke generator rewards
    return "Keep each slide to <= 4 concise bullets and one short title."


# --------------------------------------------------------------------------- #
# run one cell
# --------------------------------------------------------------------------- #
def run_one(config: OptimizerRunConfig, *, smoke: bool = False, seed_modules: Any | None = None) -> dict[str, Any]:
    iq = DEFAULT_INTRINSIC_QUALITY.get(config.condition, {})
    record: dict[str, Any] = {
        "condition": config.condition,
        "carrier": config.carrier,
        "seed": config.seed,
        "level": config.level,
        "intrinsic_quality": iq,
        "smoke": smoke,
    }
    # Live runs measure convergence against the independent common-quality gold
    # (the fair cross-condition DV); smoke keeps the proxy-based DV the offline
    # tests are calibrated on.
    quality_fn = None if smoke else _live_quality_fn()
    try:
        if config.carrier == "gepa":
            out = run_gepa(
                config,
                gen_complete=smoke_gen_complete if smoke else None,
                examiner_complete=(smoke_examiner_complete if (smoke and config.condition != "linter") else None),
                reflection_lm=smoke_reflection_lm if smoke else None,
                max_metric_calls=config.rollout_budget,
                quality_fn=quality_fn,
                seed_modules=seed_modules,
            )
        elif config.carrier == "skillopt":
            if smoke:
                raise RuntimeError("skillopt requires a live reflection endpoint; not available in smoke mode")
            from .skillopt_adapter import run_skillopt

            out = run_skillopt(config, quality_fn=quality_fn, seed_modules=seed_modules)
        else:
            raise ValueError(f"unknown carrier {config.carrier!r}")
        record.update(
            {
                "ok": True,
                "n_rollouts": out.get("n_rollouts"),
                "rollouts_to_threshold": out.get("rollouts_to_threshold"),
                "best_score": out.get("best_score"),
                "best_quality": out.get("best_quality"),
                "best_candidate_quality": out.get("best_candidate_quality"),
                "best_skill": out.get("best_skill") or out.get("best_candidate"),
                "history": out.get("history", []),
                "out_root": out.get("out_root"),
            }
        )
    except Exception as exc:  # record failures, never crash the matrix
        record.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return record


def _live_quality_fn():
    """The independent, model-free common-quality DV (imported lazily to avoid
    pulling render deps into offline smoke paths)."""
    from .part3_quality import deck_quality

    return deck_quality


def config_factory(
    condition: str,
    carrier: str,
    seed: int,
    *,
    train_tasks: str,
    val_tasks: str,
    test_tasks: str,
    out_root: str,
    rollout_budget: int,
    level: str,
    render: bool,
    q_threshold: float,
    examiner_model: str | None,
    examiner_base_url: str | None,
    gen_base_url: str | None,
    optimizer_base_url: str | None,
) -> OptimizerRunConfig:
    return OptimizerRunConfig(
        condition=condition,
        carrier=carrier,
        train_tasks=train_tasks,
        val_tasks=val_tasks,
        test_tasks=test_tasks,
        out_root=out_root,
        rollout_budget=rollout_budget,
        seed=seed,
        q_threshold=q_threshold,
        level=level,
        render=render,
        examiner_model=examiner_model,
        examiner_base_url=examiner_base_url,
        gen_base_url=gen_base_url,
        optimizer_base_url=optimizer_base_url,
    )


def run_matrix(
    *,
    conditions: list[str],
    carriers: list[str],
    seeds: list[int],
    make_config: Callable[[str, str, int], OptimizerRunConfig],
    smoke: bool,
    out_jsonl: str | Path,
    best_skill_dir: str | Path,
    on_record: Callable[[dict], None] | None = None,
    seed_modules: Any | None = None,
) -> list[dict[str, Any]]:
    from .skill_doc import PromptModules, write_skill_doc

    out_jsonl = Path(out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    best_dir = Path(best_skill_dir)
    best_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for carrier in carriers:
            for condition in conditions:
                for seed in seeds:
                    cfg = make_config(condition, carrier, seed)
                    rec = run_one(cfg, smoke=smoke, seed_modules=seed_modules)
                    if rec.get("best_skill"):
                        write_skill_doc(
                            PromptModules.from_dict(rec["best_skill"]),
                            best_dir / f"{condition}__{carrier}__seed{seed}.md",
                        )
                    # keep history out of the per-line summary to bound size
                    line = {k: v for k, v in rec.items() if k != "history"}
                    handle.write(json.dumps(line, ensure_ascii=False) + "\n")
                    records.append(rec)
                    if on_record:
                        on_record(rec)
    return records
