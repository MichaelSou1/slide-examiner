"""Part 2 examiner evaluation harness.

Scores a served OpenAI-compatible VLM on the Part 2 held-out manifests with the
Part 1 methodology: **balanced accuracy + paired clean** (never recall alone),
plus precision/recall/F1/FPR, and 2-AFC accuracy for the pairwise track.

Two prompt styles so each model is judged at its intended inference format:
  * ``trained``  — bare contract prompt folded exactly as the SFT input (no
                   scope/schema suffix). Use for the finetuned examiner.
  * ``scoped``   — contract prompt + per-task scope/schema reminder (the
                   zero-shot probe format from run_pilot). Use for zero-shot
                   baselines that need the schema spelled out.

Modes:
  pointwise  — probe each sampled positive on its defective image AND its paired
               clean image; score detection per defect with paired-clean control.
  pairwise   — 2-AFC forced choice over (clean, defective) in both orders for the
               overflow / image-text tracks (G1 / S6).

Usage:
  python scripts/part2_eval.py pointwise --manifest data/part2/manifest_eval_test_rendered.jsonl \
    --base-url http://localhost:8101/v1 --model ft-8b --prompt-style trained \
    --modalities A C --max-per-defect 80 --out runs/probe/part2_eval_ft_test.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.adapters import JSON_RETRY_INSTRUCTION, parse_examiner_json
from slide_examiner.examiner_contract import (
    build_messages_from_sample,
    image_content_from_path,
    normalize_modality,
)
from slide_examiner.schemas import ManifestSample

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO / "scripts"))
from run_pilot import build_cell_messages  # scoped prompt builder (run_pilot)

GEOMETRY = {"G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET", "G4_FONT_SIZE_INCONSISTENCY",
            "G5_BRAND_COLOR_VIOLATION", "G6_MARGIN_VIOLATION"}
PAIRWISE = {"G1_TEXT_OVERFLOW", "S6_IMAGE_TEXT_CONTRADICTION"}


def is_deck(rec: dict) -> bool:
    return bool(rec.get("deck"))


def defect_of(rec: dict) -> str:
    labs = [x.get("type") for x in rec.get("labels", [])]
    return labs[0] if labs else "NO_DEFECT"


def fold_trained(messages: list[dict]) -> list[dict]:
    """Fold contract [system,user] into a single user message preserving order
    (system text, image(s), body text) — matches the SFT input layout."""
    content: list[dict] = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, str):
            if c.strip():
                content.append({"type": "text", "text": c})
        else:
            content.extend(c)
    return [{"role": "user", "content": content}]


def clean_variant(rec: dict) -> dict | None:
    """A copy of the sample pointing at the paired clean image, with labels
    cleared (the negative control)."""
    pair = rec.get("pair") or {}
    clean_img = pair.get("clean_image_path") or rec.get("metadata", {}).get("clean_image_path")
    if not clean_img:
        return None
    if not Path(clean_img if Path(clean_img).is_absolute() else REPO / clean_img).exists():
        return None
    out = json.loads(json.dumps(rec))
    out["sample_id"] = rec["sample_id"] + "__CLEAN"
    out["image_path"] = clean_img
    out["labels"] = []
    out.setdefault("metadata", {})["defective_image_path"] = clean_img
    # clean deck: point page images at clean renders if present
    return out


def build_messages(rec: dict, modality: str, style: str) -> list[dict]:
    if style == "scoped":
        return build_cell_messages(rec, modality, "T1")
    msgs = build_messages_from_sample(rec, modality=modality)
    return fold_trained(msgs)


def call(client, model, messages, max_tokens):
    resp = client.chat.completions.create(model=model, messages=messages,
                                          max_tokens=max_tokens, temperature=0.0)
    return resp.choices[0].message.content or "{}"


def predicted_types(output: dict | None) -> set[str]:
    if not output:
        return set()
    out = set()
    for f in output.get("findings", []) or []:
        t = f.get("type")
        if t:
            out.add(t)
    return out


def probe_one(client, model, rec, modality, style, max_tokens):
    messages = build_messages(rec, modality, style)
    for attempt in range(2):
        try:
            raw = call(client, model, messages, max_tokens)
        except Exception as exc:
            return {"sample_id": rec["sample_id"], "error": str(exc)[:200], "predicted": [], "failure": True}
        try:
            parsed = parse_examiner_json(raw)
            return {"sample_id": rec["sample_id"], "predicted": sorted(predicted_types(parsed)),
                    "expected": [x["type"] for x in rec.get("labels", []) if x.get("type") != "NO_DEFECT"],
                    "level": "deck" if is_deck(rec) else "page", "raw": raw[:400]}
        except ValueError:
            messages = messages + [{"role": "user", "content": JSON_RETRY_INSTRUCTION}]
    return {"sample_id": rec["sample_id"], "predicted": [],
            "expected": [x["type"] for x in rec.get("labels", []) if x.get("type") != "NO_DEFECT"],
            "level": "deck" if is_deck(rec) else "page", "failure": True, "raw": raw[:400]}


def run_pointwise(args):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    # subsample positives per defect for tractability
    bydef = collections.defaultdict(list)
    for r in recs:
        bydef[defect_of(r)].append(r)
    only = set(args.only_defects or [])
    pos: list[dict] = []
    for d, rs in bydef.items():
        if d == "NO_DEFECT":
            continue
        if only and d not in only:
            continue
        if args.deck_only and not any(is_deck(r) for r in rs):
            continue
        pos.extend(rs[: args.max_per_defect])
    if args.deck_only:
        pos = [r for r in pos if is_deck(r)]
    # build clean controls (page-level: same-base clean image)
    cleans = [c for r in pos if (c := clean_variant(r))]
    # deck-level paired-clean controls (S2/S5): pre-rendered clean decks keyed by
    # `<defective_id>__CLEAN`; only attach controls whose positive is in `pos`.
    if args.deck_clean and Path(args.deck_clean).exists():
        pos_ids = {r["sample_id"] for r in pos}
        deck_controls = [json.loads(l) for l in Path(args.deck_clean).open() if l.strip()]
        attached = [c for c in deck_controls
                    if c["sample_id"].removesuffix("__CLEAN") in pos_ids]
        cleans.extend(attached)
        print(f"  + {len(attached)} deck clean controls from {args.deck_clean}")

    jobs = []
    for r in pos:
        for m in args.modalities:
            jobs.append((r, m))
    for c in cleans:
        for m in args.modalities:
            jobs.append((c, m))

    print(f"[{args.model}/{args.prompt_style}] {len(pos)} pos + {len(cleans)} clean x {len(args.modalities)} mod = {len(jobs)} probes")
    out_rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(probe_one, client, args.model, r, m, args.prompt_style, args.max_tokens): (r["sample_id"], m)
                for (r, m) in jobs}
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            row["modality"] = futs[fut][1]
            row["is_clean"] = row["sample_id"].endswith("__CLEAN")
            out_rows.append(row)
            done += 1
            if done % 100 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} {time.time()-t0:.0f}s")

    metrics = score_pointwise(out_rows, args.modalities)
    result = {"model": args.model, "prompt_style": args.prompt_style, "manifest": args.manifest,
              "modalities": args.modalities, "n_pos": len(pos), "n_clean": len(cleans),
              "failures": sum(1 for r in out_rows if r.get("failure")), "metrics": metrics}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def score_pointwise(rows, modalities):
    metrics = {}
    defects = sorted({d for r in rows if not r["is_clean"] for d in r["expected"]})
    for mod in modalities:
        mrows = [r for r in rows if r["modality"] == mod]
        per_defect = {}
        for d in defects:
            lvl = "deck" if d in {"S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"} else "page"
            posr = [r for r in mrows if not r["is_clean"] and d in r["expected"]]
            negr = [r for r in mrows if r["is_clean"] and r["level"] == lvl]
            if not posr or not negr:
                continue
            tp = sum(d in r["predicted"] for r in posr)
            fn = len(posr) - tp
            fp = sum(d in r["predicted"] for r in negr)
            tn = len(negr) - fp
            recall = tp / len(posr)
            spec = tn / len(negr)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            per_defect[d] = {"recall": round(recall, 3), "specificity": round(spec, 3),
                             "bal_acc": round((recall + spec) / 2, 3), "precision": round(precision, 3),
                             "f1": round(f1, 3), "fpr": round(1 - spec, 3),
                             "n_pos": len(posr), "n_neg": len(negr)}
        # grouped means
        def group_mean(keys):
            vals = [per_defect[d]["bal_acc"] for d in keys if d in per_defect]
            return round(sum(vals) / len(vals), 3) if vals else None
        metrics[mod] = {
            "per_defect": per_defect,
            "group_bal_acc": {
                "semantic": group_mean(["S1_TITLE_BODY_MISMATCH", "S4_DENSITY_RULE_VIOLATION",
                                        "S2_NARRATIVE_ORDER_BREAK", "S5_MISSING_LOGIC_SECTION"]),
                "geometry": group_mean(sorted(GEOMETRY)),
            },
        }
    return metrics


# ---------------- pairwise 2-AFC ----------------

PAIR_INSTRUCTION = (
    "Compare slide candidate A and candidate B. Decide which is better for "
    "presentation quality (text fit, image-text consistency). Output ONLY "
    "PairwiseResult JSON with fields level, subject_id, better (A|B|tie), reason."
)
PAIR_SCOPED = (
    "You are shown two renderings of the same slide: candidate A then candidate B. "
    "Exactly one may contain a defect ({defect}). Which candidate is BETTER (defect-free)? "
    'Output ONLY JSON: {{"better": "A"|"B"|"tie"}}.'
)


def parse_better(raw: str) -> str | None:
    try:
        d = parse_examiner_json(raw)
    except Exception:
        return None
    b = str(d.get("better", "")).strip().lower()
    if b in ("a", "b", "tie"):
        return b
    return None


def run_pairwise(args):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    pairs = []
    for r in recs:
        d = defect_of(r)
        if d not in PAIRWISE:
            continue
        pair = r.get("pair") or {}
        clean = pair.get("clean_image_path") or r.get("metadata", {}).get("clean_image_path")
        defective = r.get("image_path") or r.get("metadata", {}).get("defective_image_path")
        def ok(p):
            return p and Path(p if Path(p).is_absolute() else REPO / p).exists()
        if ok(clean) and ok(defective):
            pairs.append((d, clean, defective, r))
    by = collections.defaultdict(list)
    for p in pairs:
        by[p[0]].append(p)
    sel = []
    for d, ps in by.items():
        sel.extend(ps[: args.max_per_defect])
    print(f"[{args.model}/{args.prompt_style}] pairwise {len(sel)} pairs x2 orders")

    def one(d, clean, defective, order):
        # order 0: A=clean B=defective (expect better=A); order 1: A=defective B=clean (expect better=B)
        a_img, b_img = (clean, defective) if order == 0 else (defective, clean)
        expect = "a" if order == 0 else "b"
        instr = PAIR_INSTRUCTION if args.prompt_style == "trained" else PAIR_SCOPED.format(defect=d)
        content = [image_content_from_path(a_img), image_content_from_path(b_img), {"type": "text", "text": instr}]
        for attempt in range(2):
            try:
                raw = call(client, args.model, [{"role": "user", "content": content}], 256)
            except Exception as exc:
                return {"defect": d, "order": order, "pick": None, "expect": expect, "err": str(exc)[:120]}
            pick = parse_better(raw)
            if pick:
                return {"defect": d, "order": order, "pick": pick, "expect": expect, "correct": pick == expect}
            content = content + [{"type": "text", "text": JSON_RETRY_INSTRUCTION}] if False else content
        return {"defect": d, "order": order, "pick": None, "expect": expect, "correct": False}

    jobs = []
    for (d, clean, defective, r) in sel:
        jobs.append((d, clean, defective, 0))
        jobs.append((d, clean, defective, 1))
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(one, d, c, df, o) for (d, c, df, o) in jobs]
        for fut in as_completed(futs):
            rows.append(fut.result())

    metrics = {}
    for d in by:
        drows = [r for r in rows if r["defect"] == d and r.get("pick")]
        if not drows:
            metrics[d] = {"acc": None, "n": 0}
            continue
        acc = sum(r["correct"] for r in drows) / len(drows)
        picks = collections.Counter(r["pick"] for r in drows)
        metrics[d] = {"acc_2afc": round(acc, 3), "n": len(drows),
                      "pick_dist": dict(picks), "no_parse": sum(1 for r in rows if r["defect"] == d and not r.get("pick"))}
    result = {"model": args.model, "prompt_style": args.prompt_style, "mode": "pairwise_2afc",
              "manifest": args.manifest, "metrics": metrics}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["pointwise", "pairwise"])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--base-url", default="http://localhost:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt-style", choices=["trained", "scoped"], default="trained")
    ap.add_argument("--modalities", nargs="+", default=["A", "C"])
    ap.add_argument("--max-per-defect", type=int, default=80)
    ap.add_argument("--max-tokens", type=int, default=640)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None)
    ap.add_argument("--deck-clean", default=None,
                    help="JSONL of pre-rendered deck-level clean controls "
                         "(part2_render_clean_decks.py output); enables S2/S5 deck cells.")
    ap.add_argument("--deck-only", action="store_true",
                    help="Probe only deck-scope positives (+ their deck clean controls).")
    ap.add_argument("--only-defects", nargs="+", default=None,
                    help="Restrict positives to these defect types (e.g. S1/S4 for robustness).")
    args = ap.parse_args()
    if args.mode == "pointwise":
        run_pointwise(args)
    else:
        run_pairwise(args)


if __name__ == "__main__":
    main()
