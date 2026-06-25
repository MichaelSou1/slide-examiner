"""E8 internal-口径 roster summary (Row 1 diagnosis).

Aggregates the local-roster G3/G5 internal-contrast sweep written by
part3_p1_roster.py --tags internal (files data/part3/p1e8_<model>_internal_<cond>.json
and *_rows.jsonl) into the numbers the E8 paper edits need:

  * per (model x defect): C0 vs C3 NAMED bal-acc [Wilson CI] (n) + 2-AFC strict acc
    -> the "format-suppressed-then-recoverable" headline (replaces the buggy
       absolute-reference G3/G5 cells).
  * per (defect x stratum): C0 vs C3 bal-acc, per model and roster-mean -> the
    "clean magnitude threshold" evidence (G3 8/16/32 px, G5 dE 12/24/40).

The headline metric is NAMED attribution (did the model surface *this* defect),
which is where absolute pointwise C0 suppresses and atomic C3 / paired AFC recover.
DETECTION (flagged anything) is reported alongside for completeness.

Usage:
  python scripts/part3_e8_summary.py [--glob 'data/part3/p1e8_*_internal_*'] \
    --json data/part3/e8_roster_summary.json --md reports/_e8_roster.md
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from slide_examiner.statistics import wilson_interval  # noqa: E402
from part3_p2_eval import freeform_only  # noqa: E402

# Corrected E8 diagnosis: coverage_internal (matched per-deck twins), freeform-only,
# file prefix p1e8c, tag 'covint'. Full G3 saturation curve {2..64}px + G5 {6..40}.
MANIFEST = REPO / "data/part3/manifest_coverage_internal.jsonl"
PREFIX = "p1e8c"
TAG = "covint"
DEFECTS = ["G3_ALIGNMENT_OFFSET", "G5_BRAND_COLOR_VIOLATION"]
SHORT = {"G3_ALIGNMENT_OFFSET": "G3", "G5_BRAND_COLOR_VIOLATION": "G5"}
MODEL_ORDER = ["qwen35-9b", "internvl-8b", "ovis-9b", "qwen36-27b", "qwen35-27b", "gemma4-31b"]
STRATA = {"G3_ALIGNMENT_OFFSET": [2.0, 4.0, 8.0, 16.0, 32.0, 48.0, 64.0],
          "G5_BRAND_COLOR_VIOLATION": [6, 12, 24, 40]}


def stratum_map() -> dict:
    """sample_id -> (defect, stratum) from the freeform-only coverage manifest."""
    out = {}
    for r in freeform_only([json.loads(l) for l in MANIFEST.open() if l.strip()]):
        lab = (r.get("labels") or [{}])[0]
        m = lab.get("metadata") or {}
        strat = m.get("offset_px")
        if strat is None:
            strat = round(m.get("delta_e", 0))
        out[r["sample_id"]] = (lab.get("type"), strat)
    return out


def _base(sid: str) -> str:
    return sid[:-len("__CLEAN")] if sid.endswith("__CLEAN") else sid


def balacc(pos_hit, pos_n, neg_fp, neg_n):
    """bal-acc from raw counts; returns (bal_acc, recall, spec, n)."""
    if not pos_n or not neg_n:
        return None
    recall = pos_hit / pos_n
    spec = 1 - neg_fp / neg_n
    rci = wilson_interval(pos_hit, pos_n)
    sci = wilson_interval(neg_n - neg_fp, neg_n)
    return {"bal_acc": round((recall + spec) / 2, 3), "recall": round(recall, 3),
            "specificity": round(spec, 3), "n_pos": pos_n, "n_neg": neg_n,
            "recall_ci": [round(rci.low, 3), round(rci.high, 3)],
            "spec_ci": [round(sci.low, 3), round(sci.high, 3)]}


def load_pointwise(model, cond, smap, metric):
    """rows file -> {defect: pooled cell, (defect,stratum): cell} for one metric
    in {'named_target','has_defect'}."""
    f = REPO / f"data/part3/{PREFIX}_{model}_{TAG}_{cond}_rows.jsonl"
    if not f.exists():
        return None
    rows = [json.loads(l) for l in f.open()]
    # accumulators keyed by 'all' and by stratum
    acc = collections.defaultdict(lambda: [0, 0, 0, 0])  # pos_hit,pos_n,neg_fp,neg_n
    for r in rows:
        if r.get("failure"):
            continue
        d, strat = smap.get(_base(r["sample_id"]), (r.get("defect"), None))
        hit = bool(r.get(metric))
        for key in ((d, "all"), (d, strat)):
            a = acc[key]
            if r["is_clean"]:
                a[2] += int(hit); a[3] += 1
            else:
                a[0] += int(hit); a[1] += 1
    out = {}
    for (d, strat), (ph, pn, nf, nn) in acc.items():
        out[(d, strat)] = balacc(ph, pn, nf, nn)
    return out


def load_afc(model, smap):
    """AFC rows -> {defect: strict_acc, (defect,stratum): strict_acc} (probe=defective
    called worse in BOTH presentation orders)."""
    f = REPO / f"data/part3/{PREFIX}_{model}_{TAG}_AFC_rows.jsonl"
    if not f.exists():
        return None
    rows = [json.loads(l) for l in f.open()]
    acc = collections.defaultdict(lambda: [0, 0])  # probe_worse_both, n_valid
    for r in rows:
        p0, p1 = r.get("pick_order0"), r.get("pick_order1")
        if p0 not in {"a", "b"} or p1 not in {"a", "b"}:
            continue
        d, strat = smap.get(_base(r.get("probe_id", "")), (r.get("defect"), None))
        worse_both = (p0 == "a" and p1 == "b")  # order0 A=probe; order1 B=probe
        for key in ((d, "all"), (d, strat)):
            acc[key][0] += int(worse_both); acc[key][1] += 1
    out = {}
    for key, (w, n) in acc.items():
        if n:
            ci = wilson_interval(w, n)
            out[key] = {"afc_strict": round(w / n, 3), "n_pairs": n,
                        "ci": [round(ci.low, 3), round(ci.high, 3)]}
    return out


def fmt_cell(c):
    if not c:
        return "—"
    ci = c.get("recall_ci") or [0, 0]
    return f"{c['bal_acc']:.2f} (r={c['recall']:.2f}[{ci[0]:.2f}-{ci[1]:.2f}],s={c['specificity']:.2f},n={c['n_pos']}+{c['n_neg']})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="data/part3/e8_roster_summary.json")
    ap.add_argument("--md", default="reports/_e8_roster.md")
    args = ap.parse_args()
    smap = stratum_map()

    models = [m for m in MODEL_ORDER
              if (REPO / f"data/part3/{PREFIX}_{m}_{TAG}_C0_rows.jsonl").exists()]
    data = {}
    for m in models:
        data[m] = {
            "C0_named": load_pointwise(m, "C0", smap, "named_target"),
            "C0_det": load_pointwise(m, "C0", smap, "has_defect"),
            "C3_named": load_pointwise(m, "C3", smap, "named_target"),
            "C3_det": load_pointwise(m, "C3", smap, "has_defect"),
            "AFC": load_afc(m, smap),
        }

    # ---- headline table (pooled per defect) ----
    lines = ["# E8 internal-口径 roster — G3/G5 format-suppression re-run\n",
             "Headline metric = **NAMED attribution** (did the model surface *this* defect). "
             "C0 = open-ended pointwise (suppressed); C3 = atomic targeted; AFC = 2-AFC strict "
             "(defective called worse in both orders). Internal contrast 口径 (one element vs its "
             "aligned/coloured siblings — decidable from the slide alone).\n",
             "## Per-model recovery (pooled over strata)\n",
             "| Model | Defect | C0 named | C3 named | ΔC3−C0 | AFC strict (n) |",
             "|---|---|---|---|---|---|"]
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    for m in models:
        for d in DEFECTS:
            c0 = (data[m]["C0_named"] or {}).get((d, "all"))
            c3 = (data[m]["C3_named"] or {}).get((d, "all"))
            afc = (data[m]["AFC"] or {}).get((d, "all"))
            delta = f"{c3['bal_acc']-c0['bal_acc']:+.2f}" if (c0 and c3) else "—"
            afcs = f"{afc['afc_strict']:.2f} (n={afc['n_pairs']})" if afc else "—"
            lines.append(f"| {m} | {SHORT[d]} | {fmt_cell(c0)} | {fmt_cell(c3)} | {delta} | {afcs} |")
            if c0:
                agg[d]["C0"].append(c0["bal_acc"])
            if c3:
                agg[d]["C3"].append(c3["bal_acc"])
            if afc:
                agg[d]["AFC"].append(afc["afc_strict"])
    lines.append("\n## Roster mean (over models reporting the cell)\n")
    lines.append("| Defect | mean C0 named | mean C3 named | mean AFC strict | n models |")
    lines.append("|---|---|---|---|---|")
    for d in DEFECTS:
        c0s, c3s, afcs = agg[d]["C0"], agg[d]["C3"], agg[d]["AFC"]
        mc0 = f"{sum(c0s)/len(c0s):.2f}" if c0s else "—"
        mc3 = f"{sum(c3s)/len(c3s):.2f}" if c3s else "—"
        ma = f"{sum(afcs)/len(afcs):.2f}" if afcs else "—"
        lines.append(f"| {SHORT[d]} | {mc0} | {mc3} | {ma} | {len(c0s)} |")

    # ---- per-stratum threshold table (roster mean of C3 named bal-acc) ----
    lines.append("\n## Clean-magnitude threshold — roster-mean C3 named bal-acc by stratum\n")
    lines.append("| Defect | stratum | mean C0 | mean C3 | mean AFC | n models |")
    lines.append("|---|---|---|---|---|---|")
    strata = STRATA
    for d in DEFECTS:
        for s in strata[d]:
            c0v, c3v, afcv = [], [], []
            for m in models:
                c0 = (data[m]["C0_named"] or {}).get((d, s))
                c3 = (data[m]["C3_named"] or {}).get((d, s))
                afc = (data[m]["AFC"] or {}).get((d, s))
                if c0:
                    c0v.append(c0["bal_acc"])
                if c3:
                    c3v.append(c3["bal_acc"])
                if afc:
                    afcv.append(afc["afc_strict"])
            f = lambda v: f"{sum(v)/len(v):.2f}" if v else "—"
            unit = "px" if d.startswith("G3") else "ΔE"
            lines.append(f"| {SHORT[d]} | {s:g}{unit} | {f(c0v)} | {f(c3v)} | {f(afcv)} | {len(c3v)} |")

    md = "\n".join(lines) + "\n"
    Path(REPO / args.md).write_text(md, encoding="utf-8")
    Path(REPO / args.json).write_text(
        json.dumps({m: {k: {f"{d}|{s}": v for (d, s), v in (cells or {}).items()}
                        for k, cells in md_.items()} for m, md_ in data.items()},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(md)
    print(f"[wrote {args.md} and {args.json}] models={models}")


if __name__ == "__main__":
    main()
