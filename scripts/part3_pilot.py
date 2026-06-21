"""P5 — page-level pilot (occupancy milestone; estimate variance before deck-level).

Runs the matrix at page level with a small budget, then estimates the variance of
rollouts-to-threshold across seeds per condition (variance gating) to decide
whether deck-level differences will clear noise at the planned budget.

Outputs: runs/probe/part3/pilot_summary.json + reports/part3_pilot.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.feedback_sources import FEEDBACK_SOURCE_ORDER
from slide_examiner.optim_runtime import OptimizerRunConfig
from slide_examiner.part3_experiment import run_matrix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-dir", default=str(REPO / "data/part3/tasks"))
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/pilot_summary.json"))
    ap.add_argument("--report", default=str(REPO / "reports/part3_pilot.md"))
    ap.add_argument("--best-dir", default=str(REPO / "runs/part3/best_skill_pilot"))
    ap.add_argument("--out-root", default=str(REPO / "runs/part3/pilot_runs"))
    ap.add_argument("--main-jsonl", default=str(REPO / "runs/probe/part3/pilot_main.jsonl"))
    ap.add_argument("--carriers", nargs="+", default=["gepa"])
    ap.add_argument("--conditions", nargs="+", default=list(FEEDBACK_SOURCE_ORDER))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--budget", type=int, default=24)
    ap.add_argument("--q", type=float, default=0.8)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--from-jsonl", default=None, help="summarize an already-produced matrix jsonl instead of running")
    ap.add_argument("--gen-base-url", default="http://127.0.0.1:8200/v1")
    ap.add_argument("--optimizer-base-url", default="http://127.0.0.1:8200/v1")
    ap.add_argument("--examiner-base-url", default="http://127.0.0.1:8101/v1")
    ap.add_argument("--examiner-model", default="ft-8b")
    args = ap.parse_args()

    tasks = Path(args.tasks_dir)
    render = not args.smoke

    def make_config(condition: str, carrier: str, seed: int) -> OptimizerRunConfig:
        return OptimizerRunConfig(
            condition=condition, carrier=carrier,
            train_tasks=str(tasks / "train.jsonl"), val_tasks=str(tasks / "val.jsonl"), test_tasks=str(tasks / "test.jsonl"),
            out_root=args.out_root, rollout_budget=args.budget, seed=seed, q_threshold=args.q,
            level="page", max_slides=2, render=render,
            gen_base_url=args.gen_base_url, optimizer_base_url=args.optimizer_base_url,
            examiner_model=(None if condition == "linter" else args.examiner_model),
            examiner_base_url=(None if condition == "linter" else args.examiner_base_url),
        )

    if args.from_jsonl:
        from slide_examiner.io import read_jsonl
        records = read_jsonl(args.from_jsonl)
        args.carriers = sorted({r["carrier"] for r in records})
        args.conditions = [c for c in FEEDBACK_SOURCE_ORDER if any(r["condition"] == c for r in records)]
        args.seeds = sorted({r["seed"] for r in records})
    else:
        records = run_matrix(
            conditions=args.conditions, carriers=args.carriers, seeds=args.seeds,
            make_config=make_config, smoke=args.smoke, out_jsonl=args.main_jsonl, best_skill_dir=args.best_dir,
            on_record=lambda r: print(f"  [{r['carrier']}/{r['condition']}/s{r['seed']}] "
                                      f"to_thr={r.get('rollouts_to_threshold')} best={r.get('best_score')} ok={r.get('ok')}"),
        )

    # variance of rollouts-to-threshold across seeds, per (carrier, condition)
    per_cell: dict[str, dict] = {}
    for carrier in args.carriers:
        for cond in args.conditions:
            vals = [r["rollouts_to_threshold"] for r in records
                    if r["carrier"] == carrier and r["condition"] == cond and r.get("ok")
                    and r.get("rollouts_to_threshold") is not None]
            best = [r["best_score"] for r in records
                    if r["carrier"] == carrier and r["condition"] == cond and r.get("ok") and r.get("best_score") is not None]
            cell = {
                "n_seeds_reached": len(vals),
                "rollouts_to_threshold_mean": round(statistics.mean(vals), 2) if vals else None,
                "rollouts_to_threshold_std": round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0,
                "best_score_mean": round(statistics.mean(best), 3) if best else None,
            }
            per_cell[f"{carrier}/{cond}"] = cell

    summary = {
        "level": "page", "budget": args.budget, "q_threshold": args.q, "smoke": args.smoke,
        "carriers": args.carriers, "conditions": args.conditions, "seeds": args.seeds,
        "n_cells": len(records), "n_ok": sum(1 for r in records if r.get("ok")),
        "per_cell": per_cell,
        "variance_gate_note": "Proceed to deck-level only where cross-seed std of rollouts-to-threshold is small relative to cross-condition spread.",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Part 3 — Page-level pilot", "",
             f"- mode: {'SMOKE (offline fake LLMs)' if args.smoke else 'live'}; budget={args.budget}; q={args.q}",
             f"- cells ok: {summary['n_ok']}/{summary['n_cells']}", "",
             "| carrier/condition | seeds reached | rollouts→thr (mean±std) | best score |",
             "|---|---|---|---|"]
    for key, c in per_cell.items():
        mean = c["rollouts_to_threshold_mean"]
        std = c["rollouts_to_threshold_std"]
        rt = f"{mean}±{std}" if mean is not None else "censored"
        lines.append(f"| {key} | {c['n_seeds_reached']}/{len(args.seeds)} | {rt} | {c['best_score_mean']} |")
    lines += ["", "> " + summary["variance_gate_note"]]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["per_cell"], indent=2, ensure_ascii=False))
    print(f"-> {args.out}\n-> {args.report}")


if __name__ == "__main__":
    main()
