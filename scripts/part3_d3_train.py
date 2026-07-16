#!/usr/bin/env python3
"""Train the D3 critic with multimodal SFT and explicit route/select/severity heads."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from PIL import Image
from peft import LoraConfig, PeftModel, get_peft_model
from torch import nn
from torch.utils.data import DataLoader, Dataset, Sampler, WeightedRandomSampler
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from transformers import BitsAndBytesConfig

from slide_examiner.d3_data import sha256_file
from slide_examiner.d3_training import (
    ACTIONS, LOSS_NAMES, LossWeights, action_class_weights, action_sample_weights,
)

REPO = Path(__file__).resolve().parents[1]


class JsonlDataset(Dataset):
    def __init__(self, path: Path, limit: int | None = None):
        self.rows = [json.loads(line) for line in path.open() if line.strip()]
        if limit:
            self.rows = self.rows[:limit]

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]


class MixedObjectiveBatchSampler(Sampler[list[int]]):
    """Mix task/action-balanced batches with regular monotonic severity pairs."""

    def __init__(self, rows: list[dict[str, Any]], seed: int, batches: int):
        self.rows, self.seed, self.batches = rows, seed, batches
        chains: dict[str, list[int]] = {}
        for index, row in enumerate(rows):
            chains.setdefault(row["severity_chain"], []).append(index)
        self.pairs = []
        for indices in chains.values():
            ordered = sorted(indices, key=lambda i: float(rows[i].get("severity_target", rows[i]["severity"])))
            if (len(ordered) > 1 and
                    rows[ordered[0]].get("severity_target", rows[ordered[0]]["severity"])
                    != rows[ordered[-1]].get("severity_target", rows[ordered[-1]]["severity"])):
                self.pairs.append((ordered[0], ordered[-1]))
        if not self.pairs:
            raise ValueError("no non-tied severity chains available for monotonic batches")
        task_counts = Counter(row["task"] for row in rows)
        action_counts = Counter(int(row["action_id"]) for row in rows)
        self.sample_weights = [
            0.5 / task_counts[row["task"]] + 0.5 / action_counts[int(row["action_id"])]
            for row in rows
        ]

    def __iter__(self):
        generator = random.Random(self.seed)
        population = list(range(len(self.rows)))
        for batch_index in range(self.batches):
            if batch_index % 4 == 0:
                yield list(generator.choice(self.pairs))
            else:
                yield generator.choices(population, weights=self.sample_weights, k=2)

    def __len__(self) -> int:
        return self.batches


class D3Heads(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.action = nn.Linear(hidden_size, len(ACTIONS))
        self.select = nn.Linear(hidden_size, 1)
        self.severity = nn.Linear(hidden_size, 1)
        self.pair = nn.Linear(hidden_size, 1)

    def forward(self, hidden: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        return (self.action(hidden), self.select(hidden).squeeze(-1),
                self.severity(hidden).squeeze(-1), self.pair(hidden).squeeze(-1))


def _images(row: dict[str, Any]) -> list[Image.Image]:
    images = []
    for value in row["images"]:
        path = Path(value)
        if not path.exists():
            for marker in ("/runs/", "/data/", "/release/"):
                if marker in value:
                    path = REPO / marker.strip("/") / value.split(marker, 1)[1]
                    break
        images.append(Image.open(path).convert("RGB"))
    return images


def make_collator(processor: Any):
    pad_id = processor.tokenizer.pad_token_id

    def collate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        texts, images, prompt_lengths = [], [], []
        for row in rows:
            prompt = processor.apply_chat_template(row["messages"][:1], tokenize=False,
                                                     add_generation_prompt=True)
            full = processor.apply_chat_template(row["messages"], tokenize=False,
                                                   add_generation_prompt=False)
            image_list = _images(row)
            prompt_inputs = processor(text=[prompt], images=image_list if image_list else None,
                                      return_tensors="pt")
            prompt_lengths.append(int(prompt_inputs["attention_mask"].sum()))
            texts.append(full)
            images.append(image_list)
        processor_images = images if any(images) else None
        encoded = processor(text=texts, images=processor_images, padding=True, return_tensors="pt")
        labels = encoded["input_ids"].clone()
        labels[labels == pad_id] = -100
        for index, length in enumerate(prompt_lengths):
            labels[index, :length] = -100
        encoded["labels"] = labels
        encoded["meta"] = rows
        encoded["prompt_lengths"] = torch.tensor(prompt_lengths, dtype=torch.long)
        return encoded
    return collate


def pooled_at_prompt(hidden: torch.Tensor, prompt_lengths: torch.Tensor) -> torch.Tensor:
    # Route/select heads must not see the gold assistant tokens during training.
    index = prompt_lengths.long().sub(1).clamp_min(0)
    return hidden[torch.arange(hidden.shape[0], device=hidden.device), index]


def per_record_lm_loss(logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Assistant-token CE for each record, retaining task-specific supervision."""
    shifted_logits = logits[:, :-1].contiguous()
    shifted_labels = labels[:, 1:].contiguous()
    token_loss = F.cross_entropy(shifted_logits.transpose(1, 2), shifted_labels,
                                 ignore_index=-100, reduction="none")
    valid = shifted_labels.ne(-100)
    return (token_loss * valid).sum(1) / valid.sum(1).clamp_min(1)


