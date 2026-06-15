from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .adapters import (
    ExaminerAdapter,
    build_probe_payload,
)
from .schemas import ManifestSample


@dataclass(frozen=True)
class ProbeRunConfig:
    modalities: tuple[str, ...] = ("A", "B", "Bprime", "C")
    tasks: tuple[str, ...] = ("T1", "T2", "T3")


class ProbeRunner:
    def __init__(self, adapter: ExaminerAdapter, config: ProbeRunConfig | None = None) -> None:
        self.adapter = adapter
        self.config = config or ProbeRunConfig()

    def run(self, samples: Iterable[ManifestSample | dict]) -> list[dict]:
        records: list[dict] = []
        for raw_sample in samples:
            sample = ManifestSample.from_mapping(raw_sample)
            for modality in self.config.modalities:
                for task in self.config.tasks:
                    payload = build_probe_payload(sample, modality=modality, task=task)
                    output = self.adapter.examine(payload)
                    records.append(
                        {
                            "sample_id": sample.sample_id,
                            "model": getattr(self.adapter, "name", self.adapter.__class__.__name__),
                            "modality": modality,
                            "task": task,
                            "output": output,
                            "labels": [label.to_dict() for label in sample.labels],
                            "label_types": [label.type for label in sample.labels],
                            "metadata": sample.metadata,
                            "template_condition": sample.metadata.get("template_condition"),
                        }
                    )
        return records

    def run_jsonl(self, samples: Iterable[ManifestSample | dict], output_path: str | Path) -> list[dict]:
        records = self.run(samples)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return records
