"""Part 3 Protocol-2 — hybrid critic on REAL data (SlideAudit), honest scoping (A.5).

SlideAudit (UIST'25) is third-party, human-annotated, and **image-only — it ships
no element structure (IR)**. So the hybrid's two structural engines cannot run:

  * the **symbolic linter** needs declared bboxes -> N/A on bare images;
  * the **text LLM** needs the slide's text/IR -> N/A without OCR.

On real image-only data the hybrid therefore **degrades to its VLM engine** — this
is stated, not hidden, and it is the central real-data scoping caveat: the full
symbolic-neural critic needs native ``.pptx``/IR; on bare pixels only the VLM path
is available.

What we CAN test on real data is whether the Protocol-1 finding transfers: does
the VLM engine's **atomic-binary elicitation (C3)** recover real defect detection
that the whole-taxonomy pointwise call (C0) suppresses? We measure per
SlideAudit-canonical class, with class-present positives and class-
``confident_absent`` negatives (the same strong-agreement protocol as Part-2
Table 4), at paired balanced accuracy + precision.

Usage (after serving a capable VLM):
  python scripts/part3_p2_slideaudit.py --base-url http://127.0.0.1:8101/v1 \
     --model qwen35-27b --out data/part3/p2_slideaudit.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from slide_examiner.hybrid_critic import linter_types  # noqa: E402
from part3_elicit import _blank_result, _cell, ENGINES  # noqa: E402

# SlideAudit-labelled classes (their geometry + density subset).
SA_CLASSES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
              "G4_FONT_SIZE_INCONSISTENCY", "G5_BRAND_COLOR_VIOLATION",
              "G6_MARGIN_VIOLATION", "S4_DENSITY_RULE_VIOLATION"]


def img_ok(p):
    return p and Path(p if Path(p).is_absolute() else REPO / p).exists()


def build_class(recs, d, max_n):
    """positives = label d present; negatives = d in confident_absent."""
    pos, neg = [], []
    for r in recs:
        if not img_ok(r.get("image_path")):
            continue
        labs = {x["type"] for x in r.get("labels", [])}
        absent = set(r.get("metadata", {}).get("confident_absent", []))
        if d in labs:
            pos.append(r)
        elif d in absent and d not in labs:
            neg.append(r)
    return pos[:max_n], neg[:max_n]


def run_cell(client, model, pos, neg, d, condition, modality, style, max_tokens, workers):
    jobs = [(r, False) for r in pos] + [(r, True) for r in neg]

    def work(rec, is_clean):
        res = ENGINES[condition](client, model, rec, modality, d, style, max_tokens)
        res["is_clean"] = is_clean
        return res

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(work, r, c) for (r, c) in jobs]
        for f in as_completed(futs):
            rows.append(f.result())
    rows = [r for r in rows if not r.get("failure")]
    p = [r for r in rows if not r["is_clean"]]
    n = [r for r in rows if r["is_clean"]]
    if not p or not n:
        return None
    key = "named_target" if condition != "C0" else "named_target"
    return _cell(p, n, key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--style", default="scoped")
    ap.add_argument("--manifest", default="data/part2/manifest_slideaudit.jsonl")
    ap.add_argument("--modality", default="A")
    ap.add_argument("--max-per-defect", type=int, default=40)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--conds", nargs="+", default=["C0", "C3"])
    ap.add_argument("--classes", nargs="+", default=None,
                    help="subset of SA_CLASSES to run (for sharding across servers)")
    ap.add_argument("--out", default="data/part3/p2_slideaudit.json")
    args = ap.parse_args()
    sa_classes = args.classes or SA_CLASSES

    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
                    base_url=args.base_url, timeout=120.0, max_retries=1)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]

    # linter on real data: structure-free -> cannot run. Confirm + record.
    n_with_ir = sum(1 for r in recs if r.get("slide"))
    linter_note = (f"linter N/A on SlideAudit: {n_with_ir}/{len(recs)} records carry "
                   f"element structure (IR). image-only -> symbolic linter + text-LLM "
                   f"cannot run; hybrid degrades to its VLM engine.")
    print(linter_note, flush=True)

    per_class = {}
    t0 = time.time()
    for d in sa_classes:
        pos, neg = build_class(recs, d, args.max_per_defect)
        if len(pos) < 8 or len(neg) < 8:
            print(f"  skip {d}: pos={len(pos)} neg={len(neg)}", flush=True)
            continue
        cell = {"n_pos": len(pos), "n_neg": len(neg)}
        for cond in args.conds:
            cell[cond] = run_cell(client, args.model, pos, neg, d, cond,
                                  args.modality, args.style, args.max_tokens, args.workers)
        per_class[d] = cell
        c0 = cell.get("C0", {}) or {}
        c3 = cell.get("C3", {}) or {}
        print(f"  {d:32s} C0={c0.get('bal_acc')} C3={c3.get('bal_acc')} "
              f"(pos={len(pos)} neg={len(neg)}, {time.time()-t0:.0f}s)", flush=True)

    out = {"model": args.model, "manifest": args.manifest, "modality": args.modality,
           "metric": "paired (present vs confident_absent) named balanced accuracy + precision",
           "linter_status": "N/A (image-only, no IR)", "linter_note": linter_note,
           "per_class": per_class}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
