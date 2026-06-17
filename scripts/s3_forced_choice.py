"""Track P — forced-choice (2-AFC) for S3 terminology inconsistency.

S3 is a deck-level consistency check: in the defective deck one key term is
swapped on a single slide (canonical "the Platform" vs variant "the PlatformX")
while every other slide keeps the canonical term; the clean deck uses the term
consistently. Pointwise scoping over a single deck is the absolute-judgement
task that S6 showed VLMs fail at; here we show DECK A (all pages) then DECK B
(all pages) and ask which deck uses a key term inconsistently, in both
orderings to cancel position bias. Chance = 50%.

Mirrors scripts/s6_forced_choice.py. Uses the defective deck pages (sgroup
manifest) and the matching clean deck pages (deck-negative rendered manifest),
paired by clean_deck_path.

Usage: PYTHONPATH=. python scripts/s3_forced_choice.py \
  --base-url http://localhost:8013/v1 --model qwen3vl-30b
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.model_adapters import _image_url

SGROUP = "data/part1/manifest_sgroup.jsonl"
DECKNEG = "data/part1/manifest_sgroup_deckneg_rendered.jsonl"

PROMPT = (
    "You are shown two presentation decks: DECK A (first group of slide images) "
    "and DECK B (second group). In exactly ONE of the two decks, a key noun/term "
    "is used INCONSISTENTLY across its slides — the same concept is named one way "
    "on most slides and a slightly different way on one slide (e.g. 'the Platform' "
    "on most slides but 'the PlatformX' on one). In the other deck the term is used "
    "consistently everywhere. Decide which deck has the inconsistent terminology. "
    'Output ONLY one JSON object: {"answer": "A"} or {"answer": "B"}. No other text.'
)


def content(pages_a, pages_b):
    blk = [{"type": "text", "text": "DECK A:"}]
    blk += [{"type": "image_url", "image_url": {"url": _image_url(p)}} for p in pages_a]
    blk += [{"type": "text", "text": "DECK B:"}]
    blk += [{"type": "image_url", "image_url": {"url": _image_url(p)}} for p in pages_b]
    blk += [{"type": "text", "text": PROMPT}]
    return blk


def trial(client, model, pages_a, pages_b, answer):
    messages = [{"role": "user", "content": content(pages_a, pages_b)}]
    try:
        out = client.chat.completions.create(model=model, messages=messages, max_tokens=60, temperature=0.0)
        raw = (out.choices[0].message.content or "").strip()
    except Exception as exc:
        return {"answer": answer, "pick": None, "correct": False, "error": str(exc)[:160]}
    m = re.search(r'"answer"\s*:\s*"?([AB])"?', raw, re.I) or re.search(r'\b([AB])\b', raw)
    pick = m.group(1).upper() if m else None
    return {"answer": answer, "pick": pick, "correct": pick == answer, "raw": raw[:80]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8013/v1")
    ap.add_argument("--model", default="qwen3vl-30b")
    ap.add_argument("--out", default="runs/probe/part1_s3_forced_choice_30b.json")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(api_key="EMPTY", base_url=args.base_url)

    sg = [json.loads(l) for l in Path(SGROUP).open() if l.strip()]
    s3 = [x for x in sg if x["labels"] and x["labels"][0]["type"] == "S3_TERMINOLOGY_INCONSISTENCY"]
    clean_by_cd = {r["metadata"]["clean_deck_path"]: r
                   for r in (json.loads(l) for l in Path(DECKNEG).open() if l.strip())}

    pairs = []
    for x in s3:
        cd = x["metadata"].get("clean_deck_path")
        clean = clean_by_cd.get(cd)
        if not clean:
            continue
        dpg = x["metadata"]["page_image_paths"]
        cpg = clean["metadata"]["page_image_paths"]
        pairs.append((x["sample_id"], dpg, cpg))

    jobs = []  # (topic, order_label, pages_a, pages_b, correct)
    for sid, dpg, cpg in pairs:
        jobs.append((sid, "defective-first", dpg, cpg, "A"))
        jobs.append((sid, "clean-first", cpg, dpg, "B"))

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(trial, client, args.model, a, b, ans): (t, lab)
                for (t, lab, a, b, ans) in jobs}
        for fut in as_completed(futs):
            t, lab = futs[fut]
            r = fut.result(); r["topic"] = t; r["order"] = lab
            results.append(r)

    n = len(results)
    correct = sum(r["correct"] for r in results)
    picks = defaultdict(int)
    for r in results:
        picks[r["pick"]] += 1
    by_topic = defaultdict(list)
    for r in results:
        by_topic[r["topic"]].append(r["correct"])
    both = sum(1 for v in by_topic.values() if len(v) == 2 and all(v))
    summary = {
        "model": args.model, "defect": "S3_TERMINOLOGY_INCONSISTENCY", "level": "deck",
        "n_trials": n, "n_pairs": len(pairs),
        "accuracy": round(correct / n, 3) if n else None,
        "pairs_correct_both_orderings": both, "pairs_total": len(by_topic),
        "robust_accuracy": round(both / len(by_topic), 3) if by_topic else None,
        "pick_distribution": dict(picks),
        "results": sorted(results, key=lambda r: (r["topic"], r["order"])),
    }
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    acc = summary["accuracy"]
    print(f"S3 2-AFC accuracy: {correct}/{n} = {acc:.0%} "
          f"(robust both-orderings: {both}/{len(by_topic)}); picks={dict(picks)}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
