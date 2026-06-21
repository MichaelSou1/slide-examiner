"""P9 — Part 3 synthesis + H3 gate.

Reads feedback_iv.json, main.jsonl, hacking.json, final_eval.json and produces
the design-domain examiner-quality -> efficiency curve, optimizer-agnostic check,
reward-hacking table, and the H3 verdict.

H3 (SPEC §6): convergence rollouts decrease monotonically with examiner intrinsic
quality AND hybrid >= any single source. Falsification is reported honestly as a
design-domain feedback-transfer counterexample (still valuable).

Outputs: reports/part3.md + runs/probe/part3/summary.json
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


def _load(path: str) -> dict | list | None:
    p = Path(path)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    return json.loads(text)


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx > 0 and dy > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback-iv", default=str(REPO / "runs/probe/part3/feedback_iv.json"))
    ap.add_argument("--main-jsonl", default=str(REPO / "runs/probe/part3/main.jsonl"))
    ap.add_argument("--hacking", default=str(REPO / "runs/probe/part3/hacking.json"))
    ap.add_argument("--final-eval", default=str(REPO / "runs/probe/part3/final_eval.json"))
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/summary.json"))
    ap.add_argument("--report", default=str(REPO / "reports/part3.md"))
    args = ap.parse_args()

    iv = _load(args.feedback_iv) or {"conditions": {}}
    records = _load(args.main_jsonl) or []
    hacking = _load(args.hacking) or {"conditions": {}}
    final = _load(args.final_eval) or {"final_quality_by_condition": {}}

    budget = max((r.get("rollouts_to_threshold") or 0) for r in records) or 1
    carriers = sorted({r["carrier"] for r in records if r.get("ok")})

    # per-condition aggregates (pool carriers); censored -> budget (worst efficiency)
    def eff(rec_list):
        vals = [(r.get("rollouts_to_threshold") if r.get("rollouts_to_threshold") is not None else budget)
                for r in rec_list if r.get("ok")]
        return round(statistics.mean(vals), 2) if vals else None

    per_condition = {}
    for cond in FEEDBACK_SOURCE_ORDER:
        crecs = [r for r in records if r["condition"] == cond]
        if not any(r.get("ok") for r in crecs):
            continue
        q = (iv.get("conditions", {}).get(cond, {}) or {}).get("quality_scalar")
        ok_recs = [r for r in crecs if r.get("ok")]
        best_q = [r["best_quality"] for r in ok_recs if r.get("best_quality") is not None]
        per_condition[cond] = {
            "quality_scalar": q,
            "rollouts_to_threshold_mean": eff(crecs),
            "best_score_mean": round(statistics.mean([r["best_score"] for r in ok_recs if r.get("best_score") is not None]), 4)
            if any(r.get("best_score") is not None for r in ok_recs) else None,
            "best_quality_mean": round(statistics.mean(best_q), 4) if best_q else None,
            "final_quality": final.get("final_quality_by_condition", {}).get(cond),
            "by_carrier_rollouts": {c: eff([r for r in crecs if r["carrier"] == c]) for c in carriers},
            "hacking": hacking.get("conditions", {}).get(cond),
        }

    # H3 part 1: monotonic decrease of rollouts vs intrinsic quality (corr < 0)
    ordered = [c for c in FEEDBACK_SOURCE_ORDER if c in per_condition and per_condition[c]["quality_scalar"] is not None
               and per_condition[c]["rollouts_to_threshold_mean"] is not None]
    qs = [per_condition[c]["quality_scalar"] for c in ordered]
    rs = [per_condition[c]["rollouts_to_threshold_mean"] for c in ordered]
    corr = round(pearson(qs, rs), 3)

    # optimizer-agnostic: corr per carrier same (negative) direction
    carrier_corr = {}
    for c in carriers:
        oc = [cond for cond in ordered if per_condition[cond]["by_carrier_rollouts"].get(c) is not None]
        if len(oc) >= 2:
            carrier_corr[c] = round(pearson([per_condition[x]["quality_scalar"] for x in oc],
                                            [per_condition[x]["by_carrier_rollouts"][c] for x in oc]), 3)
    optimizer_agnostic = len(carrier_corr) >= 2 and all(v <= 0 for v in carrier_corr.values())

    # H3 part 2: hybrid >= any single source (fewer rollouts AND/OR higher final quality)
    singles = [c for c in ("linter", "zero_shot_8b", "zero_shot_30b", "finetuned_8b") if c in per_condition]
    hybrid = per_condition.get("hybrid")
    hybrid_ge = None
    if hybrid and singles:
        h_eff = hybrid["rollouts_to_threshold_mean"]
        single_effs = [per_condition[c]["rollouts_to_threshold_mean"] for c in singles if per_condition[c]["rollouts_to_threshold_mean"] is not None]
        hybrid_ge = bool(h_eff is not None and single_effs and h_eff <= min(single_effs) + 1e-9)

    monotonic = corr < 0
    h3_supported = bool(monotonic and (hybrid_ge is not False))
    verdict = "SUPPORTED" if h3_supported else "COUNTEREXAMPLE (design-domain feedback-transfer; reported honestly)"

    summary = {
        "carriers": carriers,
        "budget_censor": budget,
        "per_condition": per_condition,
        "h3": {
            "quality_vs_rollouts_corr": corr,
            "monotonic_decrease": monotonic,
            "optimizer_agnostic": optimizer_agnostic,
            "carrier_corr": carrier_corr,
            "hybrid_ge_single_sources": hybrid_ge,
            "verdict": verdict,
        },
        "novelty_scope": "intersection transfer (verifier-quality->efficiency) into skill-space x design + decoupled verifiable/learned feedback + gold-vs-proxy audit; NOT a claim that feedback quality matters (RL already established that).",
        "smoke": all(r.get("smoke") for r in records) if records else None,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # report
    mode = "SMOKE (offline fake LLMs)" if summary["smoke"] else "live"
    lines = [
        "# Part 3 — Examiner feedback quality → skill-space optimization efficiency", "",
        f"_Mode: {mode}; carriers: {', '.join(carriers) or 'none'}._", "",
        "> Novelty scope: " + summary["novelty_scope"], "",
        "## Examiner-quality → efficiency curve (design domain)", "",
        "_Convergence DV = rollouts until the running-best **independent common quality** "
        "(coverage+geometry+terms+conciseness, model-free) ≥ threshold — the same yardstick "
        "for every condition; censored cells = budget. `best gold` = best common quality reached; "
        "`best proxy` = the optimizer's own objective (each condition's feedback selection_score)._", "",
        "| condition | intrinsic quality | rollouts→thr (↓ better) | best gold | best proxy | final quality | audit gold | over-opt |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cond in FEEDBACK_SOURCE_ORDER:
        c = per_condition.get(cond)
        if not c:
            continue
        hk = c.get("hacking") or {}
        lines.append(
            f"| {cond} | {c['quality_scalar']} | {c['rollouts_to_threshold_mean']} | {c.get('best_quality_mean')} | "
            f"{c['best_score_mean']} | {c['final_quality']} | {hk.get('gold_score','-')} | {'YES' if hk.get('overoptimized') else 'no'} |"
        )
    lines += [
        "", "## H3 gate", "",
        f"- quality↔rollouts correlation: **{corr}** (expect < 0 → higher quality, fewer rollouts)",
        f"- monotonic decrease: **{monotonic}**",
        f"- optimizer-agnostic (per-carrier corr {carrier_corr}): **{optimizer_agnostic}**",
        f"- hybrid ≥ single sources: **{hybrid_ge}**",
        f"- **Verdict: {verdict}**", "",
        "_Reward-hacking: hybrid (verifiable selection gate) expected smallest proxy−gold gap; see reports/part3_hacking.md._",
    ]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["h3"], indent=2, ensure_ascii=False))
    print(f"-> {args.out}\n-> {args.report}")


if __name__ == "__main__":
    main()
