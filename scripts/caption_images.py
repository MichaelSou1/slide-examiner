"""Generate the B' caption oracle by captioning rendered images with a VLM.

For each sample, the served model describes the rendered slide in neutral,
detailed natural language (transcribe text + describe layout, no quality
judgement). The description is written back to manifest `caption`, which the
contract serializer feeds to modality B'. Deck samples are captioned per page,
in render (defective) order, so narrative-order defects survive into B'.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from slide_examiner.model_adapters import _image_url

PROMPT = (
    "You are describing a single presentation slide to someone who cannot see it. "
    "First transcribe the title and every line of body text exactly as written. "
    "Then describe the layout factually: where each text block sits (top/left/center), "
    "its approximate width, and whether blocks are separated or touching. "
    "Report only what is visibly present; do not evaluate quality, do not guess intent. "
    "Answer in 3-6 plain sentences."
)


def caption_one(client, model: str, img: str, max_tokens: int) -> str:
    msg = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": _image_url(img)}},
        {"type": "text", "text": PROMPT}]}]
    out = client.chat.completions.create(model=model, messages=msg, max_tokens=max_tokens, temperature=0.0)
    return (out.choices[0].message.content or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/pilot/manifest_rendered.jsonl")
    ap.add_argument("--base-url", default="http://localhost:8012/v1")
    ap.add_argument("--model", default="qwen3vl-8b")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=320)
    args = ap.parse_args()

    from openai import OpenAI
    client = OpenAI(api_key="EMPTY", base_url=args.base_url)
    records = [json.loads(l) for l in Path(args.manifest).open() if l.strip()]

    # Collect every (record_index, page_index|None, image_path) to caption.
    jobs: list[tuple[int, int | None, str]] = []
    for i, rec in enumerate(records):
        if rec.get("deck"):
            for p, img in enumerate(rec.get("metadata", {}).get("page_image_paths", [])):
                jobs.append((i, p, img))
        elif rec.get("image_path"):
            jobs.append((i, None, rec["image_path"]))

    captions: dict[tuple[int, int | None], str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(caption_one, client, args.model, img, args.max_tokens): (i, p) for (i, p, img) in jobs}
        done = 0
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                captions[key] = fut.result()
            except Exception as exc:
                captions[key] = f"(caption failed: {exc})"
            done += 1
            if done % 40 == 0 or done == len(jobs):
                print(f"  captioned {done}/{len(jobs)}")

    for i, rec in enumerate(records):
        if rec.get("deck"):
            n = len(rec.get("metadata", {}).get("page_image_paths", []))
            parts = [f"Slide {p + 1}: {captions.get((i, p), '')}" for p in range(n)]
            rec["caption"] = " || ".join(parts)
        elif (i, None) in captions:
            rec["caption"] = captions[(i, None)]

    with Path(args.manifest).open("w", encoding="utf-8") as h:
        for rec in records:
            h.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote VLM captions into {args.manifest} ({len(jobs)} images)")


if __name__ == "__main__":
    main()
