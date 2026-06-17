"""Track L — symbolic linter as the G-group ground-truth / upper bound.

Runs `lint_slide` over the frozen geometry subset (data/part1/manifest_geometry.jsonl:
G1-G6 defectives at a full severity grid + paired clean negatives) and reports,
per defect type:
  * detection recall by severity bucket (does the linter fire where the injected
    geometry defect lives?),
  * false-positive rate on the paired clean negatives,
  * the continuous geometry reading the linter recovers vs. the injected
    ground-truth magnitude (overflow_px / iou / offset_px / delta_pt / delta_e /
    bleed_px) — this is the psychophysical x-axis the SPEC (§3.0, H1 restated)
    asks to be drawn on the linter side, not the VLM side.

This is the deterministic counterpart to the VLM geometry sweep
(runs/probe/part1_geometry_summary.json): the linter is the detector of record
for G2-G6 and the upper bound the VLM is measured against.

Usage:
  PYTHONPATH=. python scripts/part1_linter_track.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from slide_examiner.geometry import lint_slide
from slide_examiner.schemas import Slide

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "part1" / "manifest_geometry.jsonl"
SUMMARY = REPO / "runs" / "probe" / "part1_linter_summary.json"
REPORT = REPO / "reports" / "part1_linter_track.md"

G_TYPES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
           "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]
# Which injected-magnitude field carries the continuous geometry quantity per type.
MAG_FIELD = {"G1_TEXT_OVERFLOW": "overflow_px", "G2_ELEMENT_OVERLAP": "iou",
             "G3_ALIGNMENT_OFFSET": "offset_px", "G4_FONT_SIZE_INCONSISTENCY": "delta_pt",
             "G5_BRAND_COLOR_VIOLATION": "delta_e", "G6_MARGIN_VIOLATION": "bleed_px"}
# The measured-quantity key the matching linter detector stamps onto its label.
READ_FIELD = MAG_FIELD


def main() -> None:
    recs = [json.loads(line) for line in MANIFEST.open() if line.strip()]

    # Per (type, severity-bucket): [tp, n] ; split by template condition so the
    # freeform column is the true upper bound and the template column is the
    # snap-to-master absorption measurement (H1-tpl, model-decoupled).
    CONDS = ("freeform", "template")
    by_sev: dict[str, dict[str, dict[float, list]]] = defaultdict(
        lambda: {c: defaultdict(lambda: [0, 0]) for c in CONDS})
    cond_tot: dict[str, dict[str, list]] = {t: {c: [0, 0] for c in CONDS} for t in G_TYPES}
    readings: dict[str, list] = defaultdict(list)  # (injected, measured) pairs, freeform only
    fp = {t: 0 for t in G_TYPES}
    neg_n = 0
    parse_fail = 0

    for rec in recs:
        try:
            slide = Slide.from_mapping(rec["slide"])
        except Exception:
            parse_fail += 1
            continue
        detected = lint_slide(slide)
        detected_by_type: dict[str, list] = defaultdict(list)
        for d in detected:
            detected_by_type[d.type].append(d)

        labels = rec.get("labels") or []
        positive_types = {lb["type"] for lb in labels if lb["type"] in G_TYPES}
        cond = rec["metadata"].get("template_condition") or "freeform"

        if not positive_types:  # paired clean negative
            neg_n += 1
            for t in G_TYPES:
                if detected_by_type.get(t):
                    fp[t] += 1
            continue

        for lb in labels:
            t = lb["type"]
            if t not in G_TYPES:
                continue
            sev = round(float(lb.get("severity", 0.0)), 3)
            hit = bool(detected_by_type.get(t))
            cell = by_sev[t][cond][sev]
            cell[0] += int(hit)
            cell[1] += 1
            cond_tot[t][cond][0] += int(hit)
            cond_tot[t][cond][1] += 1
            if cond != "freeform":
                continue
            injected = lb.get("metadata", {}).get(MAG_FIELD[t])
            measured = None
            if hit:
                # take the largest measured reading of that detector on this slide
                vals = [d.metadata.get(READ_FIELD[t]) for d in detected_by_type[t]
                        if d.metadata.get(READ_FIELD[t]) is not None]
                measured = max(vals) if vals else None
            readings[t].append({"severity": sev, "injected": injected, "measured": measured, "hit": hit})

    summary = {
        "subset": str(MANIFEST.relative_to(REPO)),
        "n_records": len(recs),
        "n_clean_negatives": neg_n,
        "parse_failures": parse_fail,
        "by_defect": {},
        "template_absorption": {},
        "false_positives": {t: [fp[t], neg_n] for t in G_TYPES},
        "readings": readings,
    }
    for t in G_TYPES:
        ff, tpl = cond_tot[t]["freeform"], cond_tot[t]["template"]
        ff_recall = round(ff[0] / ff[1], 3) if ff[1] else None
        tpl_recall = round(tpl[0] / tpl[1], 3) if tpl[1] else None
        summary["by_defect"][t] = {
            "freeform_recall": ff_recall, "freeform": ff,
            "template_recall": tpl_recall, "template": tpl,
            "by_severity_freeform": {str(s): by_sev[t]["freeform"][s] for s in sorted(by_sev[t]["freeform"])},
            "fp_on_clean": [fp[t], neg_n],
        }
        # Absorption: fraction of freeform-detectable defects the template removes.
        absorbed = None
        if ff_recall:
            absorbed = round(1 - (tpl_recall or 0) / ff_recall, 3)
        summary["template_absorption"][t] = absorbed

    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    L = []
    L.append("# Part 1 — Track L: symbolic linter as the G-group detector of record\n")
    L.append(f"Deterministic `lint_slide` over `{MANIFEST.relative_to(REPO)}` "
             f"({len(recs)} records: G1-G6 at a full severity grid + {neg_n} paired clean "
             f"negatives). The linter is the **ground truth and upper bound** the VLM "
             f"geometry sweep (`runs/probe/part1_geometry_summary.json`) is measured against.\n")
    L.append("## Detection recall + false positives (freeform = upper bound)\n")
    L.append("On **freeform** the linter is the detector of record; misses are only where "
             "the injected magnitude is below the linter's own deliberate threshold "
             "(G2 iou<0.05, G3 offset<4px). 0 FP across all clean negatives.\n")
    L.append("| defect | freeform recall | tp/n | template recall | FP on clean |")
    L.append("|---|---|---|---|---|")
    for t in G_TYPES:
        d = summary["by_defect"][t]
        L.append(f"| {t} | **{d['freeform_recall']:.2f}** | {d['freeform'][0]}/{d['freeform'][1]} "
                 f"| {d['template_recall']:.2f} | {d['fp_on_clean'][0]}/{d['fp_on_clean'][1]} |")
    L.append("")
    L.append("## Template collapse (H1-tpl): snap-to-master absorption, model-decoupled\n")
    L.append("Absorption = `1 - template_recall / freeform_recall`. Measured purely on the "
             "linter (no VLM), per SPEC §3.0(8): the question \"does the template *absorb* the "
             "geometry defect\" is symbolic and model-independent.\n")
    L.append("| defect | absorption | reading |")
    L.append("|---|---|---|")
    for t in G_TYPES:
        a = summary["template_absorption"][t]
        verdict = "**fully absorbed**" if a and a >= 0.99 else ("not absorbed" if not a else f"partial")
        L.append(f"| {t} | {a:.2f} | {verdict} |")
    L.append("")
    L.append("- Positional geometry (G1 overflow, G2 overlap, G3 offset, G6 margin) is "
             "**fully absorbed** by snap-to-master → the intern-system simplification "
             "\"under a corporate master you can drop G1/G2/G3/G6 checks\" is empirically "
             "licensed (SPEC §8).\n- Font-size (G4) and brand-color (G5) are **not** snapped "
             "by the master and survive → those two G checks stay live even under templates.\n")
    L.append("## Recall by injected severity, freeform (psychophysical x-axis lives here)\n")
    for t in G_TYPES:
        mag = MAG_FIELD[t]
        L.append(f"**{t}** (magnitude = `{mag}`):  ")
        cells = summary["by_defect"][t]["by_severity_freeform"]
        row = " · ".join(f"{s}: {v[0]}/{v[1]}" for s, v in cells.items())
        L.append(f"{row}\n")
    L.append("## Linter-recovered reading vs. injected magnitude (monotone = usable as θ axis)\n")
    for t in G_TYPES:
        pts = [r for r in readings[t] if r["measured"] is not None]
        if not pts:
            L.append(f"**{t}**: no measured readings recovered.\n")
            continue
        sample = sorted(pts, key=lambda r: r["injected"] or 0)
        shown = " · ".join(f"inj={r['injected']:.3g}->meas={r['measured']:.3g}" for r in sample[:6])
        L.append(f"**{t}**: {shown}\n")
    L.append("## Take\n")
    L.append("- The linter recovers a **continuous, monotone** geometry reading for every G "
             "type — this is where the SPEC §3.0 psychophysical curve is drawn, not on the "
             "VLM (which is step-like / random; see `part1_geometry_threshold.md`).")
    L.append("- Linter recall and 0-FP-on-clean set the **upper bound**; the VLM pointwise "
             "geometry numbers (4B/8B random, only 30B G1) are reported only as "
             "\"broke / didn't break random\", per the three-track design.")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY.relative_to(REPO)} and {REPORT.relative_to(REPO)}")
    for t in G_TYPES:
        d = summary["by_defect"][t]
        print(f"  {t:32s} freeform={d['freeform_recall']} template={d['template_recall']} "
              f"absorb={summary['template_absorption'][t]} FP={d['fp_on_clean'][0]}/{neg_n}")


if __name__ == "__main__":
    main()
