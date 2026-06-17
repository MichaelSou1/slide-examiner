"""Forced-choice (2-AFC) re-eval of S6, since VLMs compare better than they judge.

Pairs each S6 (figure-text contradiction) slide with the matching clean
(agreeing) slide for the same figure topic -- only the body differs -- shows both
images, and asks which slide contains the contradiction. Each pair is run in both
orderings to cancel position bias. Chance = 50%; this tests whether relative
comparison beats the chance-level pointwise judgement.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.model_adapters import _image_url

PROMPT = (
    "You are shown two slides: SLIDE A (first image) and SLIDE B (second image). "
    "In exactly ONE of them the figure/chart depicts a trend that CONTRADICTS the body text "
    "(e.g. the figure shows an upward arrow and says a metric 'rose' while the text says it 'fell', "
    "or vice versa). In the other slide the figure and the text agree. "
    "Decide which slide contains the contradiction. "
    'Output ONLY one JSON object: {"answer": "A"} or {"answer": "B"}. No other text.'
)


def topic(sample_id: str) -> str:
    m = re.match(r"(imgslide_\d+)", sample_id)
    return m.group(1) if m else sample_id


def is_s6(rec: dict) -> bool:
    return any(l.get("type") == "S6_IMAGE_TEXT_CONTRADICTION" for l in rec.get("labels", []))


def is_clean(rec: dict) -> bool:
    types = [l.get("type") for l in rec.get("labels", [])]
    return all(t == "NO_DEFECT" for t in types)  # no active defect


def trial(client, model: str, img_a: str, img_b: str, answer: str) -> dict:
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": _image_url(img_a)}},
        {"type": "image_url", "image_url": {"url": _image_url(img_b)}},
        {"type": "text", "text": PROMPT}]}]
    try:
        out = client.chat.completions.create(model=model, messages=messages, max_tokens=60, temperature=0.0)
        raw = (out.choices[0].message.content or "").strip()
    except Exception as exc:
        return {"answer": answer, "pick": None, "correct": False, "error": str(exc)[:120]}
    m = re.search(r'"answer"\s*:\s*"?([AB])"?', raw, re.I) or re.search(r'\b([AB])\b', raw)
    pick = m.group(1).upper() if m else None
    return {"answer": answer, "pick": pick, "correct": pick == answer, "raw": raw[:80]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/part1_img/manifest_s6_rendered.jsonl")
    ap.add_argument("--base-url", default="http://localhost:8013/v1")
    ap.add_argument("--model", default="qwen3vl-30b")
    ap.add_argument("--condition", default="freeform")
    ap.add_argument("--out", default="runs/probe/part1_s6_forced_choice_30b.json")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(api_key="EMPTY", base_url=args.base_url)
    recs = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]
    recs = [r for r in recs if r.get("metadata", {}).get("template_condition") == args.condition]

    s6 = {}; clean = {}
    for r in recs:
        if is_s6(r):
            s6.setdefault(topic(r["sample_id"]), r)
        elif is_clean(r):
            clean.setdefault(topic(r["sample_id"]), r)
    pairs = [(t, s6[t], clean[t]) for t in sorted(s6) if t in clean]

    jobs = []  # (topic, order_label, img_a, img_b, correct_answer)
    for t, s, c in pairs:
        jobs.append((t, "S6-first", s["image_path"], c["image_path"], "A"))
        jobs.append((t, "clean-first", c["image_path"], s["image_path"], "B"))

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(trial, client, args.model, a, b, ans): (t, lab) for (t, lab, a, b, ans) in jobs}
        for fut in as_completed(futs):
            t, lab = futs[fut]
            r = fut.result(); r["topic"] = t; r["order"] = lab
            results.append(r)

    n = len(results)
    correct = sum(r["correct"] for r in results)
    picks = defaultdict(int)
    for r in results:
        picks[r["pick"]] += 1
    # per-topic: correct in BOTH orderings (robust to position bias)
    by_topic = defaultdict(list)
    for r in results:
        by_topic[r["topic"]].append(r["correct"])
    both = sum(1 for v in by_topic.values() if len(v) == 2 and all(v))
    summary = {
        "model": args.model, "condition": args.condition, "n_trials": n, "n_pairs": len(pairs),
        "accuracy": round(correct / n, 3) if n else None,
        "pairs_correct_both_orderings": both, "pairs_total": len(by_topic),
        "robust_accuracy": round(both / len(by_topic), 3) if by_topic else None,
        "pick_distribution": dict(picks),
        "results": sorted(results, key=lambda r: (r["topic"], r["order"])),
    }
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"2-AFC accuracy: {correct}/{n} = {summary['accuracy']:.0%} "
          f"(robust both-orderings: {both}/{len(by_topic)} = {summary['robust_accuracy']:.0%}); "
          f"picks={dict(picks)}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
