"""P2 — record the examiner feedback-source intrinsic quality (the H3 x-axis).

Pulls intrinsic quality from the FROZEN Part 1/2 summaries (never recomputed in
Part 3) and writes a condition -> quality mapping consumed by the synthesis step.

Outputs: runs/probe/part3/feedback_iv.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.feedback_sources import DEFAULT_INTRINSIC_QUALITY, FEEDBACK_SOURCE_ORDER


def _best_semantic(model_block: dict) -> float | None:
    """Max semantic group balanced-accuracy across modalities for a model block."""
    pt = model_block.get("pointwise_test", {})
    metrics = pt.get("metrics", {})
    best = None
    for mod, m in metrics.items():
        if not isinstance(m, dict):
            continue
        sem = (m.get("group_bal_acc") or {}).get("semantic")
        if sem is not None:
            best = sem if best is None else max(best, sem)
    return best


def _linter_quality(part1_linter: dict) -> float:
    """Geometry detection quality of the verifiable linter (≈ recall on freeform)."""
    by_defect = part1_linter.get("by_defect", {})
    recalls = []
    for _, stats in by_defect.items():
        r = stats.get("recall") if isinstance(stats, dict) else None
        if isinstance(r, (int, float)):
            recalls.append(float(r))
    if recalls:
        return round(sum(recalls) / len(recalls), 3)
    return 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part2-summary", default=str(REPO / "runs/probe/part2_summary.json"))
    ap.add_argument("--part1-linter", default=str(REPO / "runs/probe/part1_linter_summary.json"))
    ap.add_argument("--out", default=str(REPO / "runs/probe/part3/feedback_iv.json"))
    args = ap.parse_args()

    part2 = json.loads(Path(args.part2_summary).read_text()) if Path(args.part2_summary).exists() else {}
    part1 = json.loads(Path(args.part1_linter).read_text()) if Path(args.part1_linter).exists() else {}
    models = part2.get("models", {})

    zs8 = _best_semantic(models.get("zs-8b", {})) or DEFAULT_INTRINSIC_QUALITY["zero_shot_8b"]["semantic_bal_acc"]
    zs30 = _best_semantic(models.get("zs-30b", {})) or DEFAULT_INTRINSIC_QUALITY["zero_shot_30b"]["semantic_bal_acc"]
    ft = _best_semantic(models.get("ft-8b", {})) or DEFAULT_INTRINSIC_QUALITY["finetuned_8b"]["semantic_bal_acc"]
    linter_geo = _linter_quality(part1) if part1 else DEFAULT_INTRINSIC_QUALITY["linter"]["geometry_bal_acc"]

    # quality_scalar = the examiner feedback quality used as the H3 x-axis.
    # linter provides no semantic reflection => semantic quality ~ chance (0.5);
    # hybrid reuses the ft reflection (same scalar) but adds a verifiable gate
    # (its advantage is tested in efficiency, not in this scalar).
    quality_scalar = {
        "linter": 0.5,
        "zero_shot_8b": round(zs8, 3),
        "zero_shot_30b": round(zs30, 3),
        "finetuned_8b": round(ft, 3),
        "hybrid": round(ft, 3),
    }

    out = {
        "source": {"part2_summary": args.part2_summary, "part1_linter": args.part1_linter},
        "measured": {"linter_geometry_recall": linter_geo, "zs8_semantic": zs8, "zs30_semantic": zs30, "ft_semantic": ft},
        "conditions": {
            cond: {
                "rank": i,
                "quality_scalar": quality_scalar[cond],
                "intrinsic_quality": DEFAULT_INTRINSIC_QUALITY[cond],
            }
            for i, cond in enumerate(FEEDBACK_SOURCE_ORDER)
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out["conditions"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
