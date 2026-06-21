"""P10 — self-refine downstream vehicle (Part 3 downgraded PRIMARY evidence).

For each examiner-quality level (the IV), run generate→critique→revise on each task
and measure the deck's independent common-quality over iterations. No GEPA/SkillOpt.

Examiner routing mirrors part3_run.py: linter = offline; zero_shot_* = API/served
examiner; finetuned_8b/hybrid = local ft-8B. Generator = PART3_GEN_* (resolve_role).

Outputs: runs/probe/part3/self_refine.jsonl + runs/probe/part3/self_refine_summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.api_config import build_completion, load_dotenv, resolve_role
from slide_examiner.feedback_sources import DEFAULT_INTRINSIC_QUALITY, FEEDBACK_SOURCE_ORDER, build_feedback_source
from slide_examiner.generator import GeneratorConfig
from slide_examiner.io import read_jsonl
from slide_examiner.self_refine import refinement_summary, run_self_refine
from slide_examiner.skill_doc import DEFAULT_PROMPT_MODULES, WEAK_PROMPT_MODULES

load_dotenv(REPO / ".env")
_GEN = resolve_role("GEN", default_model="qwen3.6-flash")
_EXAM = resolve_role("EXAMINER", default_model=_GEN["model"])


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(num / (dx * dy), 3) if dx > 0 and dy > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(REPO / "data/part3/tasks/test.jsonl"))
    ap.add_argument("--conditions", nargs="+", default=list(FEEDBACK_SOURCE_ORDER))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n-iters", type=int, default=4)
    ap.add_argument("--q", type=float, default=0.85, help="quality threshold for iters-to-threshold")
    ap.add_argument("--max-tasks", type=int, default=6)
    ap.add_argument("--max-slides", type=int, default=15)
    ap.add_argument("--gen-max-tokens", type=int, default=2048)
    ap.add_argument("--weak-seed", action="store_true", help="start from WEAK seed skill (fair, matches GEPA)")
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/self_refine.jsonl"))
    ap.add_argument("--summary", default=str(REPO / "runs/probe/part3/self_refine_summary.json"))
    ap.add_argument("--from-jsonl", default=None, help="aggregate an existing merged jsonl (skip running; for multi-phase merge)")
    # examiner endpoints (faithful = served local models; mirror part3_run)
    ap.add_argument("--api-examiner-model", default=_EXAM["model"])
    ap.add_argument("--api-examiner-base-url", default=_EXAM["base_url"] or "http://127.0.0.1:8101/v1")
    ap.add_argument("--api-examiner-api-key-env", default=_EXAM["api_key_env"])
    ap.add_argument("--ft-examiner-model", default="ft-8b")
    ap.add_argument("--ft-examiner-base-url", default="http://127.0.0.1:8101/v1")
    args = ap.parse_args()

    tasks = read_jsonl(args.tasks)[: args.max_tasks]
    seed_modules = WEAK_PROMPT_MODULES if args.weak_seed else DEFAULT_PROMPT_MODULES
    gen_cfg = GeneratorConfig(
        model=_GEN["model"], base_url=_GEN["base_url"], api_key_env=_GEN["api_key_env"],
        api_style=_GEN["api_style"], max_tokens=args.gen_max_tokens, max_slides=args.max_slides,
    )

    def examiner_complete_for(condition: str):
        if condition == "linter":
            return None
        if condition in ("zero_shot_8b", "zero_shot_30b"):
            m, b, k = args.api_examiner_model, args.api_examiner_base_url, args.api_examiner_api_key_env
        else:  # finetuned_8b / hybrid
            m, b, k = args.ft_examiner_model, args.ft_examiner_base_url, "OPENAI_API_KEY"
        return build_completion(m, b, api_key_env=k, api_style="chat", max_tokens=768)

    records: list[dict] = []
    if args.from_jsonl:
        records = read_jsonl(args.from_jsonl)
        print(f"[self_refine] aggregating {len(records)} records from {args.from_jsonl} (no run)")
        _aggregate_and_write(records, args)
        return

    out_jsonl = Path(args.out)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for cond in args.conditions:
            ex = examiner_complete_for(cond)
            feedback = build_feedback_source(cond, examiner_complete=ex)
            for seed in args.seeds:
                for ti, task in enumerate(tasks):
                    try:
                        hist = run_self_refine(
                            task, seed_modules, gen_cfg, feedback, n_iters=args.n_iters,
                            render=False, out_dir=REPO / f"runs/part3/self_refine_runs/{cond}/s{seed}/t{ti}", seed=seed,
                        )
                        summ = refinement_summary(hist, q_threshold=args.q)
                        rec = {"condition": cond, "seed": seed, "task_id": task.get("task_id", ti),
                               "ok": True, "intrinsic_quality": DEFAULT_INTRINSIC_QUALITY.get(cond, {}),
                               "history": hist, "summary": summ}
                    except Exception as exc:  # never crash the matrix
                        rec = {"condition": cond, "seed": seed, "task_id": task.get("task_id", ti),
                               "ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
                    handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    records.append(rec)
                    s = rec.get("summary") or {}
                    print(f"  [{cond}/s{seed}/t{ti}] gain={s.get('gain')} final={s.get('final')} "
                          f"iters_to_thr={s.get('iters_to_threshold')} ok={rec.get('ok')}", flush=True)

    _aggregate_and_write(records, args)


def _aggregate_and_write(records: list[dict], args) -> None:
    """Aggregate per-condition (the examiner-quality -> refinement-gain curve) + write summary."""
    iv = {}
    iv_path = REPO / "runs/probe/part3/feedback_iv.json"
    if iv_path.exists():
        iv = (json.loads(iv_path.read_text()).get("conditions") or {})
    per_condition = {}
    for cond in FEEDBACK_SOURCE_ORDER:
        ok = [r for r in records if r["condition"] == cond and r.get("ok") and r.get("summary")]
        if not ok:
            continue
        gains = [r["summary"]["gain"] for r in ok]
        # best_gain (best-over-iters minus initial) is the robust DV: a strong generator's
        # iter-2 can regress below the peak, so final-initial understates whether the
        # examiner's critique EVER helped. best_gain isolates "did the examiner buy any lift".
        best_gains = [r["summary"].get("best_gain", r["summary"]["best"] - r["summary"]["initial"]) for r in ok]
        finals = [r["summary"]["final"] for r in ok]
        reached = [r["summary"]["iters_to_threshold"] for r in ok if r["summary"]["iters_to_threshold"] is not None]
        per_condition[cond] = {
            "quality_scalar": (iv.get(cond, {}) or {}).get("quality_scalar"),
            "mean_gain": round(statistics.mean(gains), 4),
            "mean_best_gain": round(statistics.mean(best_gains), 4),
            "frac_improved": round(sum(1 for g in best_gains if g > 1e-6) / len(ok), 3),
            "mean_final_quality": round(statistics.mean(finals), 4),
            "mean_iters_to_threshold": round(statistics.mean(reached), 2) if reached else None,
            "frac_reached_threshold": round(len(reached) / len(ok), 3),
            "n": len(ok),
        }

    ordered = [c for c in FEEDBACK_SOURCE_ORDER if c in per_condition and per_condition[c]["quality_scalar"] is not None]
    qs = [per_condition[c]["quality_scalar"] for c in ordered]
    corr_gain = _pearson(qs, [per_condition[c]["mean_gain"] for c in ordered])
    corr_best_gain = _pearson(qs, [per_condition[c]["mean_best_gain"] for c in ordered])
    corr_final = _pearson(qs, [per_condition[c]["mean_final_quality"] for c in ordered])
    summary = {
        "vehicle": "self_refine",
        "n_iters": args.n_iters, "q_threshold": args.q,
        "per_condition": per_condition,
        "examiner_quality_vs_gain_corr": corr_gain,        # expect > 0: better examiner -> bigger refinement gain
        "examiner_quality_vs_best_gain_corr": corr_best_gain,  # robust variant (best-over-iters)
        "examiner_quality_vs_final_corr": corr_final,
        "note": "Downgraded Part 3 primary vehicle (lightweight). EvoPresent-style self-refine "
                "used as a controlled measurement of examiner-quality -> refinement gain; baseline-style, not headline.",
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"per_condition": per_condition,
                      "examiner_quality_vs_gain_corr": corr_gain,
                      "examiner_quality_vs_best_gain_corr": corr_best_gain,
                      "examiner_quality_vs_final_corr": corr_final}, indent=2, ensure_ascii=False))
    print(f"-> {args.summary}")


if __name__ == "__main__":
    main()
