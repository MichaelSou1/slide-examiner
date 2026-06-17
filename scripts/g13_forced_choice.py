"""2-AFC forced-choice probe for G1/G3 at a given render resolution.

Pairs each defective slide with its matching clean slide (same base, only the
defect differs) and asks which slide has the defect, both orderings, image-only.
Chance = 50%. Tests whether higher resolution + relative judgement rescues the
geometry detection that pointwise judging cannot do.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.model_adapters import _image_url

REPO = "/home/gpus/slide-examiner"
QUESTION = {
    "G1_TEXT_OVERFLOW": (
        "You are shown two slides: SLIDE A (first image) and SLIDE B (second image). "
        "In exactly ONE of them, some text overflows or spills outside the borders of its box; "
        "in the other, all text fits inside its box. Which slide has the text overflow?"),
    "G3_ALIGNMENT_OFFSET": (
        "You are shown two slides: SLIDE A (first image) and SLIDE B (second image). "
        "In exactly ONE of them, one element is misaligned — shifted out of alignment with the others; "
        "in the other, the elements are aligned. Which slide has the misaligned element?"),
}
SUFFIX = ' Output ONLY one JSON object: {"answer": "A"} or {"answer": "B"}.'


def img_url(rec):
    p = rec["image_path"]
    return _image_url(p if p.startswith("/") else f"{REPO}/{p}")


def trial(client, model, prompt, a_url, b_url, answer):
    msgs = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": a_url}},
        {"type": "image_url", "image_url": {"url": b_url}},
        {"type": "text", "text": prompt}]}]
    try:
        out = client.chat.completions.create(model=model, messages=msgs, max_tokens=60, temperature=0.0)
        raw = (out.choices[0].message.content or "").strip()
    except Exception as exc:
        return {"pick": None, "correct": False, "error": str(exc)[:100]}
    m = re.search(r'"answer"\s*:\s*"?([AB])"?', raw, re.I) or re.search(r'\b([AB])\b', raw)
    pick = m.group(1).upper() if m else None
    return {"pick": pick, "correct": pick == answer}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--defect", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    from openai import OpenAI
    client = OpenAI(api_key="EMPTY", base_url=args.base_url)

    recs = [json.loads(l) for l in open(args.manifest) if l.strip()]
    recs = [r for r in recs if r.get("metadata", {}).get("defect") == args.defect]
    by_key = defaultdict(dict)
    for r in recs:
        by_key[r["metadata"]["pair_key"]][r["metadata"]["role"]] = r
    pairs = [(k, v["def"], v["clean"]) for k, v in by_key.items() if "def" in v and "clean" in v]

    prompt = QUESTION[args.defect] + SUFFIX
    jobs = []
    for k, d, c in pairs:
        jobs.append((k, "def-first", img_url(d), img_url(c), "A"))
        jobs.append((k, "clean-first", img_url(c), img_url(d), "B"))

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(trial, client, args.model, prompt, a, b, ans): (k, lab) for (k, lab, a, b, ans) in jobs}
        for fut in as_completed(futs):
            k, lab = futs[fut]; r = fut.result(); r["pair"] = k; r["order"] = lab; results.append(r)

    n = len(results); correct = sum(r["correct"] for r in results)
    picks = defaultdict(int)
    for r in results:
        picks[r["pick"]] += 1
    by_pair = defaultdict(list)
    for r in results:
        by_pair[r["pair"]].append(r["correct"])
    both = sum(1 for v in by_pair.values() if len(v) == 2 and all(v))
    summary = {"defect": args.defect, "model": args.model, "manifest": args.manifest,
               "n_trials": n, "n_pairs": len(pairs), "accuracy": round(correct / n, 3) if n else None,
               "robust_both_orderings": f"{both}/{len(by_pair)}",
               "robust_accuracy": round(both / len(by_pair), 3) if by_pair else None,
               "picks": dict(picks)}
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.defect} acc {correct}/{n}={summary['accuracy']:.0%} robust {both}/{len(by_pair)} picks={dict(picks)}")


if __name__ == "__main__":
    main()
