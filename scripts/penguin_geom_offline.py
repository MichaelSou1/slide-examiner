"""Probe Penguin-VL-8B on the geometry subset using vLLM's OFFLINE LLM class.

The Penguin-VL vLLM plugin's OpenAI HTTP server fights version drift with the
pip vLLM 0.11.0, but the engine itself initializes fine. So we bypass the HTTP
server and call the offline `LLM.chat()` API (batched) directly, reusing the
same contract serializer + scope/schema suffix the other models used.

Run in the penguin-vl env:
  HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=1,2 \
  PYTHONPATH=/tmp/Penguin-VL-repo:/home/gpus/slide-examiner \
  python scripts/penguin_geom_offline.py --smoke   # then without --smoke for full
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import penguinvl.plugin.vllm  # noqa: F401 -- registers PenguinVLQwen3ForCausalLM + processor
from vllm import LLM, SamplingParams

from slide_examiner.adapters import parse_examiner_json
import scripts.run_pilot as rp

REPO = "/home/gpus/slide-examiner"
MANIFEST = f"{REPO}/data/part1/manifest_geometry.jsonl"
MODEL = "/home/gpus/models/Penguin-VL-8B"


def absolutize(rec):
    """Image paths in the manifest are relative to the repo; we run from /tmp
    (to dodge the gcc/./specs triton issue), so make them absolute."""
    p = rec.get("image_path")
    if p and not p.startswith("/"):
        rec["image_path"] = f"{REPO}/{p}"
    md = rec.get("metadata", {})
    if isinstance(md.get("page_image_paths"), list):
        md["page_image_paths"] = [pp if pp.startswith("/") else f"{REPO}/{pp}" for pp in md["page_image_paths"]]
    return rec
MODALITIES = ("A", "B", "C")  # image-bearing + structure; B' needs captions, skipped for geometry


def build_records(recs):
    jobs = []  # (rec, modality, messages)
    for rec in recs:
        for m in MODALITIES:
            msgs = rp.build_cell_messages(rec, m, "T1")
            jobs.append((rec, m, msgs))
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default="/home/gpus/slide-examiner/runs/probe/part1_geom_penguin.jsonl")
    args = ap.parse_args()

    recs = [absolutize(json.loads(l)) for l in open(MANIFEST) if l.strip()]
    if args.smoke:
        recs = recs[:2]

    llm = LLM(model=MODEL, tensor_parallel_size=2, gpu_memory_utilization=0.90,
              max_model_len=12288, enforce_eager=True, trust_remote_code=True,
              disable_custom_all_reduce=True, limit_mm_per_prompt={"image": 1})
    sp = SamplingParams(temperature=0.0, max_tokens=640)

    jobs = build_records(recs)
    convs = [m for (_r, _mod, m) in jobs]
    print(f"Running {len(convs)} conversations on Penguin-VL-8B...")
    t0 = time.time()
    outs = llm.chat(convs, sp, chat_template_kwargs={"image_token": "<image>"})
    print(f"  done in {time.time()-t0:.0f}s")

    records = []
    fails = 0
    for (rec, modality, _msgs), out in zip(jobs, outs):
        raw = out.outputs[0].text if out.outputs else ""
        rectype = "deck" if rec.get("deck") else "page"
        r = {"sample_id": rec["sample_id"], "model": "penguin-vl-8b", "modality": modality, "task": "T1",
             "labels": rec.get("labels", []), "label_types": [l.get("type") for l in rec.get("labels", [])],
             "metadata": rec.get("metadata", {}), "template_condition": rec.get("metadata", {}).get("template_condition"),
             "level": rectype, "raw_output": raw}
        try:
            r["output"] = parse_examiner_json(raw)
        except Exception as exc:
            r["output"] = None; r["examiner_failure"] = True; r["failure_message"] = str(exc)[:200]; fails += 1
        records.append(r)

    if args.smoke:
        for r in records:
            print(f"[{r['modality']}] {r['sample_id'][:40]} -> {(r.get('raw_output') or '')[:160]}")
        return

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as h:
        for r in records:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} records to {out} ({fails} parse failures)")


if __name__ == "__main__":
    main()
