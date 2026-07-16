#!/usr/bin/env python3
"""Merge a D3 LoRA adapter into BF16 weights for reproducible serving."""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.bfloat16, trust_remote_code=True, low_cpu_mem_usage=True,
    )
    merged = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    args.output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.output, safe_serialization=True, max_shard_size="5GB")
    AutoProcessor.from_pretrained(args.adapter, trust_remote_code=True).save_pretrained(args.output)


if __name__ == "__main__":
    main()
