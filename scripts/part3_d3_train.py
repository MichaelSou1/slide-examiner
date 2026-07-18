#!/usr/bin/env python3
"""Train the D3 critic with multimodal SFT and explicit route/select/severity heads."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
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
    is_optimizer_boundary, mixed_objective_batches, resume_config_mismatches,
)

REPO = Path(__file__).resolve().parents[1]
FROZEN_TRAIN_SHA256 = "8d283c67f87ee5d4552a220753009dd933b8f9365a4a1fc854b85414a400a6a5"
FROZEN_DEV_SHA256 = "132858199082f0e50320618bbd0b059bbf8fa27d72afcae56c84d628902a472a"


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

    def __init__(self, rows: list[dict[str, Any]], seed: int, batches: int,
                 start_batch: int = 0):
        self.rows, self.seed, self.batches = rows, seed, batches
        self.start_batch = start_batch
        # Validate the rows eagerly rather than failing in the DataLoader worker.
        next(iter(mixed_objective_batches(rows, seed, 1)))

    def __iter__(self):
        # Recreate the same deterministic stream and discard already-consumed
        # batches so a resumed run sees exactly the uninterrupted next batch.
        yield from mixed_objective_batches(
            self.rows, self.seed, self.batches, start_batch=self.start_batch)

    def __len__(self) -> int:
        return max(0, self.batches - self.start_batch)


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

    def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Accept both OpenAI multimodal parts and legacy LF ``<image>`` strings."""
        normalized = []
        for message in messages:
            content = message.get("content", "")
            if not isinstance(content, str) or "<image>" not in content:
                normalized.append(message)
                continue
            parts: list[dict[str, str]] = []
            chunks = content.split("<image>")
            for index, chunk in enumerate(chunks):
                if index:
                    parts.append({"type": "image"})
                if chunk:
                    parts.append({"type": "text", "text": chunk})
            normalized.append({**message, "content": parts})
        return normalized

    def collate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        texts, images, prompt_lengths = [], [], []
        for row in rows:
            messages = normalize_messages(row["messages"])
            prompt = processor.apply_chat_template(messages[:1], tokenize=False,
                                                     add_generation_prompt=True)
            full = processor.apply_chat_template(messages, tokenize=False,
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


def _write_json(path: Path, value: Any) -> None:
    """Atomically replace small run metadata so interrupted writes stay detectable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def write_sha256_inventory(output: Path) -> dict[str, Any]:
    """Hash every checkpoint artifact except the inventory itself."""
    inventory_path = output / "sha256_inventory.json"
    files = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path == inventory_path or path.name.startswith(".sha256_inventory.json"):
            continue
        files.append({"path": path.relative_to(output).as_posix(),
                      "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    inventory = {"algorithm": "sha256", "root": str(output), "files": files}
    _write_json(inventory_path, inventory)
    return inventory


def save_checkpoint(model: nn.Module, heads: D3Heads | None, processor: Any, output: Path,
                    optimizer: torch.optim.Optimizer, scheduler: Any,
                    config: dict[str, Any], trainer_state: dict[str, Any],
                    metrics: dict[str, Any] | None = None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output / "adapter")
    processor.save_pretrained(output / "adapter")
    if heads is not None:
        torch.save(heads.state_dict(), output / "d3_heads.pt")
    torch.save(optimizer.state_dict(), output / "optimizer.pt")
    torch.save(scheduler.state_dict(), output / "scheduler.pt")
    rng_state = {"python": random.getstate(), "torch": torch.get_rng_state()}
    if torch.cuda.is_available():
        rng_state["cuda"] = torch.cuda.get_rng_state_all()
    torch.save(rng_state, output / "rng_state.pt")
    _write_json(output / "run_config.json", config)
    _write_json(output / "trainer_state.json", trainer_state)
    history = trainer_state.get("history", [])
    history_text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in history)
    history_path = output / "train_history.jsonl"
    history_temporary = history_path.with_name(f".{history_path.name}.tmp")
    history_temporary.write_text(history_text)
    os.replace(history_temporary, history_path)
    if metrics is not None:
        _write_json(output / "metrics.json", metrics)
    write_sha256_inventory(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="/home/nvme04/models/Qwen3-VL-8B-Instruct")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--init-adapter", type=Path)
    parser.add_argument("--init-heads", type=Path,
                        help="load an existing D3 auxiliary-head state (for continuation or eval-only max-steps=0)")
    parser.add_argument("--objective", choices=("d3", "vanilla"), default="d3",
                        help="d3 trains all auxiliary heads; vanilla trains only assistant-token SFT")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parent-commit")
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--dev-limit", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--scheduler", choices=("constant", "linear"), default="constant")
    parser.add_argument("--warmup-steps", type=int, default=0)
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--severity-chain-sampling", action=argparse.BooleanOptionalAction,
                        default=False)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--image-max-pixels", type=int, default=589824)
    parser.add_argument("--save-steps", type=int, default=0,
                        help="save a resumable checkpoint-N snapshot every N optimizer steps; 0 disables")
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--allow-nonfrozen-data", action="store_true",
                        help="explicitly allow hashes other than the frozen W7.3 train/dev pair (smoke only)")
    parser.add_argument("--quantization", choices=("qlora", "bf16"), default="qlora")
    parser.add_argument("--action-class-weighting", choices=("none", "sqrt-inverse", "inverse"),
                        default="sqrt-inverse")
    parser.add_argument("--action-balanced-sampling", action=argparse.BooleanOptionalAction,
                        default=True)
    for name in LOSS_NAMES:
        parser.add_argument(f"--loss-{name}", type=float, default=getattr(LossWeights(), name))
    args = parser.parse_args()

    if args.resume_from_checkpoint and (args.init_adapter or args.init_heads):
        raise ValueError("--resume-from-checkpoint cannot be combined with --init-adapter/--init-heads")
    if args.save_steps < 0:
        raise ValueError("--save-steps must be non-negative")
    train_sha256, dev_sha256 = sha256_file(args.train), sha256_file(args.dev)
    if not args.allow_nonfrozen_data and (train_sha256, dev_sha256) != (
            FROZEN_TRAIN_SHA256, FROZEN_DEV_SHA256):
        raise ValueError(
            "refusing non-frozen W7.3 data: "
            f"train={train_sha256} dev={dev_sha256}; pass --allow-nonfrozen-data only for smoke runs")

    if args.parent_commit:
        parent = args.parent_commit
    else:
        try:
            parent = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True,
                                             stderr=subprocess.DEVNULL).strip()
        except Exception:
            parent = "unavailable"

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
    resume_adapter = args.resume_from_checkpoint / "adapter" if args.resume_from_checkpoint else None
    if resume_adapter or args.init_adapter:
        model = PeftModel.from_pretrained(model, resume_adapter or args.init_adapter, is_trainable=True)
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
        heads_state = (args.resume_from_checkpoint / "d3_heads.pt"
                       if args.resume_from_checkpoint else args.init_heads)
        if heads_state:
            heads.load_state_dict(torch.load(heads_state, map_location=device, weights_only=True))
    elif args.init_heads:
        raise ValueError("--init-heads is only valid with --objective d3")
    parameters = [p for p in model.parameters() if p.requires_grad]
    if heads is not None:
        parameters += list(heads.parameters())
    optimizer = torch.optim.AdamW(parameters, lr=args.learning_rate)
    if args.scheduler == "constant":
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _: 1.0)
    else:
        def lr_factor(current_step: int) -> float:
            if args.warmup_steps and current_step < args.warmup_steps:
                return current_step / max(args.warmup_steps, 1)
            return max(0.0, (args.max_steps - current_step)
                       / max(args.max_steps - args.warmup_steps, 1))
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_factor)
    weights = LossWeights(**{name: getattr(args, f"loss_{name}") for name in LOSS_NAMES})
    train = JsonlDataset(args.train, args.train_limit)
    dev = JsonlDataset(args.dev, args.dev_limit)
    if args.objective == "d3":
        route_weight_values = action_class_weights(train.rows, args.action_class_weighting)
        route_class_weights = torch.tensor(route_weight_values, dtype=torch.float32, device=device)
    else:
        route_weight_values = [1.0] * len(ACTIONS)
        route_class_weights = None
    resume_state: dict[str, Any] = {}
    if args.resume_from_checkpoint:
        resume_state = json.loads((args.resume_from_checkpoint / "trainer_state.json").read_text())
        resume_config = json.loads((args.resume_from_checkpoint / "run_config.json").read_text())
        immutable_resume_fields = {
            "base_model": args.model, "seed": args.seed, "objective": args.objective,
            "max_steps": args.max_steps, "batch_size": args.batch_size,
            "gradient_accumulation": args.gradient_accumulation,
            "learning_rate": args.learning_rate, "scheduler": args.scheduler,
            "warmup_steps": args.warmup_steps,
            "lora_rank": args.lora_rank, "lora_alpha": args.lora_alpha,
            "image_max_pixels": args.image_max_pixels,
            "train_sha256": train_sha256, "dev_sha256": dev_sha256,
            "quantization": args.quantization,
            "loss_weights": asdict(weights),
            "severity_chain_sampling": args.severity_chain_sampling,
            "action_class_weighting": args.action_class_weighting,
            "action_balanced_sampling": args.action_balanced_sampling,
            "dev_limit": args.dev_limit, "train_limit": args.train_limit,
            "save_steps": args.save_steps, "parent_commit": parent,
        }
        mismatches = resume_config_mismatches(resume_config, immutable_resume_fields)
        if mismatches:
            raise ValueError(f"resume configuration mismatch: {mismatches}")
        if not args.severity_chain_sampling:
            raise ValueError(
                "exact resume currently requires --severity-chain-sampling; "
                "shuffle/weighted sampler state is not replay-safe")

    sampler = None
    batch_sampler = None
    consumed_batches = int(resume_state.get("global_step", 0)) * args.gradient_accumulation
    total_batches = args.max_steps * args.gradient_accumulation
    if args.severity_chain_sampling:
        if args.batch_size != 2:
            raise ValueError("--severity-chain-sampling requires --batch-size 2")
        batch_sampler = MixedObjectiveBatchSampler(
            train.rows, args.seed, total_batches, start_batch=consumed_batches)
    elif args.action_balanced_sampling and args.objective == "d3":
        generator = torch.Generator().manual_seed(args.seed)
        sampler = WeightedRandomSampler(action_sample_weights(train.rows), len(train),
                                        replacement=True, generator=generator)
    if batch_sampler is not None:
        loader = DataLoader(
            train, batch_sampler=batch_sampler, collate_fn=make_collator(processor),
            generator=torch.Generator().manual_seed(args.seed),
        )
    else:
        loader = DataLoader(train, batch_size=args.batch_size, shuffle=sampler is None, sampler=sampler,
                            collate_fn=make_collator(processor),
                            generator=torch.Generator().manual_seed(args.seed))
    history: list[dict[str, Any]] = []
    step = 0
    micro_step = 0
    epoch = 0
    if args.resume_from_checkpoint:
        step, epoch = int(resume_state["global_step"]), int(resume_state.get("epoch", 0))
        micro_step = int(resume_state.get("micro_step", consumed_batches))
        if micro_step != step * args.gradient_accumulation:
            raise ValueError(
                "resume checkpoint ends inside an accumulation window: "
                f"global_step={step} micro_step={micro_step} "
                f"gradient_accumulation={args.gradient_accumulation}")
        history = list(resume_state.get("history", []))
        optimizer.load_state_dict(torch.load(args.resume_from_checkpoint / "optimizer.pt",
                                             map_location=device, weights_only=False))
        scheduler.load_state_dict(torch.load(args.resume_from_checkpoint / "scheduler.pt",
                                             map_location=device, weights_only=False))
        rng_state = torch.load(args.resume_from_checkpoint / "rng_state.pt",
                               map_location="cpu", weights_only=False)
        random.setstate(rng_state["python"])
        torch.set_rng_state(rng_state["torch"])
        if torch.cuda.is_available() and "cuda" in rng_state:
            torch.cuda.set_rng_state_all(rng_state["cuda"])
    optimizer.zero_grad(set_to_none=True)
    model.train()
    if heads is not None:
        heads.train()
    run_started_at = time.time()
    previous_elapsed_seconds = float(resume_state.get("elapsed_seconds", 0.0))

    def trainer_state() -> dict[str, Any]:
        return {"global_step": step, "micro_step": micro_step,
                "epoch": epoch, "max_steps": args.max_steps,
                "history": history,
                "elapsed_seconds": previous_elapsed_seconds + time.time() - run_started_at,
                "resume_from_checkpoint": (str(args.resume_from_checkpoint)
                                           if args.resume_from_checkpoint else None)}

    def checkpoint_config() -> dict[str, Any]:
        return {"base_model": args.model, "seed": args.seed, "objective": args.objective,
                "max_steps": args.max_steps, "learning_rate": args.learning_rate,
                "scheduler": args.scheduler, "warmup_steps": args.warmup_steps,
                "batch_size": args.batch_size,
                "gradient_accumulation": args.gradient_accumulation,
                "lora_rank": args.lora_rank, "lora_alpha": args.lora_alpha,
                "image_max_pixels": args.image_max_pixels,
                "train_sha256": train_sha256, "dev_sha256": dev_sha256,
                "loss_weights": asdict(weights), "quantization": args.quantization,
                "severity_chain_sampling": args.severity_chain_sampling,
                "action_class_weighting": args.action_class_weighting,
                "action_balanced_sampling": args.action_balanced_sampling,
                "dev_limit": args.dev_limit, "train_limit": args.train_limit,
                "save_steps": args.save_steps, "parent_commit": parent,
                "final_test_read": False}

    while step < args.max_steps:
        epoch += 1
        for batch in loader:
            micro_step += 1
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
            if not is_optimizer_boundary(micro_step, args.gradient_accumulation):
                continue
            learning_rate = optimizer.param_groups[0]["lr"]
            optimizer.step(); scheduler.step(); optimizer.zero_grad(set_to_none=True)
            step += 1
            item = {"step": step, "micro_step": micro_step, "epoch": epoch,
                    "total": float(total.detach()),
                    "lm": float(lm_per_record.mean().detach()),
                    **{name: float(loss.detach()) for name, loss in losses.items()}}
            item["learning_rate"] = learning_rate
            history.append(item)
            print(json.dumps(item), flush=True)
            if args.save_steps and step % args.save_steps == 0:
                save_checkpoint(model, heads, processor, args.output / f"checkpoint-{step}",
                                optimizer, scheduler, checkpoint_config(), trainer_state())
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
    config = {**checkpoint_config(), "parent_commit": parent,
              "action_class_weighting": args.action_class_weighting,
              "action_class_weights": dict(zip(ACTIONS, route_weight_values, strict=True)),
              "action_balanced_sampling": args.action_balanced_sampling,
              "severity_chain_sampling": args.severity_chain_sampling,
              "init_adapter": str(args.init_adapter) if args.init_adapter else None,
              "init_heads": str(args.init_heads) if args.init_heads else None,
              "resume_from_checkpoint": (str(args.resume_from_checkpoint)
                                         if args.resume_from_checkpoint else None),
              "save_steps": args.save_steps,
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "torch": torch.__version__,
                              "transformers": __import__("transformers").__version__,
                              "peft": __import__("peft").__version__,
                              "cuda": torch.version.cuda,
                              "visible_gpus": os.environ.get("CUDA_VISIBLE_DEVICES"),
                              "gpu_names": ([torch.cuda.get_device_name(index)
                                             for index in range(torch.cuda.device_count())]
                                            if torch.cuda.is_available() else [])}}
    save_checkpoint(model, heads, processor, args.output, optimizer, scheduler,
                    config, trainer_state(), metrics)
    print(json.dumps({"saved": str(args.output), **metrics}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
