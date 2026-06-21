"""Part 3 Protocol-1 elicitation harness (A.4).

Generalizes ``playground/probe_toc.py`` into a 4-condition elicitation sweep over
the "rescuable" defect classes (G1 / S6 / G7). The science is **C3 vs C0**: same
model, same taxonomy, same image, the only difference is "ask the whole taxonomy
in one overloaded call" (C0) vs "ask one atomic binary per type with forced
localization" (C3, PresentBench-style).

Conditions:
  C0  pointwise + rubric + whole-taxonomy single call  (reuses part2_eval)
  C3  atomic per-type binary YES/NO + forced evidence   (this module)
  C1  free-form describe -> classify to taxonomy         (slide_examiner.elicit_freeform)
  C2  synth-twin pairwise (geometry-normalized counterfactual) (slide_examiner.elicit_pairwise)

Every per-sample result records BOTH a detection-level signal (``has_defect`` —
model asserts something is wrong) and a named-level signal (``named_target`` —
model names the *asked* defect type). Scoring then reports paired-clean
balanced-accuracy / recall / FPR / precision at each level with Wilson CIs.
  * G1 / S6 are in the frozen taxonomy -> the NAMED level is the headline.
  * G7 is our extension and absent from C0's taxonomy (C0 cannot emit the literal
    string) -> the DETECTION level is the headline for the C3-vs-C0 contrast.

Usage:
  python scripts/part3_elicit.py --condition C3 \
    --manifest data/part3/manifest_g7_rendered.jsonl \
    --base-url http://localhost:8101/v1 --model ft-8b --style trained \
    --defects G7_RENDER_CONTAINMENT_OVERFLOW --modalities A \
    --out data/part3/p1_ft8b_C3_g7.json
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

from slide_examiner.adapters import parse_examiner_json  # noqa: E402
from slide_examiner.elicit_common import chat_complete  # noqa: E402
from slide_examiner.defect_types import (  # noqa: E402
    G7_RENDER_CONTAINMENT_OVERFLOW,
    G7_SPEC,
    is_extension,
)
from slide_examiner.examiner_contract import image_content_from_path  # noqa: E402
from slide_examiner.statistics import balanced_accuracy_ci, wilson_interval  # noqa: E402
from slide_examiner.taxonomy import DEFECTS  # noqa: E402

# part2_eval gives us build_messages (trained|scoped), call, clean_variant, defect_of.
from part2_eval import build_messages, call, clean_variant, defect_of, is_deck  # noqa: E402

DECK_DEFECTS = {"S2_NARRATIVE_ORDER_BREAK", "S3_TERMINOLOGY_INCONSISTENCY", "S5_MISSING_LOGIC_SECTION"}


# --------------------------------------------------------------------------- #
# Per-type binary questions (C3 / used as the localization target by C1)
# --------------------------------------------------------------------------- #
_SPECIFIC_QUESTIONS = {
    "G1_TEXT_OVERFLOW": (
        "Does any text visibly overflow or get clipped by its text box — letters "
        "cut off at an edge, or a line running past the box boundary?"
    ),
    "S6_IMAGE_TEXT_CONTRADICTION": (
        "Does any chart, diagram, or image visibly contradict the text near it — "
        "e.g. the text states a trend, label, or number that the figure does not "
        "show?"
    ),
    G7_RENDER_CONTAINMENT_OVERFLOW: G7_SPEC.elicit_question,
}


def question_for(defect: str) -> str:
    if defect in _SPECIFIC_QUESTIONS:
        return _SPECIFIC_QUESTIONS[defect]
    spec = DEFECTS.get(defect)
    desc = spec.description if spec else defect.replace("_", " ").lower()
    return f"Does this slide visibly exhibit the following defect — {desc}?"


C3_SYSTEM = (
    "You are a meticulous slide-quality inspector. You will be asked about ONE "
    "specific possible defect. Look only at what is visibly rendered. Answer with "
    "a single JSON object and nothing else."
)

C3_SCHEMA_HINT = (
    'Answer strictly as JSON:\n'
    '{{"present": true|false, "evidence_element": "<concrete element/region you '
    'point to, or empty>", "evidence_region": "<top-left|top|top-right|left|'
    'center|right|bottom-left|bottom|bottom-right|empty>", "confidence": 0.0-1.0}}\n'
    'If present=true you MUST name a concrete evidence_element (e.g. "the title", '
    '"the right-hand card", "the bottom list item"). If you cannot point to '
    "concrete visible evidence, answer present=false."
)


# --------------------------------------------------------------------------- #
# Unified per-sample elicitation result
# --------------------------------------------------------------------------- #
def _blank_result(rec: dict, sample_id: str | None = None) -> dict:
    return {
        "sample_id": sample_id or rec["sample_id"],
        "has_defect": False,
        "named_target": False,
        "predicted_types": [],
        "locator": None,
        "confidence": None,
        "other": [],          # off-taxonomy free-form items (C1 only)
        "raw": "",
        "failure": False,
    }


# --------------------------------------------------------------------------- #
# C0 — whole-taxonomy single pointwise call (reuse part2_eval prompt path)
# --------------------------------------------------------------------------- #
def engine_c0(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    try:
        messages = build_messages(rec, modality, style)
        raw = chat_complete(client, model, messages, max_tokens)
    except Exception as exc:  # noqa: BLE001 - bad record / API error must not abort the run
        out["failure"] = True
        out["raw"] = f"ERR {exc}"[:300]
        return out
    out["raw"] = raw[:400]
    try:
        parsed = parse_examiner_json(raw)
    except Exception:  # noqa: BLE001
        out["failure"] = True
        return out
    findings = parsed.get("findings", []) or []
    types = sorted({f.get("type") for f in findings if f.get("type")})
    out["predicted_types"] = types
    out["has_defect"] = bool(parsed.get("has_defect")) or bool(findings)
    out["named_target"] = target_defect in types
    return out


# --------------------------------------------------------------------------- #
# C3 — atomic per-type binary + forced localization (PresentBench-style)
# --------------------------------------------------------------------------- #
def engine_c3(client, model, rec, modality, target_defect, style, max_tokens):
    out = _blank_result(rec)
    img = rec.get("image_path") or rec.get("metadata", {}).get("defective_image_path")
    if not img:
        out["failure"] = True
        return out
    question = question_for(target_defect)
    text = f"Question: {question}\n\n{C3_SCHEMA_HINT}"
    content = [image_content_from_path(img), {"type": "text", "text": text}]
    messages = [{"role": "system", "content": C3_SYSTEM}, {"role": "user", "content": content}]
    try:
        raw = chat_complete(client, model, messages, max_tokens)
    except Exception as exc:  # noqa: BLE001
        out["failure"] = True
        out["raw"] = f"ERR {exc}"[:300]
        return out
    out["raw"] = raw[:400]
    try:
        parsed = parse_examiner_json(raw)
    except Exception:  # noqa: BLE001
        out["failure"] = True
        return out
    present = bool(parsed.get("present"))
    locator = (parsed.get("evidence_element") or "").strip()
    region = (parsed.get("evidence_region") or "").strip()
    # Forced-evidence gate: YES only counts if it points somewhere concrete.
    has_evidence = bool(locator) and locator.lower() not in {"empty", "none", "n/a"}
    asserted = present and has_evidence
    out["has_defect"] = asserted
    out["named_target"] = asserted
    out["locator"] = {"element": locator, "region": region} if asserted else None
    out["confidence"] = parsed.get("confidence")
    out["predicted_types"] = [target_defect] if asserted else []
    return out


# --------------------------------------------------------------------------- #
# C1 / C2 — implemented in dedicated engine modules (Phase 1); imported lazily.
# --------------------------------------------------------------------------- #
def engine_c1(client, model, rec, modality, target_defect, style, max_tokens):
    from slide_examiner.elicit_freeform import run_freeform_sample
    return run_freeform_sample(
        client, model, rec, modality=modality, target_defect=target_defect,
        max_tokens=max_tokens, blank=_blank_result,
    )


def engine_c2(client, model, rec, modality, target_defect, style, max_tokens):
    from slide_examiner.elicit_pairwise import run_pairwise_sample
    return run_pairwise_sample(
        client, model, rec, target_defect=target_defect,
        max_tokens=max_tokens, blank=_blank_result,
    )


ENGINES = {"C0": engine_c0, "C1": engine_c1, "C2": engine_c2, "C3": engine_c3}


# --------------------------------------------------------------------------- #
# Job construction + run
# --------------------------------------------------------------------------- #
def _level_of(defect: str) -> str:
    return "deck" if defect in DECK_DEFECTS else "page"


def build_jobs(recs, defects, modalities, max_per_defect):
    bydef = collections.defaultdict(list)
    for r in recs:
        bydef[defect_of(r)].append(r)
    jobs = []  # (rec, modality, target_defect, is_clean)
    targets = defects or [d for d in bydef if d != "NO_DEFECT"]
    for d in targets:
        pos = bydef.get(d, [])[:max_per_defect]
        cleans = [c for r in pos if (c := clean_variant(r))]
        for r in pos:
            for m in modalities:
                jobs.append((r, m, d, False))
        for c in cleans:
            for m in modalities:
                jobs.append((c, m, d, True))
    return jobs


def run(args):
    from openai import OpenAI

    # timeout/max_retries so a crashed server makes calls FAIL FAST (caught ->
    # marked failure) instead of hanging the whole sweep indefinitely.
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url,
                    timeout=90.0, max_retries=1)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    engine = ENGINES[args.condition]
    jobs = build_jobs(recs, args.defects, args.modalities, args.max_per_defect)
    if args.condition == "C2":
        # Playwright sync API is not thread-safe -> batch-render the snap-twins for
        # ONLY the records actually used (dedup by slide_id), in the main thread,
        # before the pool starts.
        from slide_examiner.elicit_pairwise import prepare_twins
        seen, used = set(), []
        for rec, _m, _d, _clean in jobs:
            sid = (rec.get("slide") or {}).get("slide_id")
            if sid and sid not in seen:
                seen.add(sid)
                used.append(rec)
        prepared = prepare_twins(used)
        print(f"[C2] prepared {len(prepared)} snap-twins from {len(used)} unique IR records")
    print(f"[{args.model}/{args.condition}/{args.style}] {len(jobs)} probes "
          f"over defects={args.defects} modalities={args.modalities}")

    def work(rec, modality, target_defect, is_clean):
        res = engine(client, args.model, rec, modality, target_defect, args.style, args.max_tokens)
        res["modality"] = modality
        res["defect"] = target_defect
        res["is_clean"] = is_clean
        res["level"] = "deck" if is_deck(rec) else "page"
        return res

    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, *job) for job in jobs]
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} {time.time()-t0:.0f}s")

    metrics = score(rows, args.modalities, args.defects)
    result = {
        "condition": args.condition, "model": args.model, "style": args.style,
        "manifest": args.manifest, "modalities": args.modalities,
        "defects": args.defects, "n_jobs": len(jobs),
        "failures": sum(1 for r in rows if r.get("failure")),
        "metrics": metrics,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Scoring — paired-clean, two levels (detection / named), with Wilson CIs
# --------------------------------------------------------------------------- #
def _cell(pos_rows, neg_rows, key):
    tp = sum(bool(r[key]) for r in pos_rows)
    fn = len(pos_rows) - tp
    fp = sum(bool(r[key]) for r in neg_rows)
    tn = len(neg_rows) - fp
    n_pos, n_neg = len(pos_rows), len(neg_rows)
    recall = tp / n_pos if n_pos else 0.0
    spec = tn / n_neg if n_neg else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    bacc = balanced_accuracy_ci(tp, n_pos, tn, n_neg)
    rec_ci = wilson_interval(tp, n_pos)
    prec_ci = wilson_interval(tp, tp + fp) if (tp + fp) else None
    return {
        "recall": round(recall, 3), "specificity": round(spec, 3),
        "bal_acc": round(bacc.estimate, 3), "bal_acc_ci": [round(bacc.low, 3), round(bacc.high, 3)],
        "precision": round(precision, 3),
        "precision_ci": [round(prec_ci.low, 3), round(prec_ci.high, 3)] if prec_ci else None,
        "fpr": round(1 - spec, 3), "f1": round(f1, 3),
        "recall_ci": [round(rec_ci.low, 3), round(rec_ci.high, 3)],
        "tp": tp, "fn": fn, "fp": fp, "tn": tn, "n_pos": n_pos, "n_neg": n_neg,
    }


def score(rows, modalities, defects):
    metrics = {}
    target_defects = defects or sorted({r["defect"] for r in rows})
    for mod in modalities:
        mrows = [r for r in rows if r["modality"] == mod and not r.get("failure")]
        per_defect = {}
        for d in target_defects:
            lvl = _level_of(d)
            pos = [r for r in mrows if not r["is_clean"] and r["defect"] == d]
            neg = [r for r in mrows if r["is_clean"] and r["defect"] == d and r["level"] == lvl]
            if not pos or not neg:
                continue
            per_defect[d] = {
                "detection": _cell(pos, neg, "has_defect"),
                "named": _cell(pos, neg, "named_target"),
                # Headline = detection universally: the C3-vs-C0 science is about
                # asserting-a-defect vs abstaining (a free-form critic that sees an
                # overflow but the cheap classifier labels it a neighbour type still
                # *detected* it). `named` is kept as a stricter secondary metric.
                "headline_level": "detection",
            }
        metrics[mod] = {"per_defect": per_defect}
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", choices=list(ENGINES), required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--base-url", default="http://localhost:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--style", choices=["trained", "scoped"], default="trained")
    ap.add_argument("--defects", nargs="+", default=None,
                    help="Defect-type strings to probe (e.g. G1_TEXT_OVERFLOW "
                         "S6_IMAGE_TEXT_CONTRADICTION G7_RENDER_CONTAINMENT_OVERFLOW).")
    ap.add_argument("--modalities", nargs="+", default=["A"])
    ap.add_argument("--max-per-defect", type=int, default=60)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
