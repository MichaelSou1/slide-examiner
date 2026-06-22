"""Part 3 Protocol-3 (a) — audit a *published* reward model for the G7 blind spot.

We do NOT retrain a reward model (expensive, derivative). Instead we take
published ones and ask one falsifiable question of each:

    Does it penalise a slide whose content visibly **overflows its container**
    (our G7 render-containment class), i.e. is reward(clean) > reward(defective)?

A reward blind to render-containment overflow assigns the defective slide a
reward no lower than its clean twin -> paired preference accuracy ~= chance
(0.5). We measure that per defect class on the SAME paired-clean slides used by
Protocols 1-2, with:

  * **freeform** renders (the defect actually renders) — the real sensitivity test;
  * **template** renders (snap-to-master absorbs the geometry defect, Protocol-3c)
    — where the "defective" image is pixel-identical to clean, so even a perfect
    reward model is structurally unable to react. This ties the reward blind spot
    to the perturbation-fidelity hazard.

This script audits ONE reward model (``--rm``), abstracted behind
``slide_examiner.reward_adapters.RewardAdapter`` (DocReward / Skywork-VL /
IXC-2.5 / aesthetic). Output -> ``data/part3/p3_audit__<key>.json``. The merge
step (``part3_p3_audit_merge.py``) combines them into ``p3_audit_multi.json`` and
the cross-RM fidelity file ``p3_fidelity_multi.json`` to make the blind spot
*model-agnostic*.

Run on one GPU:  CUDA_VISIBLE_DEVICES=2 python scripts/part3_p3_reward_audit.py --rm skywork-vl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO))
from slide_examiner.statistics import wilson_interval  # noqa: E402
from slide_examiner import reward_adapters as RA  # noqa: E402

# freeform sensitivity classes (does the reward penalise the VISIBLE defect?)
FREEFORM_CLASSES = ["G7_RENDER_CONTAINMENT_OVERFLOW", "G1_TEXT_OVERFLOW",
                    "G2_ELEMENT_OVERLAP", "G5_BRAND_COLOR_VIOLATION",
                    "S4_DENSITY_RULE_VIOLATION", "S6_IMAGE_TEXT_CONTRADICTION"]
# template (snap-absorbed) classes — perturbation-fidelity tie-in (defect erased)
TEMPLATE_CLASSES = ["G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET", "G6_MARGIN_VIOLATION"]


def defect_of(rec: dict) -> str:
    return rec["labels"][0]["type"] if rec.get("labels") else "NO_DEFECT"


def variant_paths(rec: dict, variant: str):
    """(defective_img, clean_img) for the requested render variant."""
    dp = rec.get("image_path")
    cp = (rec.get("pair") or {}).get("clean_image_path")
    if not dp or not cp:
        return None, None
    if variant == "template":
        dp, cp = dp.replace("__freeform", "__template"), cp.replace("__freeform", "__template")
    for p in (dp, cp):
        if not Path(p if Path(p).is_absolute() else REPO / p).exists():
            return None, None
    return dp, cp


def run_class(scorer, recs, defect, render, max_n, variant="generic"):
    # keep freeform synth records (drop interleaved __template ones) AND the G7
    # records (whose paths carry neither suffix — they are freeform by construction).
    pos = [r for r in recs if defect_of(r) == defect
           and "__template" not in (r.get("image_path") or "")][:max_n]
    gaps, clean_pref, n = [], 0, 0
    for r in pos:
        dp, cp = variant_paths(r, render)
        if not dp:
            continue
        rd = scorer.score(dp, variant=variant)
        rc = scorer.score(cp, variant=variant)
        gap = rc - rd          # >0 means the reward correctly prefers the clean slide
        gaps.append(gap)
        clean_pref += int(gap > 0)
        n += 1
    if not n:
        return None
    ci = wilson_interval(clean_pref, n)
    mean_gap = sum(gaps) / n
    return {
        "defect": defect, "render": render, "n": n,
        "preference_accuracy": round(clean_pref / n, 3),
        "preference_ci": [round(ci.low, 3), round(ci.high, 3)],
        "mean_reward_gap_clean_minus_def": round(mean_gap, 4),
        "median_gap": round(sorted(gaps)[n // 2], 4),
        "n_clean_preferred": clean_pref,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rm", default="docreward", choices=list(RA.ADAPTERS),
                    help="which published reward model to audit")
    ap.add_argument("--model-path", default=None, help="override the on-disk path")
    ap.add_argument("--synth", default="data/part2/manifest_eval_test_rendered.jsonl")
    ap.add_argument("--g7", default="data/part3/manifest_g7_rendered.jsonl")
    ap.add_argument("--max-per-defect", type=int, default=40)
    ap.add_argument("--variant", default="generic", choices=["generic", "probe"],
                    help="elicitation regime for PROMPT_CONDITIONED RMs: 'generic' "
                         "(deployment-realistic, PRIMARY) / 'probe' (defect-aware, sensitivity)")
    ap.add_argument("--g7-only", action="store_true",
                    help="only run G7 freeform (used for the probe sensitivity pass)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print(f"loading reward model '{args.rm}' ...", flush=True)
    scorer = RA.build(args.rm, path=args.model_path, repo=REPO).load()
    print(f"loaded {scorer.display_name} ({scorer.category}, {scorer.contract}).", flush=True)

    synth = [json.loads(l) for l in Path(args.synth).open() if l.strip()]
    g7 = [json.loads(l) for l in Path(args.g7).open() if l.strip()]

    results = []
    freeform = ["G7_RENDER_CONTAINMENT_OVERFLOW"] if args.g7_only else FREEFORM_CLASSES
    for d in freeform:
        recs = g7 if d == "G7_RENDER_CONTAINMENT_OVERFLOW" else synth
        r = run_class(scorer, recs, d, "freeform", args.max_per_defect, variant=args.variant)
        if r:
            results.append(r)
            print(f"  [freeform] {d:32s} pref_acc={r['preference_accuracy']} "
                  f"gap={r['mean_reward_gap_clean_minus_def']} n={r['n']}", flush=True)
    if not args.g7_only:
        # template (snap-absorbed): defect erased -> gap should be ~0 for ANY RM.
        for d in TEMPLATE_CLASSES:
            r = run_class(scorer, synth, d, "template", args.max_per_defect, variant=args.variant)
            if r:
                results.append(r)
                print(f"  [template] {d:32s} pref_acc={r['preference_accuracy']} "
                      f"gap={r['mean_reward_gap_clean_minus_def']} n={r['n']}", flush=True)

    q_a = RA.ELICITATIONS[args.variant]
    out = {
        **scorer.meta(),
        "variant": args.variant,
        "elicitation": {"question": q_a[0], "answer": q_a[1]}
        if scorer.contract == RA.PROMPT_CONDITIONED else None,
        "metric": "paired preference accuracy = P(reward(clean) > reward(defective)); "
                  "0.5 = blind, 1.0 = always prefers the clean slide",
        "results": results,
    }
    suffix = "" if args.variant == "generic" else f"__{args.variant}"
    out_path = args.out or f"data/part3/p3_audit__{args.rm}{suffix}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", out_path)


if __name__ == "__main__":
    main()