def _masked_mean(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    return values[mask].mean() if bool(mask.any()) else values.sum() * 0


def compute_joint_loss(lm_per_record: torch.Tensor, action_logits: torch.Tensor,
                       select_logits: torch.Tensor, severity_logits: torch.Tensor,
                       pair_logits: torch.Tensor,
                       rows: list[dict[str, Any]], weights: LossWeights,
                       route_class_weights: torch.Tensor | None = None,
                       ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    device = action_logits.device
    action = torch.tensor([row["action_id"] for row in rows], device=device)
    confidence = torch.tensor([row["target_confidence"] for row in rows], dtype=torch.float32, device=device)
    severity = torch.tensor([row.get("severity_target", row["severity"]) for row in rows],
                            dtype=torch.float32, device=device)
    # PyTorch's weighted mean divides by the observed class weight, which makes
    # weighting a no-op at batch_size=1. Apply the per-record multiplier after
    # unreduced CE so rare actions remain upweighted under the v2 configuration.
    route_per_record = F.cross_entropy(action_logits, action, reduction="none")
    if route_class_weights is not None:
        route_per_record = route_per_record * route_class_weights[action]
    route = route_per_record.mean()
    select = F.binary_cross_entropy_with_logits(select_logits, confidence.clamp(0, 1))
    severity_point = F.smooth_l1_loss(torch.sigmoid(severity_logits), severity.clamp(0, 1))
    # Explicit same-source monotonic ranking when a batch contains a severity chain.
    rank_terms = []
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if rows[left]["severity_chain"] != rows[right]["severity_chain"]:
                continue
            delta = severity[left] - severity[right]
            if delta.abs() > 1e-8:
                sign = delta.sign()
                rank_terms.append(F.relu(0.1 - sign * (severity_logits[left] - severity_logits[right])))
    severity_rank = (torch.stack(rank_terms).mean() if rank_terms
                     else severity_logits.sum() * 0)
    severity_loss = severity_point + severity_rank
    tasks = [row["task"] for row in rows]
    detect = _masked_mean(lm_per_record, torch.tensor([task == "detect" for task in tasks], device=device))
    distill = _masked_mean(lm_per_record, torch.tensor([task == "distill" for task in tasks], device=device))
    pair_mask = torch.tensor([row.get("pair_target") is not None for row in rows], device=device)
    if bool(pair_mask.any()):
        pair_target = torch.tensor([float(row.get("pair_target") or 0.0) for row in rows], device=device)
        pair = F.binary_cross_entropy_with_logits(pair_logits[pair_mask], pair_target[pair_mask])
    else:
        pair = pair_logits.sum() * 0
    losses = {"detect": detect, "distill": distill, "pair": pair,
              "severity": severity_loss, "route": route, "select": select,
              "severity_point": severity_point, "severity_rank": severity_rank}
    total = sum(float(getattr(weights, name)) * losses[name] for name in LOSS_NAMES)
    return total, losses


def save_checkpoint(model: nn.Module, heads: D3Heads | None, processor: Any, output: Path,
                    config: dict[str, Any], metrics: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output / "adapter")
    processor.save_pretrained(output / "adapter")
    if heads is not None:
        torch.save(heads.state_dict(), output / "d3_heads.pt")
    (output / "run_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False))
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--init-adapter", type=Path)
    parser.add_argument("--objective", choices=("d3", "vanilla"), default="d3",
                        help="d3 trains all auxiliary heads; vanilla trains only assistant-token SFT")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parent-commit")
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--dev-limit", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--severity-chain-sampling", action=argparse.BooleanOptionalAction,
                        default=False)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--image-max-pixels", type=int, default=589824)
    parser.add_argument("--quantization", choices=("qlora", "bf16"), default="qlora")
    parser.add_argument("--action-class-weighting", choices=("none", "sqrt-inverse", "inverse"),
                        default="sqrt-inverse")
    parser.add_argument("--action-balanced-sampling", action=argparse.BooleanOptionalAction,
                        default=True)
    for name in LOSS_NAMES:
        parser.add_argument(f"--loss-{name}", type=float, default=getattr(LossWeights(), name))
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True,
                                               max_pixels=args.image_max_pixels)
    model_kwargs: dict[str, Any] = {
        "torch_dtype": torch.bfloat16, "trust_remote_code": True,
        "attn_implementation": "sdpa", "low_cpu_mem_usage": True,
    }
    if args.quantization == "qlora":
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["device_map"] = {"": 0}
    model = Qwen3VLForConditionalGeneration.from_pretrained(args.model, **model_kwargs)
    if args.init_adapter:
        model = PeftModel.from_pretrained(model, args.init_adapter, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(
            r=args.lora_rank, lora_alpha=args.lora_alpha, lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            task_type="CAUSAL_LM",
        ))
    model.enable_input_require_grads()
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.quantization == "bf16":
        model.to(device)
    heads = None
    if args.objective == "d3":
        hidden_size = model.get_base_model().config.text_config.hidden_size
        heads = D3Heads(hidden_size).to(device=device, dtype=torch.float32)
    parameters = [p for p in model.parameters() if p.requires_grad]
    if heads is not None:
        parameters += list(heads.parameters())
    optimizer = torch.optim.AdamW(parameters, lr=args.learning_rate)
    weights = LossWeights(**{name: getattr(args, f"loss_{name}") for name in LOSS_NAMES})
    train = JsonlDataset(args.train, args.train_limit)
    dev = JsonlDataset(args.dev, args.dev_limit)
    if args.objective == "d3":
        route_weight_values = action_class_weights(train.rows, args.action_class_weighting)
        route_class_weights = torch.tensor(route_weight_values, dtype=torch.float32, device=device)
    else:
        route_weight_values = [1.0] * len(ACTIONS)
        route_class_weights = None
    sampler = None
    batch_sampler = None
    if args.severity_chain_sampling:
        if args.batch_size != 2:
            raise ValueError("--severity-chain-sampling requires --batch-size 2")
        batch_sampler = MixedObjectiveBatchSampler(train.rows, args.seed, args.max_steps)
    elif args.action_balanced_sampling and args.objective == "d3":
        generator = torch.Generator().manual_seed(args.seed)
        sampler = WeightedRandomSampler(action_sample_weights(train.rows), len(train),
                                        replacement=True, generator=generator)
    if batch_sampler is not None:
        loader = DataLoader(train, batch_sampler=batch_sampler, collate_fn=make_collator(processor))
    else:
        loader = DataLoader(train, batch_size=args.batch_size, shuffle=sampler is None, sampler=sampler,
                            collate_fn=make_collator(processor))
    history: list[dict[str, Any]] = []
    optimizer.zero_grad(set_to_none=True)
    model.train()
    if heads is not None:
        heads.train()
    step = 0
    epoch = 0
    while step < args.max_steps:
        epoch += 1
        for batch in loader:
            step += 1
            rows = batch.pop("meta")
            prompt_lengths = batch.pop("prompt_lengths").to(device)
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch, output_hidden_states=heads is not None, return_dict=True)
            lm_per_record = per_record_lm_loss(outputs.logits, batch["labels"])
            if heads is None:
                total = lm_per_record.mean()
                losses = {name: total.detach() * 0 for name in LOSS_NAMES}
            else:
                pooled = pooled_at_prompt(outputs.hidden_states[-1], prompt_lengths).float()
                action_logits, select_logits, severity_logits, pair_logits = heads(pooled)
                total, losses = compute_joint_loss(lm_per_record, action_logits, select_logits,
                                                   severity_logits, pair_logits, rows, weights,
                                                   route_class_weights)
            (total / args.gradient_accumulation).backward()
            if step % args.gradient_accumulation == 0 or step == args.max_steps:
                optimizer.step(); optimizer.zero_grad(set_to_none=True)
            item = {"step": step, "epoch": epoch, "total": float(total.detach()),
                    "lm": float(lm_per_record.mean().detach()),
                    **{name: float(loss.detach()) for name, loss in losses.items()}}
            history.append(item)
            print(json.dumps(item), flush=True)
            if step >= args.max_steps:
                break

    model.eval()
    if heads is not None:
        heads.eval()
    confusion = [[0 for _ in ACTIONS] for _ in ACTIONS]
    dev_loss_sums = Counter()
    dev_route_rows: list[dict[str, Any]] = []
    dev_loss, dev_seen = 0.0, 0
    with torch.no_grad():
        for batch in DataLoader(dev, batch_size=1, shuffle=False, collate_fn=make_collator(processor)):
            rows = batch.pop("meta")
            prompt_lengths = batch.pop("prompt_lengths").to(device)
            batch = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**batch, output_hidden_states=heads is not None, return_dict=True)
            lm_per_record = per_record_lm_loss(outputs.logits, batch["labels"])
            if heads is None:
                total = lm_per_record.mean()
                losses = {name: total.detach() * 0 for name in LOSS_NAMES}
            else:
                pooled = pooled_at_prompt(outputs.hidden_states[-1], prompt_lengths).float()
                action_logits, select_logits, severity_logits, pair_logits = heads(pooled)
                total, losses = compute_joint_loss(lm_per_record, action_logits, select_logits,
                                                   severity_logits, pair_logits, rows, weights,
                                                   route_class_weights)
                truth, pred = rows[0]["action_id"], int(action_logits.argmax(-1).item())
                confusion[truth][pred] += 1
                dev_route_rows.append({"defect": rows[0]["defect"],
                                       "availability": rows[0]["availability"],
                                       "truth": truth, "pred": pred})
            for name, loss in losses.items():
                dev_loss_sums[name] += float(loss)
            dev_loss += float(total); dev_seen += 1
    action_recall = {}
    for index, action in enumerate(ACTIONS):
        support = sum(confusion[index])
        action_recall[action] = confusion[index][index] / support if support else None
    g7_rows = [row for row in dev_route_rows if row["defect"].startswith("G7_")
               and row["availability"] == "image_only"]
    geometry_rows = [row for row in dev_route_rows
                     if row["defect"].split("_", 1)[0] in {"G2", "G3", "G4", "G5", "G6"}
                     and row["availability"] == "image_only"]
    metrics = {
        "history": history,
        "objective": args.objective,
        "dev_joint_loss": dev_loss / max(dev_seen, 1),
        "dev_sub_losses": {name: value / max(dev_seen, 1)
                           for name, value in sorted(dev_loss_sums.items())},
        "dev_records": dev_seen,
        "action_labels": list(ACTIONS),
        "action_confusion": confusion,
        "action_recall": action_recall,
        "g7_generic_answer_recall": (
            sum(row["pred"] == ACTIONS.index("ANSWER") for row in g7_rows) / len(g7_rows)
            if g7_rows else None),
        "g2_g6_image_only_unsafe_answer_rate": (
            sum(row["pred"] == ACTIONS.index("ANSWER") for row in geometry_rows) / len(geometry_rows)
            if geometry_rows else None),
        "dev_selection_basis": ("minimum dev_joint_loss; no validation or final_test read"
                                if heads is not None else
                                "minimum assistant-token dev SFT loss; no validation or final_test read"),
    }
    if args.parent_commit:
        parent = args.parent_commit
    else:
        try:
            parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
                                             stderr=subprocess.DEVNULL).strip()
        except Exception:
            parent = "unavailable"
    config = {"parent_commit": parent, "base_model": args.model, "seed": args.seed,
              "objective": args.objective,
              "max_steps": args.max_steps, "train_sha256": sha256_file(args.train),
              "dev_sha256": sha256_file(args.dev), "loss_weights": asdict(weights),
              "action_class_weighting": args.action_class_weighting,
              "action_class_weights": dict(zip(ACTIONS, route_weight_values, strict=True)),
              "action_balanced_sampling": args.action_balanced_sampling,
              "severity_chain_sampling": args.severity_chain_sampling,
              "quantization": args.quantization, "init_adapter": str(args.init_adapter) if args.init_adapter else None}
    save_checkpoint(model, heads, processor, args.output, config, metrics)
    print(json.dumps({"saved": str(args.output), **metrics}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
