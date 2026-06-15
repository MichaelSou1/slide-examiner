from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrainingConfig:
    model_name_or_path: str = "Qwen/Qwen3-VL-8B-Instruct"
    train_jsonl: str = "data/sft_pointwise.jsonl"
    output_dir: str = "models/qwen3-vl-8b-examiner-lora"
    finetune_backend: str = "qwen-vl-finetune"
    learning_rate: float = 2e-5
    num_train_epochs: float = 1.0
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    lora_rank: int = 16

    def to_dict(self) -> dict:
        return {
            "model_name_or_path": self.model_name_or_path,
            "train_jsonl": self.train_jsonl,
            "output_dir": self.output_dir,
            "finetune_backend": self.finetune_backend,
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "lora_rank": self.lora_rank,
        }


def write_training_config(config: TrainingConfig, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    return output


def build_training_command(config: TrainingConfig) -> list[str]:
    return [
        "python",
        "-m",
        config.finetune_backend,
        "--model_name_or_path",
        config.model_name_or_path,
        "--data_path",
        config.train_jsonl,
        "--output_dir",
        config.output_dir,
        "--learning_rate",
        str(config.learning_rate),
        "--num_train_epochs",
        str(config.num_train_epochs),
        "--per_device_train_batch_size",
        str(config.per_device_train_batch_size),
        "--gradient_accumulation_steps",
        str(config.gradient_accumulation_steps),
        "--lora_rank",
        str(config.lora_rank),
    ]


def run_training(config: TrainingConfig, *, dry_run: bool = True) -> dict:
    command = build_training_command(config)
    if dry_run:
        return {"dry_run": True, "command": command, "config": config.to_dict()}
    if shutil.which("python") is None:
        raise RuntimeError("Python executable not found")
    result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "dry_run": False,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

