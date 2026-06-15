from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .adapters import MockAdapter
from .io import read_jsonl, write_jsonl
from .matrix import ExperimentMatrix
from .model_adapters import JSONLReplayAdapter, OpenAICompatibleAdapter, OpenAICompatibleConfig, QwenVLConfig, QwenVLTransformersAdapter
from .probe import ProbeRunConfig, ProbeRunner
from .schemas import ManifestSample


@dataclass(frozen=True)
class MatrixRunConfig:
    adapter: str = "mock"
    model: str | None = None
    replay_path: str | None = None
    base_url: str | None = None
    limit: int | None = None


def run_matrix(
    manifest_path: str | Path,
    matrix_path: str | Path,
    output_path: str | Path,
    *,
    config: MatrixRunConfig | None = None,
) -> list[dict]:
    cfg = config or MatrixRunConfig()
    samples = [ManifestSample.from_mapping(item) for item in read_jsonl(manifest_path)]
    matrix_records = _matrix_records(matrix_path)
    if cfg.limit is not None:
        matrix_records = matrix_records[: cfg.limit]

    all_records: list[dict] = []
    for cell in matrix_records:
        adapter = _adapter_for(cfg, cell)
        selected_samples = [_with_cell_metadata(sample, cell) for sample in samples]
        runner = ProbeRunner(adapter, ProbeRunConfig(modalities=(cell["modality"],), tasks=(cell["task"],)))
        records = runner.run(selected_samples)
        for record in records:
            record.update(
                {
                    "model": cell["model"],
                    "resolution": cell["resolution"],
                    "seed": cell["seed"],
                    "template_condition": cell["template_condition"],
                }
            )
        all_records.extend(records)
    write_jsonl(all_records, output_path)
    return all_records


def write_default_matrix(path: str | Path) -> Path:
    from .matrix import write_matrix_json

    return write_matrix_json(ExperimentMatrix(), path)


def _matrix_records(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("records", []))


def _adapter_for(config: MatrixRunConfig, cell: dict):
    if config.adapter == "mock":
        return MockAdapter(name=str(cell["model"]))
    if config.adapter == "replay":
        if not config.replay_path:
            raise ValueError("replay_path is required for replay adapter")
        return JSONLReplayAdapter(config.replay_path)
    if config.adapter == "qwen-local":
        return QwenVLTransformersAdapter(QwenVLConfig(model_id=config.model or str(cell["model"])))
    if config.adapter == "openai":
        return OpenAICompatibleAdapter(OpenAICompatibleConfig(model=config.model or str(cell["model"]), base_url=config.base_url))
    raise ValueError(f"Unsupported matrix adapter: {config.adapter}")


def _with_cell_metadata(sample: ManifestSample, cell: dict) -> ManifestSample:
    from dataclasses import replace

    metadata = {
        **sample.metadata,
        "template_condition": cell["template_condition"],
        "resolution": cell["resolution"],
        "seed": cell["seed"],
        "matrix_model": cell["model"],
    }
    return replace(sample, metadata=metadata)

