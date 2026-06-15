from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .examiner_contract import (
    DeckExamResult,
    ExamLevel,
    Modality,
    PageExamResult,
    PairwiseChoice,
    PairwiseResult,
    build_messages_from_sample,
    page_result_from_labels,
    result_from_sample,
)
from .schemas import DefectLabel, ManifestSample


def answer_from_labels(labels: Iterable[DefectLabel]) -> dict:
    """Compatibility helper returning a contract-shaped result body.

    The historical API accepted labels only, so it cannot know page/deck ids. Use
    ``page_result_from_labels`` / ``deck_result_from_labels`` for full samples.
    """

    manifest = ManifestSample(sample_id="sample", labels=tuple(labels))
    return page_result_from_labels(manifest).model_dump(mode="json")


def build_pointwise_record(sample: ManifestSample | dict) -> dict:
    manifest = ManifestSample.from_mapping(sample)
    modality = _modality_for_sample(manifest)
    messages = build_messages_from_sample(manifest, modality=modality)
    target = result_from_sample(manifest)
    return {
        "sample_id": manifest.sample_id,
        "exam_level": target.__class__.__name__,
        "modality": modality.value,
        "messages": _messages_with_assistant(messages, _json_text(target)),
    }


def build_pairwise_record(sample: ManifestSample | dict) -> dict:
    manifest = ManifestSample.from_mapping(sample)
    pair = manifest.pair or {}
    target = result_from_sample(manifest)
    level = ExamLevel.DECK if isinstance(target, DeckExamResult) else ExamLevel.PAGE
    subject_id = target.deck_id if isinstance(target, DeckExamResult) else target.page_id
    answer = PairwiseResult(
        level=level,
        subject_id=subject_id,
        better=PairwiseChoice.TIE if not target.has_defect else PairwiseChoice.A,
        reason="A is the clean/reference candidate; B contains the injected defect." if target.has_defect else "Both candidates are clean.",
    )
    clean_image = pair.get("clean_image_path", manifest.metadata.get("clean_image_path", ""))
    defective_image = pair.get("defective_image_path", manifest.image_path or "")
    user_text = "Compare candidate A and candidate B for slide quality. Output ONLY PairwiseResult JSON."
    return {
        "sample_id": manifest.sample_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": clean_image},
                    {"type": "image", "image": defective_image},
                    {"type": "text", "text": user_text},
                ],
            },
            {"role": "assistant", "content": [{"type": "text", "text": _json_text(answer)}]},
        ],
    }


def export_sft_jsonl(
    samples: Iterable[ManifestSample | dict],
    output_path: str | Path,
    *,
    mode: str = "pointwise",
) -> int:
    builders = {"pointwise": build_pointwise_record, "pairwise": build_pairwise_record}
    if mode not in builders:
        raise ValueError(f"Unsupported SFT export mode: {mode}")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(builders[mode](sample), ensure_ascii=False) + "\n")
            count += 1
    return count


def build_llamafactory_record(sample: ManifestSample | dict) -> dict | None:
    """Build a LLaMA-Factory ``sharegpt``+images record using the I/O contract."""

    manifest = ManifestSample.from_mapping(sample)
    image = manifest.image_path or manifest.metadata.get("defective_image_path")
    modality = _modality_for_sample(manifest)
    contract_messages = build_messages_from_sample(manifest, modality=modality)
    target = result_from_sample(manifest)
    user_content = _sharegpt_user_content(contract_messages)
    if not image:
        return None
    if "<image>" not in user_content:
        user_content = f"<image>\n{user_content}"
    return {"messages": [{"role": "user", "content": user_content}, {"role": "assistant", "content": _json_text(target)}], "images": [str(image)]}


def write_llamafactory_dataset_info(
    jsonl_path: str | Path,
    *,
    dataset_name: str = "slide_examiner",
    info_path: str | Path | None = None,
) -> Path:
    """Write/merge a LLaMA-Factory ``dataset_info.json`` entry for the export."""

    jsonl_path = Path(jsonl_path)
    info = Path(info_path) if info_path else jsonl_path.parent / "dataset_info.json"
    entry = {
        dataset_name: {
            "file_name": jsonl_path.name,
            "formatting": "sharegpt",
            "columns": {"messages": "messages", "images": "images"},
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
            },
        }
    }
    existing: dict = {}
    if info.exists():
        try:
            existing = json.loads(info.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing.update(entry)
    info.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def export_llamafactory_jsonl(
    samples: Iterable[ManifestSample | dict],
    output_path: str | Path,
    *,
    dataset_name: str = "slide_examiner",
    write_info: bool = True,
) -> int:
    """Export a LLaMA-Factory multimodal SFT dataset and its dataset_info entry."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            record = build_llamafactory_record(sample)
            if record is None:
                continue
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    if write_info:
        write_llamafactory_dataset_info(path, dataset_name=dataset_name)
    return count


def _modality_for_sample(manifest: ManifestSample) -> Modality:
    image = manifest.image_path or manifest.metadata.get("defective_image_path")
    return Modality.C_BOTH if image and Path(str(image)).exists() else Modality.B_STRUCT_ONLY


def _messages_with_assistant(messages: list[dict], assistant_json: str) -> list[dict]:
    return [*messages, {"role": "assistant", "content": [{"type": "text", "text": assistant_json}]}]


def _json_text(result: PageExamResult | DeckExamResult | PairwiseResult) -> str:
    return result.model_dump_json()


def _sharegpt_user_content(messages: list[dict]) -> str:
    parts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        for item in message.get("content", []):
            if item.get("type") == "image_url":
                parts.append("<image>")
            elif item.get("type") == "text":
                parts.append(str(item.get("text", "")))
    return "\n".join(part for part in parts if part)
