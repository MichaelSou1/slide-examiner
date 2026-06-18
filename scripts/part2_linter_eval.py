"""Part 2 — symbolic baselines on the SAME held-out eval set as the VLM examiner.

  * G1-G6 geometry: `lint_slide` over each eval positive (defective slide) and its
    paired clean slide -> recall / specificity / balanced accuracy / FPR.
  * S3 terminology: `lint_deck` (term-consistency module) over S3 eval decks.

This is the linter column for the Part 2 head-to-head (finetuned-8B vs zero-shot
vs linter). Mirrors the Part 1 conclusion that G2-G6 belong to the linter and S3
belongs to the term-consistency module — re-measured on the Part 2 eval split.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from slide_examiner.geometry import lint_slide
from slide_examiner.schemas import Slide
from slide_examiner.ingest import load_slide_json
from slide_examiner.term_consistency import lint_deck

REPO = Path(__file__).resolve().parents[1]
G_TYPES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
           "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"]


def defect_of(r):
    return r["labels"][0]["type"] if r.get("labels") else "NO_DEFECT"


def _clean_slide(rec):
    p = (rec.get("pair") or {}).get("clean_slide_path") or rec.get("metadata", {}).get("clean_slide_path")
    if not p:
        return None
    p = p if Path(p).is_absolute() else REPO / p
    if not Path(p).exists():
        return None
    try:
        return load_slide_json(p)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", nargs="+", required=True)
    ap.add_argument("--out", default="runs/probe/part2_linter_eval.json")
    args = ap.parse_args()

    recs = []
    for m in args.manifests:
        recs += [json.loads(l) for l in Path(m).open() if l.strip()]

    # geometry: per type tp/fn on defectives, fp/tn on paired clean
    stat = {t: {"tp": 0, "pos": 0, "fp": 0, "neg": 0} for t in G_TYPES}
    for rec in recs:
        d = defect_of(rec)
        if d not in G_TYPES:
            continue
        try:
            defective = Slide.from_mapping(rec["slide"])
        except Exception:
            continue
        det = {x.type for x in lint_slide(defective)}
        stat[d]["pos"] += 1
        stat[d]["tp"] += int(d in det)
        clean = _clean_slide(rec)
        if clean is not None:
            cdet = {x.type for x in lint_slide(clean)}
            stat[d]["neg"] += 1
            stat[d]["fp"] += int(d in cdet)

    geometry = {}
    for t in G_TYPES:
        s = stat[t]
        if not s["pos"]:
            continue
        recall = s["tp"] / s["pos"]
        spec = (1 - s["fp"] / s["neg"]) if s["neg"] else None
        geometry[t] = {
            "recall": round(recall, 3),
            "specificity": round(spec, 3) if spec is not None else None,
            "bal_acc": round((recall + spec) / 2, 3) if spec is not None else None,
            "fpr": round(s["fp"] / s["neg"], 3) if s["neg"] else None,
            "n_pos": s["pos"], "n_neg": s["neg"],
        }

    # S3 terminology via term-consistency module (deck-level)
    s3 = {"tp": 0, "pos": 0, "fp": 0, "neg": 0}
    seen_decks = set()
    for rec in recs:
        if defect_of(rec) != "S3_TERMINOLOGY_INCONSISTENCY":
            continue
        deck = rec.get("deck")
        if not deck:
            continue
        from slide_examiner.schemas import Deck
        try:
            d_def = Deck.from_mapping(deck)
        except Exception:
            continue
        findings = lint_deck(d_def)
        s3["pos"] += 1
        s3["tp"] += int(bool(findings))
    s3_metrics = {"recall": round(s3["tp"] / s3["pos"], 3) if s3["pos"] else None, "n_pos": s3["pos"]}

    result = {"geometry": geometry, "s3_terminology": s3_metrics,
              "manifests": args.manifests}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
