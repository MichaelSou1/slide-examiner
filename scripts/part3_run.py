"""P6 — Part 3 optimizer matrix driver (deck-level by default).

Runs {5 feedback conditions} x {carriers} x {seeds} through the shared
generator+feedback pipeline (feedback source = the only IV), recording
convergence (rollouts-to-threshold) + best skill per cell.

  --smoke : offline (fake LLMs, GEPA carrier only) — validates the full pipeline.
  live    : serve Qwen3.6-27B (generator+reflection) + examiner VLM, then run.

Outputs: <out>/main.jsonl + <best-dir>/<condition>__<carrier>__seed<k>.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.api_config import load_dotenv, resolve_role
from slide_examiner.feedback_sources import FEEDBACK_SOURCE_ORDER
from slide_examiner.optim_runtime import OptimizerRunConfig
from slide_examiner.part3_experiment import run_matrix

load_dotenv(REPO / ".env")
_ENV_BASE = os.environ.get("OPENAI_BASE_URL")  # online API base (blank -> local vLLM defaults)
# Three independent API services (generator / reflector / judge). Each reads its own
# PART3_<ROLE>_{MODEL,BASE_URL,API_KEY,API_STYLE}; optimizer co-locates with the
# generator only when its own vars are unset. Judge is resolved in part3_final_eval.py.
_GEN = resolve_role("GEN", default_model="qwen3.6-27b")
_OPT = resolve_role("OPTIMIZER", fallback="GEN", default_model=_GEN["model"])
_EXAM = resolve_role("EXAMINER", default_model=_GEN["model"])  # API-path examiner (faithful = local)
_LOCAL = "http://127.0.0.1:8200/v1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-dir", default=str(REPO / "data/part3/tasks"))
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/main.jsonl"))
    ap.add_argument("--best-dir", default=str(REPO / "runs/part3/best_skill"))
    ap.add_argument("--out-root", default=str(REPO / "runs/part3/runs"))
    ap.add_argument("--carriers", nargs="+", default=["gepa", "skillopt"])
    ap.add_argument("--conditions", nargs="+", default=list(FEEDBACK_SOURCE_ORDER))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--budget", type=int, default=200)
    ap.add_argument("--level", default="deck", choices=["deck", "page"])
    ap.add_argument("--q", type=float, default=0.8)
    ap.add_argument("--max-slides", type=int, default=None, help="override (page level defaults to 2)")
    ap.add_argument("--gen-max-tokens", type=int, default=None, help="cap generator output tokens (page defaults to 700)")
    ap.add_argument("--smoke", action="store_true", help="offline fake LLMs (GEPA only)")
    ap.add_argument("--weak-seed", action="store_true", help="start optimization from the near-empty WEAK seed skill (the fair H3 seed)")
    ap.add_argument("--no-render", action="store_true", help="skip rendering (structure-only feedback)")
    ap.add_argument("--api-style", default=os.environ.get("PART3_API_STYLE", "chat"), choices=["chat", "responses"])
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    # GENERATOR (做PPT;冻结) — its own API service (PART3_GEN_*)
    ap.add_argument("--gen-model", default=_GEN["model"])
    ap.add_argument("--gen-base-url", default=_GEN["base_url"] or _LOCAL)
    ap.add_argument("--gen-api-key-env", default=_GEN["api_key_env"])
    ap.add_argument("--gen-api-style", default=_GEN["api_style"])
    # OPTIMIZER / REFLECTION LLM (改skill;冻结) — its own API service (PART3_OPTIMIZER_*),
    # fully decoupled (co-locates with the generator only if PART3_OPTIMIZER_* is unset).
    ap.add_argument("--optimizer-model", default=_OPT["model"])
    ap.add_argument("--optimizer-base-url", default=_OPT["base_url"] or _LOCAL)
    ap.add_argument("--optimizer-api-key-env", default=_OPT["api_key_env"])
    ap.add_argument("--optimizer-api-style", default=_OPT["api_style"])
    # examiner is resolved PER CONDITION: zero_shot_* use the API examiner (its OWN
    # service, PART3_EXAMINER_*); finetuned_8b/hybrid use the LOCAL trained ft-8B; linter uses no model.
    ap.add_argument("--api-examiner-model", default=_EXAM["model"])
    ap.add_argument("--api-examiner-base-url", default=_EXAM["base_url"] or "http://127.0.0.1:8101/v1")
    ap.add_argument("--api-examiner-api-key-env", default=_EXAM["api_key_env"])
    ap.add_argument("--api-examiner-api-style", default=_EXAM["api_style"])
    ap.add_argument("--ft-examiner-model", default="ft-8b")
    ap.add_argument("--ft-examiner-base-url", default="http://127.0.0.1:8101/v1")
    # image-based zero-shot examiner via an online VLM API (implies rendering ON)
    ap.add_argument("--examiner-vlm", action="store_true", help="route zero-shot examiner to PART3_VLM_* (image modality; forces render)")
    ap.add_argument("--vlm-model", default=os.environ.get("PART3_VLM_MODEL"))
    ap.add_argument("--vlm-base-url", default=os.environ.get("PART3_VLM_BASE_URL") or _ENV_BASE)
    ap.add_argument("--vlm-api-key-env", default="PART3_VLM_API_KEY")
    ap.add_argument("--vlm-api-style", default=os.environ.get("PART3_VLM_API_STYLE", "chat"))
    args = ap.parse_args()

    tasks = Path(args.tasks_dir)
    train, val, test = tasks / "train.jsonl", tasks / "val.jsonl", tasks / "test.jsonl"
    max_slides = args.max_slides if args.max_slides is not None else (2 if args.level == "page" else 15)
    gen_max_tokens = args.gen_max_tokens if args.gen_max_tokens is not None else (700 if args.level == "page" else 2048)
    if args.examiner_vlm and not args.vlm_model:
        raise SystemExit("--examiner-vlm requires PART3_VLM_MODEL (.env) or --vlm-model")
    # image examiner needs rendered images, so --examiner-vlm forces rendering ON
    render = (not args.smoke) and (args.examiner_vlm or not args.no_render)

    # zero-shot examiner endpoints map onto the model name; here a single examiner
    # endpoint is assumed per run (serve the relevant VLM and pass its name).
    def examiner_for(condition: str) -> tuple[str | None, str | None, str, str]:
        # returns (model, base_url, api_key_env, api_style)
        if condition in ("zero_shot_8b", "zero_shot_30b"):
            if args.examiner_vlm:
                return args.vlm_model, args.vlm_base_url, args.vlm_api_key_env, args.vlm_api_style
            return args.api_examiner_model, args.api_examiner_base_url, args.api_examiner_api_key_env, args.api_examiner_api_style
        if condition in ("finetuned_8b", "hybrid"):
            return args.ft_examiner_model, args.ft_examiner_base_url, args.api_key_env, args.api_style
        return None, None, args.api_key_env, args.api_style  # linter

    def make_config(condition: str, carrier: str, seed: int) -> OptimizerRunConfig:
        ex_model, ex_base, ex_key_env, ex_style = examiner_for(condition)
        return OptimizerRunConfig(
            condition=condition,
            carrier=carrier,
            train_tasks=str(train),
            val_tasks=str(val),
            test_tasks=str(test),
            out_root=args.out_root,
            rollout_budget=args.budget,
            seed=seed,
            q_threshold=args.q,
            level=args.level,
            max_slides=max_slides,
            gen_max_tokens=gen_max_tokens,
            render=render,
            gen_model=args.gen_model,
            gen_base_url=args.gen_base_url,
            gen_api_key_env=args.gen_api_key_env,
            gen_api_style=args.gen_api_style,
            optimizer_model=args.optimizer_model,
            optimizer_base_url=args.optimizer_base_url,
            optimizer_api_key_env=args.optimizer_api_key_env,
            optimizer_api_style=args.optimizer_api_style,
            examiner_model=ex_model,
            examiner_base_url=ex_base,
            examiner_api_key_env=ex_key_env,
            examiner_api_style=ex_style,
            api_style=args.api_style,
            api_key_env=args.api_key_env,
        )

    def progress(rec: dict) -> None:
        status = "ok" if rec.get("ok") else f"FAIL({rec.get('error','')[:60]})"
        print(f"  [{rec['carrier']}/{rec['condition']}/seed{rec['seed']}] "
              f"rollouts={rec.get('n_rollouts')} to_thr={rec.get('rollouts_to_threshold')} "
              f"best={rec.get('best_score')} gold={rec.get('best_quality')} {status}", flush=True)

    seed_modules = None
    if args.weak_seed:
        from slide_examiner.skill_doc import WEAK_PROMPT_MODULES
        seed_modules = WEAK_PROMPT_MODULES

    print(f"[part3_run] level={args.level} smoke={args.smoke} weak_seed={args.weak_seed} carriers={args.carriers} "
          f"conditions={args.conditions} seeds={args.seeds} budget={args.budget}", flush=True)
    records = run_matrix(
        conditions=args.conditions,
        carriers=args.carriers,
        seeds=args.seeds,
        make_config=make_config,
        smoke=args.smoke,
        out_jsonl=args.out,
        best_skill_dir=args.best_dir,
        on_record=progress,
        seed_modules=seed_modules,
    )
    n_ok = sum(1 for r in records if r.get("ok"))
    print(f"[part3_run] {n_ok}/{len(records)} cells ok -> {args.out}")


if __name__ == "__main__":
    main()
