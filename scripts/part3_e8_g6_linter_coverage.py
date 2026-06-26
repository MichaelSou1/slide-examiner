r"""E8 CPU recompute — Table-2 LINTER column on the page-offset G6 (no GPU).

Companion to ``part3_e8_linter_coverage.py`` (G3/G5). After the E8
re-operationalisation \g{G6} margin is a *page offset* (whole content block
shifted toward one edge; ``manifest_g6_internal.jsonl``, mode
``internal_page_offset``). The ``detect_margin_violations`` rule reasons over the
declared-bbox IR, so the coverage cell is pure CPU. Strata = shift magnitude
(px). Reuses ``part3_p2_eval.linter_cell`` so the number is identical to the
linter column the GPU coverage scorer writes.

Usage:  python scripts/part3_e8_g6_linter_coverage.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from part3_p2_eval import linter_cell, freeform_only  # noqa: E402
from part2_eval import defect_of  # noqa: E402
from slide_examiner.hybrid_critic import linter_types  # noqa: E402
from slide_examiner.statistics import wilson_interval  # noqa: E402

MANIFEST = REPO / "data/part3/manifest_g6_internal.jsonl"
G6 = "G6_MARGIN_VIOLATION"


def shift_of(rec):
    m = (rec.get("labels") or [{}])[0].get("metadata") or {}
    return round(m.get("shift_px", 0))


def main():
    rows = freeform_only([json.loads(l) for l in MANIFEST.open() if l.strip()])
    pos = [r for r in rows if defect_of(r) == G6]
    cell = linter_cell(pos)
    if not cell:
        raise SystemExit("no G6 positives in manifest")

    rci = wilson_interval(cell["tp"], cell["n_pos"])
    out = {"manifest": str(MANIFEST), "per_class": {G6: cell}, "per_stratum": {}}
    md = ["# E8 CPU recompute — Table-2 LINTER column (page-offset G6)\n",
          "Linter (`detect_margin_violations`) over declared-bbox IR (CPU only). "
          "Specificity on the paired CLEAN IR. G6 re-posed as page offset "
          "(whole block shifted to one edge).\n",
          "| Class | linter bal-acc | recall [95% CI] | specificity | n=pos+neg | tp/fp |",
          "|---|---|---|---|---|---|",
          f"| G6 | {cell['bal_acc']:.3f} | {cell['recall']:.2f} "
          f"[{rci.low:.2f}-{rci.high:.2f}] | {cell['specificity']:.2f} | "
          f"{cell['n_pos']}+{cell['n_neg']} | {cell['tp']}/{cell['fp']} |"]

    md.append("\n## Per-stratum linter recall (caught once content nears/clips the edge)\n")
    md.append("| stratum (shift_px) | linter recall | n |")
    md.append("|---|---|---|")
    strata = collections.defaultdict(lambda: [0, 0])
    for r in pos:
        v = shift_of(r)
        hit = G6 in linter_types(r)
        strata[v][0] += int(hit)
        strata[v][1] += 1
    out["per_stratum"][G6] = {f"px{v}": {"recall": round(h / n, 3), "n": n}
                              for v, (h, n) in sorted(strata.items())}
    for v, (h, n) in sorted(strata.items()):
        md.append(f"| {v:g}px | {h/n:.2f} | {n} |")

    fp_clean = sum(1 for r in pos if G6 in linter_types(r, use_clean=True))
    md.append(f"\n**False-fire on paired clean IR:** {fp_clean} (0 = calibrated).")

    text = "\n".join(md) + "\n"
    (REPO / "reports/_e8_g6_linter_coverage.md").write_text(text, encoding="utf-8")
    (REPO / "data/part3/e8_g6_linter_coverage.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(text)
    print("[wrote reports/_e8_g6_linter_coverage.md + data/part3/e8_g6_linter_coverage.json]")


if __name__ == "__main__":
    main()
