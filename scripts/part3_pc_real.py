"""Part 3 R2 — real-layout modality A/B/C attribution (detect / localize / repair).

Runs the paper's perception/capability attribution protocol on the REAL-layout
paired manifest (``part3_real_inject``): each injected defect is presented under

  A  image-only            (the real LibreOffice render)
  B  structured oracle only (the lossless python-pptx IR, de-leaked)
  C  image + oracle

with the SAME atomic-binary detect prompt per class, plus a localize target and a
repair action. Scoring is balanced accuracy on paired clean controls (never recall
alone) with Wilson CIs, and an exact paired McNemar A-vs-C / A-vs-B on per-item
correctness. The attribution logic (paper Sec. 4):

  A-fail ∧ B-succeed  ⇒ perception bottleneck (structure reveals it)
  A-fail ∧ C-fail     ⇒ capability bottleneck (neither channel suffices)
  A-succeed ∧ repair-fail ⇒ execution bottleneck

This closes the §8 limitation: a *structured (image+oracle) evaluation on real
slides* the paper said it could not run, with a lossless tool oracle (no human /
self annotation -> no annotation bias).

Usage (one served VLM):
  ~/anaconda3/envs/slide-examiner/bin/python scripts/part3_pc_real.py \
    --manifest data/part3/manifest_real_rendered.jsonl \
    --base-url http://localhost:8101/v1 --model qwen35-27b \
    --out data/part3/pc_real_qwen35-27b.json --dump-rows data/part3/pc_real_qwen35-27b_rows.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(REPO))

from slide_examiner.adapters import parse_examiner_json  # noqa: E402
from slide_examiner.elicit_common import chat_complete  # noqa: E402
from slide_examiner.examiner_contract import image_content_from_path  # noqa: E402
from slide_examiner.schemas import oracle_view  # noqa: E402
from slide_examiner.statistics import balanced_accuracy_ci, wilson_interval  # noqa: E402

MODALITIES = ["A", "B", "C"]
CLASSES = ["G1_TEXT_OVERFLOW", "G2_ELEMENT_OVERLAP", "G3_ALIGNMENT_OFFSET",
           "G4_FONT_SIZE_INCONSISTENCY", "G6_MARGIN_VIOLATION"]

QUESTION = {
    "G1_TEXT_OVERFLOW": ("Does any text visibly overflow or get clipped by its box/container, "
                         "or run past the slide edge?"),
    "G2_ELEMENT_OVERLAP": ("Do any two elements visibly overlap or collide (one drawn on top of "
                           "another) when they should be laid out separately?"),
    "G3_ALIGNMENT_OFFSET": ("Is any element misaligned — visibly offset from the column / edge / "
                            "baseline that its peer elements line up to?"),
    "G4_FONT_SIZE_INCONSISTENCY": ("Is any text block's font size inconsistent with comparable peers "
                                   "— noticeably larger or smaller than the text it should match?"),
    "G6_MARGIN_VIOLATION": ("Does any element cross the slide's safe margin or bleed off the slide "
                            "edge (partly outside the slide)?"),
}

SYSTEM = ("You are a meticulous slide-quality inspector. You will be asked about ONE specific "
          "possible defect on ONE slide. Use only the evidence you are given. Answer with a single "
          "JSON object and nothing else.")

SCHEMA = ('Answer strictly as JSON:\n'
          '{"present": true|false, "evidence_element": "<the concrete element/region you point to, '
          'or empty>", "evidence_region": "<top-left|top|top-right|left|center|right|bottom-left|'
          'bottom|bottom-right|empty>", "fix": "<one concrete corrective action, or empty>", '
          '"confidence": 0.0-1.0}\n'
          'If present=true you MUST name a concrete evidence_element and a fix action; if you cannot '
          'point to concrete evidence, answer present=false.')

ACTION_RE = re.compile(r"\b(add|adjust|align|change|correct|move|normalize|realign|reduce|remove|"
                       r"replace|resize|restore|revise|reorder|shorten|split|update|shrink|enlarge|"
                       r"wrap|fit|center|nudge)\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Structured-oracle serialization (modality B/C)
# --------------------------------------------------------------------------- #
def serialize_oracle(slide_dict: dict) -> str:
    view = oracle_view(slide_dict)
    lines = [f"STRUCTURED SLIDE ORACLE (lossless, extracted from the source file; coordinates in "
             f"pixels; slide is {view.get('width')}x{view.get('height')} px):"]
    for el in view.get("elements", []):
        b = el.get("bbox", {})
        style = el.get("style", {})
        txt = (el.get("text") or "").replace("\n", " ")
        if len(txt) > 120:
            txt = txt[:120] + "…"
        font = style.get("font_size_pt")
        color = style.get("color")
        lines.append(
            f"[{el.get('element_id')}] type={el.get('type')} "
            f"bbox=(x={b.get('x')}, y={b.get('y')}, w={b.get('width')}, h={b.get('height')}) "
            f"font={font}pt color={color} text={txt!r}"
        )
    return "\n".join(lines)


def build_content(rec_slide: dict, image_path: str | None, modality: str, defect: str):
    content = []
    if modality in ("A", "C") and image_path:
        content.append(image_content_from_path(image_path))
    text = ""
    if modality in ("B", "C"):
        text += serialize_oracle(rec_slide) + "\n\n"
    text += f"Question: {QUESTION[defect]}\n\n{SCHEMA}"
    content.append({"type": "text", "text": text})
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


# --------------------------------------------------------------------------- #
# One probe
# --------------------------------------------------------------------------- #
def probe(client, model, slide_dict, image_path, modality, defect, max_tokens):
    out = {"present": False, "localized": False, "repair_ok": False, "failure": False,
           "evidence_element": "", "raw": ""}
    if modality in ("A", "C") and not (image_path and Path(image_path).exists()):
        out["failure"] = True
        return out
    messages = build_content(slide_dict, image_path, modality, defect)
    try:
        raw = chat_complete(client, model, messages, max_tokens)
    except Exception as exc:  # noqa: BLE001
        out["failure"] = True
        out["raw"] = f"ERR {exc}"[:200]
        return out
    out["raw"] = raw[:300]
    try:
        parsed = parse_examiner_json(raw)
    except Exception:  # noqa: BLE001
        out["failure"] = True
        return out
    present = bool(parsed.get("present"))
    ev = (parsed.get("evidence_element") or "").strip()
    fix = (parsed.get("fix") or "").strip()
    has_ev = bool(ev) and ev.lower() not in {"empty", "none", "n/a", "null"}
    out["present"] = present and has_ev
    out["evidence_element"] = ev
    out["repair_ok"] = bool(ACTION_RE.search(fix)) if out["present"] else False
    return out


def is_localized(ev: str, target_id: str, target_text: str) -> bool:
    e = ev.lower()
    if target_id and target_id.lower() in e:
        return True
    if target_text:
        toks = [t for t in re.split(r"\W+", target_text.lower()) if len(t) > 3][:6]
        hit = sum(1 for t in toks if t in e)
        if toks and hit >= max(1, len(toks) // 3):
            return True
    return False


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def cell(pos_rows, neg_rows):
    tp = sum(r["present"] for r in pos_rows)
    fp = sum(r["present"] for r in neg_rows)
    n_pos, n_neg = len(pos_rows), len(neg_rows)
    tn = n_neg - fp
    recall = tp / n_pos if n_pos else 0.0
    spec = tn / n_neg if n_neg else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    bacc = balanced_accuracy_ci(tp, n_pos, tn, n_neg)
    rec_ci = wilson_interval(tp, n_pos)
    loc = [r for r in pos_rows if r["present"]]
    localize_rate = sum(r["localized"] for r in loc) / len(loc) if loc else None
    repair_rate = sum(r["repair_ok"] for r in loc) / len(loc) if loc else None
    return {
        "bal_acc": round(bacc.estimate, 3), "bal_acc_ci": [round(bacc.low, 3), round(bacc.high, 3)],
        "recall": round(recall, 3), "recall_ci": [round(rec_ci.low, 3), round(rec_ci.high, 3)],
        "specificity": round(spec, 3), "fpr": round(1 - spec, 3), "precision": round(prec, 3),
        "localize_rate": round(localize_rate, 3) if localize_rate is not None else None,
        "repair_rate": round(repair_rate, 3) if repair_rate is not None else None,
        "tp": tp, "fp": fp, "fn": n_pos - tp, "tn": tn, "n_pos": n_pos, "n_neg": n_neg,
    }


def mcnemar(corr_x: dict, corr_y: dict) -> tuple[float, int, int]:
    """Exact two-sided McNemar over shared sample_ids. b = x-wrong & y-right (y gains)."""
    shared = set(corr_x) & set(corr_y)
    b = sum(1 for s in shared if (not corr_x[s]) and corr_y[s])
    c = sum(1 for s in shared if corr_x[s] and (not corr_y[s]))
    n = b + c
    if n == 0:
        return 1.0, b, c
    k = min(b, c)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) * (0.5 ** n))
    return round(p, 4), b, c


def run(args):
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"), base_url=args.base_url,
                    timeout=120.0, max_retries=1)
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

    jobs = []  # (rec, modality, is_clean)
    for r in recs:
        for m in MODALITIES:
            jobs.append((r, m, False))
            jobs.append((r, m, True))
    print(f"[{args.model}] {len(recs)} pairs x {len(MODALITIES)} modalities x2 = {len(jobs)} probes")

    def work(rec, modality, is_clean):
        defect = rec["defect"]
        slide_dict = rec["clean_slide"] if is_clean else rec["slide"]
        image_path = (rec["pair"]["clean_image_path"] if is_clean
                      else rec["pair"]["defective_image_path"])
        res = probe(client, args.model, slide_dict, image_path, modality, defect, args.max_tokens)
        tgt = rec["labels"][0]["target_element_ids"][0]
        tgt_text = ""
        for el in rec["slide"].get("elements", []):
            if el.get("element_id") == tgt:
                tgt_text = el.get("text", "")
                break
        res["localized"] = is_localized(res["evidence_element"], tgt, tgt_text) if (res["present"] and not is_clean) else False
        res.update({"sample_id": rec["sample_id"], "defect": defect, "modality": modality,
                    "is_clean": is_clean})
        return res

    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, *j) for j in jobs]
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 200 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} {time.time()-t0:.0f}s")

    # per-modality per-class cells + correctness maps for McNemar
    per_modality: dict = {}
    correct: dict = {}  # modality -> class -> sample_id(+__C) -> correct
    for m in MODALITIES:
        per_modality[m] = {"per_class": {}}
        for cls in CLASSES:
            pos = [r for r in rows if r["modality"] == m and r["defect"] == cls
                   and not r["is_clean"] and not r["failure"]]
            neg = [r for r in rows if r["modality"] == m and r["defect"] == cls
                   and r["is_clean"] and not r["failure"]]
            if not pos or not neg:
                continue
            per_modality[m]["per_class"][cls] = cell(pos, neg)
            cm = correct.setdefault(m, {}).setdefault(cls, {})
            for r in pos:
                cm[r["sample_id"]] = bool(r["present"])             # defective: correct iff flagged
            for r in neg:
                cm[r["sample_id"] + "__C"] = bool(not r["present"])  # clean: correct iff NOT flagged

    # attribution per class (A vs B vs C) + McNemar
    attribution = {}
    for cls in CLASSES:
        a = per_modality["A"]["per_class"].get(cls)
        b = per_modality["B"]["per_class"].get(cls)
        c = per_modality["C"]["per_class"].get(cls)
        if not (a and b and c):
            continue
        p_ac, gac, lac = mcnemar(correct.get("A", {}).get(cls, {}), correct.get("C", {}).get(cls, {}))
        p_ab, gab, lab = mcnemar(correct.get("A", {}).get(cls, {}), correct.get("B", {}).get(cls, {}))
        a_ba, b_ba, c_ba = a["bal_acc"], b["bal_acc"], c["bal_acc"]
        # verdict at chance threshold 0.6 (bal-acc), structure-rescue gate
        a_fail = a_ba < 0.6
        if a_fail and max(b_ba, c_ba) >= 0.6:
            verdict = "perception"      # structure reveals what image-only misses
        elif a_fail and c_ba < 0.6:
            verdict = "capability"      # neither channel suffices
        else:
            verdict = "image_sufficient"
        attribution[cls] = {
            "A_bal_acc": a_ba, "B_bal_acc": b_ba, "C_bal_acc": c_ba,
            "delta_C_minus_A": round(c_ba - a_ba, 3), "delta_B_minus_A": round(b_ba - a_ba, 3),
            "mcnemar_C_vs_A": {"p": p_ac, "gain": gac, "loss": lac},
            "mcnemar_B_vs_A": {"p": p_ab, "gain": gab, "loss": lab},
            "verdict": verdict,
            "repair_rate_A": a.get("repair_rate"), "localize_rate_C": c.get("localize_rate"),
        }

    result = {
        "model": args.model, "manifest": args.manifest, "n_pairs": len(recs),
        "failures": sum(1 for r in rows if r["failure"]),
        "per_modality": per_modality, "attribution": attribution,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.dump_rows:
        Path(args.dump_rows).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(attribution, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/part3/manifest_real_rendered.jsonl")
    ap.add_argument("--base-url", default="http://localhost:8101/v1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--max-per-class", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-rows", default=None)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
