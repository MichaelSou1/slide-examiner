"""Push the Part 2 QLoRA LoRA adapter to the Hugging Face Hub.

Run this ONLY after enabling a proxy so huggingface.co is reachable. It:
  1. auto-generates a model card (README.md) from runs/probe/part2_summary.json,
  2. creates the HF model repo (if needed) and uploads the adapter folder.

Auth: set HF_TOKEN env var (or run `huggingface-cli login`) before running.

Usage:
  HF_TOKEN=hf_xxx python scripts/push_adapter_hf.py \
    --repo-id <user>/slide-examiner-8b-qlora \
    --adapter-dir runs/part2/examiner_lora_v2
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def model_card(repo_id: str, adapter_dir: Path) -> str:
    summ = {}
    p = REPO / "runs/probe/part2_summary.json"
    if p.exists():
        summ = json.loads(p.read_text())

    def g(*keys, default=None):
        d = summ
        for k in keys:
            if not isinstance(d, dict):
                return default
            d = d.get(k)
            if d is None:
                return default
        return d

    ft = g("models", "ft-8b", "pointwise_test", "metrics", "A", "group_bal_acc", "semantic")
    zs8 = g("models", "zs-8b", "pointwise_test", "metrics", "A", "group_bal_acc", "semantic")
    zs30 = g("models", "zs-30b", "pointwise_test", "metrics", "A", "group_bal_acc", "semantic")
    evals = g("training", "eval_loss_series")
    return f"""---
license: apache-2.0
base_model: Qwen/Qwen3-VL-8B-Instruct
tags:
- lora
- qlora
- vision-language
- slide-quality
- presentation-examiner
library_name: peft
---

# Slide-Examiner 8B (QLoRA adapter)

QLoRA LoRA adapter on **Qwen3-VL-8B-Instruct** for examining presentation-slide
quality. Trained as Part 2 of the Slide-Examiner project.

## What it does
A pointwise + pairwise slide *examiner*: detects semantic slide defects
(title/body mismatch, density, narrative order, missing section) and is
deliberately trained to **abstain on pixel-level geometry** (overflow / overlap /
alignment / font / color / margin) — those are handled by a symbolic linter, not
the VLM. Output is strict contract JSON (PageExamResult / DeckExamResult /
PairwiseResult).

## Headline results (in-domain held-out, balanced accuracy, modality A = image-only)
| S-group semantic | this adapter (8B) | zero-shot 8B | zero-shot 30B |
|---|---|---|---|
| balanced accuracy | {ft} | {zs8} | {zs30} |

The finetuned 8B examiner surpasses the **zero-shot 30B** model on the S-group
while keeping ~0 false-positive rate on geometry (it abstains rather than
hallucinating geometry from pixels). eval_loss trajectory: {evals}.

## Training
- Base: `Qwen/Qwen3-VL-8B-Instruct`; QLoRA 4-bit (bitsandbytes), LoRA rank 16, alpha 32, 2 epochs, cosine LR 1e-4.
- Data: ~5.3K synthetic slides (paired clean/defective), architecture-correct routing
  (S-group pointwise; geometry restate-from-structure + abstain-under-image; G1/S6 pairwise; S3→linter).
- Framework: LLaMA-Factory, template `qwen3_vl_nothink`.

## Usage
```python
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor
base = "Qwen/Qwen3-VL-8B-Instruct"
model = AutoModelForImageTextToText.from_pretrained(base, torch_dtype="bfloat16", device_map="auto")
model = PeftModel.from_pretrained(model, "{repo_id}")
proc = AutoProcessor.from_pretrained(base)
```

Adapter files: `{', '.join(sorted(p.name for p in adapter_dir.glob('adapter*')))}`.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", required=True, help="e.g. <user>/slide-examiner-8b-qlora")
    ap.add_argument("--adapter-dir", default="runs/part2/examiner_lora_v2")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="write the model card but do not upload")
    args = ap.parse_args()

    adapter_dir = (REPO / args.adapter_dir) if not Path(args.adapter_dir).is_absolute() else Path(args.adapter_dir)
    if not (adapter_dir / "adapter_model.safetensors").exists():
        raise SystemExit(f"no adapter at {adapter_dir}")
    card = model_card(args.repo_id, adapter_dir)
    (adapter_dir / "README.md").write_text(card, encoding="utf-8")
    print(f"wrote model card to {adapter_dir/'README.md'}")
    if args.dry_run:
        print("dry-run: skipping upload"); return

    token = os.environ.get("HF_TOKEN")
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    api.create_repo(args.repo_id, repo_type="model", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=args.repo_id, repo_type="model", folder_path=str(adapter_dir),
        allow_patterns=["adapter_*", "README.md", "*.json", "training_eval_loss.png"],
    )
    print(f"uploaded {adapter_dir} -> https://huggingface.co/{args.repo_id}")


if __name__ == "__main__":
    main()
