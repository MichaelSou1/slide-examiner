"""Confirm Penguin-VL-8B actually perceives images (rule out silent image-drop).

Probes the 3 blatant sanity slides with a plain perception question. If it
catches the blatant overflow/overlap and clears the clean one, the image is
reaching the model and the geometry-subset zeros are genuine model behaviour,
not a broken pipeline.
"""
from __future__ import annotations

import base64
from pathlib import Path

import penguinvl.plugin.vllm  # noqa: F401
from vllm import LLM, SamplingParams

REPO = "/home/gpus/slide-examiner"
CASES = [
    ("blatant_overflow", f"{REPO}/runs/pilot/sanity/blatant_overflow/1024/image.png"),
    ("blatant_overlap", f"{REPO}/runs/pilot/sanity/blatant_overlap/1024/image.png"),
    ("clearly_clean", f"{REPO}/runs/pilot/sanity/clearly_clean/1024/image.png"),
]
PROMPT = ("Describe this slide's layout. Does any text run outside the borders of its box, "
          "or do any two boxes overlap each other? Answer plainly.")


def data_url(p):
    return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()


def main():
    llm = LLM(model="/home/gpus/models/Penguin-VL-8B", tensor_parallel_size=2,
              gpu_memory_utilization=0.90, max_model_len=12288, enforce_eager=True,
              trust_remote_code=True, disable_custom_all_reduce=True, limit_mm_per_prompt={"image": 1})
    convs = [[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": data_url(p)}},
        {"type": "text", "text": PROMPT}]}] for _name, p in CASES]
    outs = llm.chat(convs, SamplingParams(temperature=0.0, max_tokens=200),
                    chat_template_kwargs={"image_token": "<image>"})
    for (name, _p), out in zip(CASES, outs):
        print(f"### {name}\n  {(out.outputs[0].text or '').strip()[:300]}\n")


if __name__ == "__main__":
    main()
