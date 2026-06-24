"""Part 3 E5 — open-world hybrid: linter on structure recovered from pixels.

Answers R3-W1 / EIC-W1: the routed hybrid's symbolic linter needs the native IR a
``.pptx`` carries; third-party decks exported to PDF/PNG ship none, so on bare
pixels the critic degrades to its VLM engine. This experiment **recovers** element
structure from the rendered pixels with a document-layout detector
(PP-DocLayoutV2), feeds the recovered boxes to the *same* geometry linter, and
asks how much coverage survives.

Two testbeds:

  * **synthetic real-layout** (``manifest_real_rendered.jsonl``): carries BOTH the
    ground-truth IR and the LibreOffice render, so we get the full three-way
    coverage ladder — native-IR linter (upper bound) vs pixel-recovered linter vs
    VLM-only floor — on the *same* slides, plus a recovery-fidelity (box IoU) figure
    against the GT IR.
  * **image-only SlideAudit** (third-party, no IR): the genuine open-world case —
    recovered-linter coverage vs the VLM-only floor; no native-IR or IoU possible.

Scoring is paired balanced accuracy with Wilson CIs at the linter's shipped
operating point (``min_iou=0.05``, ``margin_px=32``), and an exact paired McNemar
recovered-vs-native on per-item correctness.

Usage:
  CUDA_VISIBLE_DEVICES=1 python scripts/part3_e5_recovered.py \
      --mode synthetic --manifest data/part3/manifest_real_rendered.jsonl \
      --out data/part3/e5_recovered_synth.json
  CUDA_VISIBLE_DEVICES=1 python scripts/part3_e5_recovered.py \
      --mode slideaudit --manifest data/part2/manifest_slideaudit.jsonl \
      --out data/part3/e5_recovered_slideaudit.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from slide_examiner.geometry import lint_slide  # noqa: E402
from slide_examiner.schemas import Slide  # noqa: E402
from slide_examiner.statistics import balanced_accuracy_ci, wilson_interval  # noqa: E402
from slide_examiner.structure_recovery import (  # noqa: E402
    DEFAULT_MODEL, DetectionCache, LayoutDetector, normalize_gt_slide,
    recover_slide, recovery_fidelity,
)

# geometry classes the linter can in principle own (S3/term is deck-level, excluded)
GEO_CLASSES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
               "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]


def abspath(p: str) -> str:
    return p if Path(p).is_absolute() else str(REPO / p)


def lint_types(slide_dict: dict, *, min_iou: float, margin_px: float) -> set[str]:
    """Detected defect-type strings for one slide dict at a given operating point."""
    try:
        slide = Slide.from_mapping(slide_dict)
    except Exception:  # noqa: BLE001
        return set()
    return {x.type for x in lint_slide(slide, min_iou=min_iou, margin_px=margin_px)}


def exact_mcnemar(corr_x: dict, corr_y: dict) -> dict:
    """Exact two-sided paired McNemar over shared keys. gain = x-wrong & y-right."""
    shared = set(corr_x) & set(corr_y)
    b = sum(1 for s in shared if (not corr_x[s]) and corr_y[s])
    c = sum(1 for s in shared if corr_x[s] and (not corr_y[s]))
    n = b + c
    if n == 0:
        return {"p": 1.0, "gain_y": b, "loss_y": c, "n_discordant": 0}
    k = min(b, c)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) * (0.5 ** n))
    return {"p": round(p, 5), "gain_y": b, "loss_y": c, "n_discordant": n}


def cell_from_counts(tp: int, n_pos: int, tn: int, n_neg: int) -> dict:
    bacc = balanced_accuracy_ci(tp, n_pos, tn, n_neg)
    rec = wilson_interval(tp, n_pos)
    fp = n_neg - tn
    spec = wilson_interval(tn, n_neg)
    return {
        "bal_acc": round(bacc.estimate, 3), "bal_acc_ci": [round(bacc.low, 3), round(bacc.high, 3)],
        "recall": round(tp / n_pos, 3) if n_pos else None,
        "recall_ci": [round(rec.low, 3), round(rec.high, 3)],
        "specificity": round(tn / n_neg, 3) if n_neg else None,
        "specificity_ci": [round(spec.low, 3), round(spec.high, 3)],
        "fpr": round(fp / n_neg, 3) if n_neg else None,
        "tp": tp, "fp": fp, "fn": n_pos - tp, "tn": tn, "n_pos": n_pos, "n_neg": n_neg,
    }


# --------------------------------------------------------------------------- #
# Synthetic real-layout: native-IR vs recovered vs VLM + recovery IoU
# --------------------------------------------------------------------------- #
def run_synthetic(args, detector, cache):
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    if args.max_per_class:
        seen: dict = {}
        keep = []
        for r in recs:
            d = r["defect"]
            if seen.get(d, 0) < args.max_per_class:
                seen[d] = seen.get(d, 0) + 1
                keep.append(r)
        recs = keep

    # VLM-only (modality A) floor on the SAME slides, from the pc_real run.
    vlm_floor = {}
    if args.vlm_floor and Path(args.vlm_floor).exists():
        vf = json.load(open(args.vlm_floor))
        for cls, c in vf.get("per_modality", {}).get("A", {}).get("per_class", {}).items():
            vlm_floor[cls] = {"bal_acc": c["bal_acc"], "bal_acc_ci": c.get("bal_acc_ci"),
                              "n_pos": c.get("n_pos"), "n_neg": c.get("n_neg")}

    # accumulate per-class correctness maps for native + recovered
    per_class: dict = {c: {"n": 0,
                           "native": {"tp": 0, "tn": 0, "np": 0, "nn": 0},
                           "recov": {"tp": 0, "tn": 0, "np": 0, "nn": 0},
                           "corr_native": {}, "corr_recov": {},
                           "fid": []}
                       for c in GEO_CLASSES}

    t0 = time.time()
    for i, r in enumerate(recs):
        d = r["defect"]
        if d not in per_class:
            continue
        def_img = abspath(r["pair"]["defective_image_path"])
        cln_img = abspath(r["pair"]["clean_image_path"])
        if not (Path(def_img).exists() and Path(cln_img).exists()):
            continue
        pc = per_class[d]
        pc["n"] += 1
        sid = r["sample_id"]

        # native-IR linter on GT def / clean
        nat_def = d in lint_types(r["slide"], min_iou=args.min_iou, margin_px=args.margin_px)
        nat_cln = d in lint_types(r["clean_slide"], min_iou=args.min_iou, margin_px=args.margin_px)
        pc["native"]["tp"] += int(nat_def); pc["native"]["np"] += 1
        pc["native"]["tn"] += int(not nat_cln); pc["native"]["nn"] += 1
        pc["corr_native"][sid] = nat_def          # defective: correct iff fired
        pc["corr_native"][sid + "__C"] = (not nat_cln)  # clean: correct iff NOT fired

        # recovered-structure linter on detector output for def / clean image
        det_def = cache.get_or_compute(detector, def_img)
        det_cln = cache.get_or_compute(detector, cln_img)
        rec_def = recover_slide(det_def)
        rec_cln = recover_slide(det_cln)
        rcv_def = d in lint_types(rec_def, min_iou=args.min_iou, margin_px=args.margin_px)
        rcv_cln = d in lint_types(rec_cln, min_iou=args.min_iou, margin_px=args.margin_px)
        pc["recov"]["tp"] += int(rcv_def); pc["recov"]["np"] += 1
        pc["recov"]["tn"] += int(not rcv_cln); pc["recov"]["nn"] += 1
        pc["corr_recov"][sid] = rcv_def
        pc["corr_recov"][sid + "__C"] = (not rcv_cln)

        # recovery fidelity vs GT IR (on the defective render)
        gt_norm = normalize_gt_slide(r["slide"])
        pc["fid"].append(recovery_fidelity(rec_def, gt_norm))

        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(recs)} {time.time()-t0:.0f}s", flush=True)

    out_classes = {}
    for c in GEO_CLASSES:
        pc = per_class[c]
        if pc["n"] == 0:
            continue
        nat = cell_from_counts(pc["native"]["tp"], pc["native"]["np"],
                               pc["native"]["tn"], pc["native"]["nn"])
        rcv = cell_from_counts(pc["recov"]["tp"], pc["recov"]["np"],
                               pc["recov"]["tn"], pc["recov"]["nn"])
        mc = exact_mcnemar(pc["corr_native"], pc["corr_recov"])  # gain_y = recovered gains
        fids = pc["fid"]
        fid_summary = None
        if fids:
            import statistics as st
            fid_summary = {
                "mean_iou_matched": round(st.mean(f["mean_iou_matched"] for f in fids), 3),
                "recall_at_iou": round(st.mean(f["recall_at_iou"] for f in fids), 3),
                "precision_at_iou": round(st.mean(f["precision_at_iou"] for f in fids), 3),
                "mean_n_gt": round(st.mean(f["n_gt"] for f in fids), 2),
                "mean_n_rec": round(st.mean(f["n_rec"] for f in fids), 2),
            }
        out_classes[c] = {"n": pc["n"], "native_ir": nat, "recovered": rcv,
                          "vlm_only_A": vlm_floor.get(c),
                          "mcnemar_recov_vs_native": mc,
                          "recovery_fidelity": fid_summary}

    return {
        "mode": "synthetic", "manifest": args.manifest, "model_id": args.model_id,
        "operating_point": {"min_iou": args.min_iou, "margin_px": args.margin_px,
                            "score_thr": args.score_thr, "nms_iou": args.nms_iou,
                            "norm_width": 960},
        "vlm_floor_source": args.vlm_floor,
        "per_class": out_classes,
    }


# --------------------------------------------------------------------------- #
# Image-only SlideAudit: recovered-linter coverage vs VLM floor
# --------------------------------------------------------------------------- #
def run_slideaudit(args, detector, cache):
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]

    def img_ok(p):
        return p and Path(abspath(p)).exists()

    # VLM floor from existing p2_slideaudit run
    vlm_floor = {}
    if args.vlm_floor and Path(args.vlm_floor).exists():
        vf = json.load(open(args.vlm_floor))
        for cls, cell in vf.get("per_class", {}).items():
            vlm_floor[cls] = {"C0": (cell.get("C0") or {}).get("bal_acc"),
                              "C3": (cell.get("C3") or {}).get("bal_acc")}

    out_classes = {}
    t0 = time.time()
    classes = args.classes or GEO_CLASSES
    for c in classes:
        pos, neg = [], []
        for r in recs:
            if not img_ok(r.get("image_path")):
                continue
            labs = {x["type"] for x in r.get("labels", [])}
            absent = set(r.get("metadata", {}).get("confident_absent", []))
            if c in labs:
                pos.append(r)
            elif c in absent and c not in labs:
                neg.append(r)
        pos, neg = pos[:args.max_per_class or len(pos)], neg[:args.max_per_class or len(neg)]
        if len(pos) < 8 or len(neg) < 8:
            print(f"  skip {c}: pos={len(pos)} neg={len(neg)}", flush=True)
            continue
        tp = tn = 0
        for r in pos:
            det = cache.get_or_compute(detector, abspath(r["image_path"]))
            fired = c in lint_types(recover_slide(det), min_iou=args.min_iou, margin_px=args.margin_px)
            tp += int(fired)
        for r in neg:
            det = cache.get_or_compute(detector, abspath(r["image_path"]))
            fired = c in lint_types(recover_slide(det), min_iou=args.min_iou, margin_px=args.margin_px)
            tn += int(not fired)
        cell = cell_from_counts(tp, len(pos), tn, len(neg))
        out_classes[c] = {"recovered": cell, "vlm_only": vlm_floor.get(c)}
        print(f"  {c:28s} recov_balacc={cell['bal_acc']:.3f} "
              f"(recall={cell['recall']}, fpr={cell['fpr']}, n={len(pos)}+{len(neg)}) "
              f"VLM={vlm_floor.get(c)} [{time.time()-t0:.0f}s]", flush=True)

    return {
        "mode": "slideaudit", "manifest": args.manifest, "model_id": args.model_id,
        "operating_point": {"min_iou": args.min_iou, "margin_px": args.margin_px,
                            "score_thr": args.score_thr, "nms_iou": args.nms_iou,
                            "norm_width": 960},
        "vlm_floor_source": args.vlm_floor,
        "per_class": out_classes,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["synthetic", "slideaudit"], required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-id", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None)
    ap.add_argument("--cache", default="data/part3/e5_layout_cache.jsonl")
    ap.add_argument("--score-thr", type=float, default=0.4)
    ap.add_argument("--nms-iou", type=float, default=0.7)
    ap.add_argument("--min-iou", type=float, default=0.05, help="linter overlap IoU threshold")
    ap.add_argument("--margin-px", type=float, default=32.0)
    ap.add_argument("--max-per-class", type=int, default=0)
    ap.add_argument("--classes", nargs="+", default=None)
    ap.add_argument("--vlm-floor", default=None,
                    help="pc_real_*.json (synthetic) or p2_slideaudit.json (slideaudit)")
    args = ap.parse_args()

    detector = LayoutDetector(args.model_id, device=args.device,
                              score_thr=args.score_thr, nms_iou=args.nms_iou)
    cache = DetectionCache(args.cache)

    if args.mode == "synthetic":
        result = run_synthetic(args, detector, cache)
    else:
        result = run_slideaudit(args, detector, cache)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
