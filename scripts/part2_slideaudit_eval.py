"""SlideAudit real-data transfer eval (modality A, image-only).

Probes a served model on real SlideAudit slides and scores per mapped defect
using the dataset's own strong-agreement labels:
  positives = slides where the mapped defect is present (strong agreement)
  negatives = slides where it is confidently absent (strong agreement)
-> recall / specificity / balanced accuracy / FPR. No element structure exists in
SlideAudit, so only modality A (image) applies; the linter/B/C do not.

Prompt styles: 'trained' (bare contract, for the finetuned examiner) and 'scoped'
(schema/scope suffix, for zero-shot baselines) — same as part2_eval.
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from slide_examiner.adapters import JSON_RETRY_INSTRUCTION, parse_examiner_json
from slide_examiner.examiner_contract import (
    Modality, PageContext, PageExamRequest, RenderSpec, Scene,
    build_page_messages, PAGE_SCOPED_DEFECTS,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from run_pilot import cell_suffix  # scoped schema/scope reminder
from part2_eval import fold_trained, predicted_types, call

MAPPED = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
          "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION",
          "G6_MARGIN_VIOLATION", "S4_DENSITY_RULE_VIOLATION"]


def build_messages(img_path: str, style: str) -> list[dict]:
    with Image.open(img_path) as im:
        w, h = im.size
    b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
    req = PageExamRequest(
        page_id=Path(img_path).stem,
        render=RenderSpec(image_width_px=w, image_height_px=h, scale_x=1.0, scale_y=1.0, renderer="real"),
        image_png_base64=b64,
        elements=[],
        context=PageContext(scene=Scene.FULL_PROPOSAL, page_index=0, task_brief="real slide"),
        modality=Modality.A_IMAGE_ONLY,
    )
    msgs = build_page_messages(req)
    if style == "scoped":
        msgs[-1]["content"].append({"type": "text", "text": cell_suffix({}, "T1")})
        return msgs
    return fold_trained(msgs)


def probe(client, model, img_path, style, max_tokens):
    msgs = build_messages(img_path, style)
    for _ in range(2):
        try:
            raw = call(client, model, msgs, max_tokens)
        except Exception as e:
            return {"pred": set(), "fail": True, "err": str(e)[:120]}
        try:
            return {"pred": predicted_types(parse_examiner_json(raw))}
        except ValueError:
            msgs = msgs + [{"role": "user", "content": JSON_RETRY_INSTRUCTION}]
    return {"pred": set(), "fail": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/part2/manifest_slideaudit.jsonl")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt-style", choices=["trained", "scoped"], default="trained")
    ap.add_argument("--max-pos-per-defect", type=int, default=60)
    ap.add_argument("--max-slides", type=int, default=500)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    # select slides: positives per defect (capped) + negative-only pool, up to max-slides
    chosen, seen = [], set()
    by_def = collections.defaultdict(list)
    for r in recs:
        for lb in r["labels"]:
            if lb["type"] in MAPPED:
                by_def[lb["type"]].append(r)
    for d in MAPPED:
        for r in by_def[d][: args.max_pos_per_defect]:
            if r["sample_id"] not in seen:
                seen.add(r["sample_id"]); chosen.append(r)
    for r in recs:  # fill with negative-ish slides
        if len(chosen) >= args.max_slides:
            break
        if r["sample_id"] not in seen:
            seen.add(r["sample_id"]); chosen.append(r)
    chosen = chosen[: args.max_slides]

    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url)
    print(f"[{args.model}/{args.prompt_style}] probing {len(chosen)} real SlideAudit slides")
    preds = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(probe, client, args.model, r["image_path"], args.prompt_style, 640): r["sample_id"]
                for r in chosen}
        done = 0
        for fut in as_completed(futs):
            preds[futs[fut]] = fut.result()
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(chosen)} {time.time()-t0:.0f}s")

    rec_by_id = {r["sample_id"]: r for r in chosen}
    metrics = {}
    for d in MAPPED:
        tp = fn = fp = tn = 0
        for sid, p in preds.items():
            if p.get("fail"):
                continue
            r = rec_by_id[sid]
            present = any(lb["type"] == d for lb in r["labels"])
            absent = d in r["metadata"].get("confident_absent", [])
            if present:
                tp += int(d in p["pred"]); fn += int(d not in p["pred"])
            elif absent:
                fp += int(d in p["pred"]); tn += int(d not in p["pred"])
        npos, nneg = tp + fn, fp + tn
        if npos < 5 or nneg < 5:
            metrics[d] = {"n_pos": npos, "n_neg": nneg, "note": "insufficient"}
            continue
        recall = tp / npos; spec = tn / nneg
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = 2 * prec * recall / (prec + recall) if (prec + recall) else 0.0
        metrics[d] = {"recall": round(recall, 3), "specificity": round(spec, 3),
                      "bal_acc": round((recall + spec) / 2, 3), "precision": round(prec, 3),
                      "f1": round(f1, 3), "fpr": round(1 - spec, 3), "n_pos": npos, "n_neg": nneg}
    result = {"model": args.model, "prompt_style": args.prompt_style, "dataset": "SlideAudit (real)",
              "modality": "A", "n_probed": len(chosen),
              "failures": sum(1 for p in preds.values() if p.get("fail")), "metrics": metrics}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
