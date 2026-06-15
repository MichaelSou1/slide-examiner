from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

from .adapters import MODALITIES, TASKS


@dataclass(frozen=True)
class ExperimentMatrix:
    models: tuple[str, ...] = ("qwen3-vl-4b", "qwen3-vl-8b", "qwen3-vl-32b", "qwen3-vl-30b-a3b")
    modalities: tuple[str, ...] = MODALITIES
    tasks: tuple[str, ...] = TASKS
    template_conditions: tuple[str, ...] = ("freeform", "template")
    resolutions: tuple[int, ...] = (768, 1024, 1536, 2048)
    seeds: tuple[int, ...] = (0, 1, 2)
    metadata: dict = field(default_factory=dict)

    def records(self) -> list[dict]:
        return [
            {
                "model": model,
                "modality": modality,
                "task": task,
                "template_condition": template_condition,
                "resolution": resolution,
                "seed": seed,
            }
            for model, modality, task, template_condition, resolution, seed in product(
                self.models,
                self.modalities,
                self.tasks,
                self.template_conditions,
                self.resolutions,
                self.seeds,
            )
        ]

    def to_dict(self) -> dict:
        return {
            "models": list(self.models),
            "modalities": list(self.modalities),
            "tasks": list(self.tasks),
            "template_conditions": list(self.template_conditions),
            "resolutions": list(self.resolutions),
            "seeds": list(self.seeds),
            "metadata": self.metadata,
            "planned_cells": len(self.records()),
        }


def write_matrix_json(matrix: ExperimentMatrix, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"matrix": matrix.to_dict(), "records": matrix.records()}, indent=2), encoding="utf-8")
    return output

