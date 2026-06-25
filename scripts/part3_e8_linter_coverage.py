"""E8 CPU recompute — Table-2 LINTER column on internal-口径 G3/G5 (no GPU).

The symbolic geometry linter reasons over the declared-bbox IR, so its coverage
cells are pure CPU. After the E8 re-operationalisation the relevant rules are
internal-contrast (``alignment_group`` for G3, ``detect_color_inconsistency`` for
G5); this script splices the actual Table-2 linter numbers + a per-stratum
recall breakdown (supra-threshold detected, sub-threshold abstained = the
well-posed residue), with Wilson CIs and 0-false-fire specificity on the paired
clean IR.

Reuses ``part3_p2_eval.linter_cell`` so the number is identical to the linter
column the GPU coverage scorer (Row 3) writes into p2_synth_internal_g3g5.json.

Usage:  python scripts/part3_e8_linter_coverage.py
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

MANIFEST = REPO / "data/part3/manifest_coverage_internal.jsonl"
CLASSES = ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION"]
SHORT = {"G3_ALIGNMENT_OFFSET": "G3", "G5_BRAND_COLOR_VIOLATION": "G5"}


def stratum_of(rec):
    m = (rec.get("labels") or [{}])[0].get("metadata") or {}
    v = m.get("offset_px")
    return ("px", v) if v is not None else ("ΔE", round(m.get("delta_e", 0)))


def main():
    rows = freeform_only([json.loads(l) for l in MANIFEST.open() if l.strip()])
    bydef = collections.defaultdict(list)
    for r in rows:
        bydef[defect_of(r)].append(r)

    out = {"manifest": str(MANIFEST), "per_class": {}, "per_stratum": {}}
    md = ["# E8 CPU recompute — Table-2 LINTER column (internal-口径 G3/G5)\n",
          "Linter over declared-bbox IR (CPU only). Detection = the linter emits the class; "
          "specificity measured on the paired CLEAN IR (declared-bbox negative). Internal rules: "
          "`alignment_group` (G3), `detect_color_inconsistency` (G5).\n",
          "| Class | linter bal-acc | recall [95% CI] | specificity | n=pos+neg | tp/fp |",
          "|---|---|---|---|---|---|"]
    for d in CLASSES:
        pos = bydef.get(d, [])
        cell = linter_cell(pos)
        if not cell:
            continue
        out["per_class"][d] = cell
        rci = wilson_interval(cell["tp"], cell["n_pos"])
        md.append(f"| {SHORT[d]} | {cell['bal_acc']:.3f} | {cell['recall']:.2f} "
                  f"[{rci.low:.2f}-{rci.high:.2f}] | {cell['specificity']:.2f} | "
                  f"{cell['n_pos']}+{cell['n_neg']} | {cell['tp']}/{cell['fp']} |")

    # per-stratum recall (which magnitudes the linter catches)
    md.append("\n## Per-stratum linter recall (supra-threshold detected / sub-threshold abstained)\n")
    md.append("| Class | stratum | linter recall | n |")
    md.append("|---|---|---|---|")
    for d in CLASSES:
        strata = collections.defaultdict(lambda: [0, 0])  # hit, n
        for r in bydef.get(d, []):
            unit, val = stratum_of(r)
            hit = d in linter_types(r)
            key = (unit, val)
            strata[key][0] += int(hit)
            strata[key][1] += 1
        out["per_stratum"][d] = {f"{u}{v}": {"recall": round(h / n, 3), "n": n}
                                 for (u, v), (h, n) in sorted(strata.items(), key=lambda kv: kv[0][1])}
        for (u, v), (h, n) in sorted(strata.items(), key=lambda kv: kv[0][1]):
            md.append(f"| {SHORT[d]} | {v:g}{u} | {h/n:.2f} | {n} |")

    # specificity sanity: false-fire count on clean IR across both classes
    fp_clean = sum(1 for d in CLASSES for r in bydef.get(d, []) if d in linter_types(r, use_clean=True))
    md.append(f"\n**False-fire on paired clean IR:** {fp_clean} (0 = calibrated; the linter's near-zero-FP edge).")

    text = "\n".join(md) + "\n"
    (REPO / "reports/_e8_linter_coverage.md").write_text(text, encoding="utf-8")
    (REPO / "data/part3/e8_linter_coverage.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(text)
    print("[wrote reports/_e8_linter_coverage.md + data/part3/e8_linter_coverage.json]")


if __name__ == "__main__":
    main()
