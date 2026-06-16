from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .examiner_contract import (
    DeckExamResult,
    ExamLevel,
    Modality,
    PageExamResult,
    PairwiseChoice,
    PairwiseResult,
    build_deck_messages,
    build_page_messages,
    build_messages_from_sample,
    deck_request_from_sample,
    image_content_from_path,
    page_result_from_labels,
    page_request_from_sample,
    parse_deck_result,
    parse_page_result,
    result_from_sample,
)
from .schemas import DefectLabel, ManifestSample


@dataclass(frozen=True)
class SFTExportStats:
    """Parseability and modality summary for an exported SFT JSONL file."""

    record_count: int
    parse_failures: int
    modality_counts: dict[str, int]
    parse_failure_examples: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "parse_failures": self.parse_failures,
            "modality_counts": self.modality_counts,
            "parse_failure_examples": self.parse_failure_examples,
        }


def answer_from_labels(labels: Iterable[DefectLabel]) -> dict:
    """Compatibility helper returning a contract-shaped result body.

    The historical API accepted labels only, so it cannot know page/deck ids. Use
    ``page_result_from_labels`` / ``deck_result_from_labels`` for full samples.
    """

    manifest = ManifestSample(sample_id="sample", labels=tuple(labels))
    return page_result_from_labels(manifest).model_dump(mode="json")


def build_pointwise_record(sample: ManifestSample | dict, *, modality: Modality | str | None = None) -> dict:
    manifest = ManifestSample.from_mapping(sample)
    selected_modality = _modality_for_sample(manifest, requested=modality)
    request = _pointwise_request(manifest, selected_modality)
    messages = build_deck_messages(request) if request.level == ExamLevel.DECK else build_page_messages(request)
    target = result_from_sample(manifest)
    return {
        "sample_id": manifest.sample_id,
        "exam_level": target.__class__.__name__,
        "modality": selected_modality.value,
        "metadata": _record_metadata(manifest, selected_modality),
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
    user_text = _pairwise_user_text(manifest)
    content = []
    if clean_image:
        content.append(image_content_from_path(clean_image))
    if defective_image:
        content.append(image_content_from_path(defective_image))
    content.append({"type": "text", "text": user_text})
    return {
        "sample_id": manifest.sample_id,
        "exam_level": "PairwiseResult",
        "modality": Modality.A_IMAGE_ONLY.value,
        "metadata": _record_metadata(manifest, Modality.A_IMAGE_ONLY, mode="pairwise"),
        "messages": [
            {
                "role": "user",
                "content": content,
            },
            {"role": "assistant", "content": [{"type": "text", "text": _json_text(answer)}]},
        ],
    }


def export_sft_jsonl(
    samples: Iterable[ManifestSample | dict],
    output_path: str | Path,
    *,
    mode: str = "pointwise",
    min_a_image_only_ratio: float = 0.30,
    b_struct_ratio: float = 0.35,
    c_both_ratio: float = 0.35,
    parse_summary_path: str | Path | None = None,
) -> int:
    return export_sft_jsonl_with_stats(
        samples,
        output_path,
        mode=mode,
        min_a_image_only_ratio=min_a_image_only_ratio,
        b_struct_ratio=b_struct_ratio,
        c_both_ratio=c_both_ratio,
        parse_summary_path=parse_summary_path,
    ).record_count


def export_sft_jsonl_with_stats(
    samples: Iterable[ManifestSample | dict],
    output_path: str | Path,
    *,
    mode: str = "pointwise",
    min_a_image_only_ratio: float = 0.30,
    b_struct_ratio: float = 0.35,
    c_both_ratio: float = 0.35,
    parse_summary_path: str | Path | None = None,
) -> SFTExportStats:
    if mode not in {"pointwise", "pairwise"}:
        raise ValueError(f"Unsupported SFT export mode: {mode}")
    manifest_samples = [ManifestSample.from_mapping(sample) for sample in samples]
    modalities = (
        _assign_modalities(
            manifest_samples,
            min_a_image_only_ratio=min_a_image_only_ratio,
            b_struct_ratio=b_struct_ratio,
            c_both_ratio=c_both_ratio,
        )
        if mode == "pointwise"
        else []
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    modality_counts = {item.value: 0 for item in Modality}
    parse_failure_examples: list[dict[str, str]] = []
    with path.open("w", encoding="utf-8") as handle:
        for index, sample in enumerate(manifest_samples):
            record = (
                build_pointwise_record(sample, modality=modalities[index])
                if mode == "pointwise"
                else build_pairwise_record(sample)
            )
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            modality_counts[record["modality"]] = modality_counts.get(record["modality"], 0) + 1
            try:
                parse_sft_assistant(record)
            except Exception as exc:  # pragma: no cover - retained for external malformed inputs.
                parse_failure_examples.append({"sample_id": record.get("sample_id", ""), "error": str(exc)})

    stats = SFTExportStats(
        record_count=len(manifest_samples),
        parse_failures=len(parse_failure_examples),
        modality_counts={key: value for key, value in modality_counts.items() if value},
        parse_failure_examples=parse_failure_examples[:20],
    )
    if parse_summary_path:
        summary_path = Path(parse_summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def parse_sft_assistant(record: dict[str, Any]) -> PageExamResult | DeckExamResult | PairwiseResult:
    """Parse one exported assistant JSON back through the contract models."""

    assistant_text = _assistant_text(record)
    exam_level = record.get("exam_level")
    if exam_level == "PairwiseResult":
        return PairwiseResult.model_validate_json(assistant_text)
    if exam_level == "DeckExamResult":
        return parse_deck_result(assistant_text)
    if exam_level == "PageExamResult":
        return parse_page_result(assistant_text)
    value = json.loads(assistant_text)
    if "better" in value:
        return PairwiseResult.model_validate(value)
    if "deck_id" in value:
        return parse_deck_result(value)
    return parse_page_result(value)


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


def _modality_for_sample(manifest: ManifestSample, requested: Modality | str | None = None) -> Modality:
    if requested is not None:
        return Modality(requested)
    return Modality.C_BOTH if _has_image_payload(manifest) else Modality.B_STRUCT_ONLY


def _pointwise_request(manifest: ManifestSample, modality: Modality):
    if manifest.deck is not None or (manifest.oracle and "deck_id" in manifest.oracle):
        return deck_request_from_sample(manifest, modality=modality)
    return page_request_from_sample(manifest, modality=modality)


def _record_metadata(manifest: ManifestSample, modality: Modality, *, mode: str = "pointwise") -> dict[str, Any]:
    return {**manifest.metadata, "exam_mode": mode, "level": _sample_level(manifest), "modality": modality.value}


def _assign_modalities(
    samples: list[ManifestSample],
    *,
    min_a_image_only_ratio: float,
    b_struct_ratio: float,
    c_both_ratio: float,
) -> list[Modality]:
    _validate_modality_ratios(min_a_image_only_ratio, b_struct_ratio, c_both_ratio)
    if not samples:
        return []
    image_available = [_has_image_payload(sample) for sample in samples]

    assignments: list[Modality | None] = [None for _ in samples]
    for level in ("page", "deck"):
        level_indices = [index for index, sample in enumerate(samples) if _sample_level(sample) == level]
        image_indices = [index for index in level_indices if image_available[index]]
        desired_a = _ceil_ratio(len(level_indices), min_a_image_only_ratio)
        if len(image_indices) < desired_a:
            raise ValueError(
                f"{level} A_IMAGE_ONLY requires {desired_a} image-backed samples for ratio "
                f"{min_a_image_only_ratio:g}, but only {len(image_indices)} are available"
            )
        for index in image_indices[:desired_a]:
            assignments[index] = Modality.A_IMAGE_ONLY

    remaining = [index for index, item in enumerate(assignments) if item is None]
    total_remaining_ratio = b_struct_ratio + c_both_ratio
    c_fraction = c_both_ratio / total_remaining_ratio if total_remaining_ratio else 0.0
    desired_c = min(sum(1 for index in remaining if image_available[index]), round(len(remaining) * c_fraction))

    c_assigned = 0
    for index in remaining:
        if image_available[index] and c_assigned < desired_c:
            assignments[index] = Modality.C_BOTH
            c_assigned += 1
        else:
            assignments[index] = Modality.B_STRUCT_ONLY

    return [item if item is not None else Modality.B_STRUCT_ONLY for item in assignments]


def _validate_modality_ratios(min_a_image_only_ratio: float, b_struct_ratio: float, c_both_ratio: float) -> None:
    if not 0 <= min_a_image_only_ratio <= 1:
        raise ValueError("min_a_image_only_ratio must be between 0 and 1")
    if b_struct_ratio < 0 or c_both_ratio < 0:
        raise ValueError("b_struct_ratio and c_both_ratio must be non-negative")
    if b_struct_ratio + c_both_ratio <= 0:
        raise ValueError("at least one of b_struct_ratio or c_both_ratio must be positive")


def _ceil_ratio(count: int, ratio: float) -> int:
    if count <= 0 or ratio <= 0:
        return 0
    return int(-(-count * ratio // 1))


def _has_image_payload(sample: ManifestSample) -> bool:
    return _image_path(sample) is not None


def _image_path(sample: ManifestSample) -> Path | None:
    path = sample.image_path or sample.metadata.get("defective_image_path")
    if not path:
        return None
    image_path = Path(str(path))
    return image_path if image_path.exists() else None


def _sample_level(sample: ManifestSample) -> str:
    return "deck" if sample.deck is not None or (sample.oracle and "deck_id" in sample.oracle) else "page"


def _assistant_text(record: dict[str, Any]) -> str:
    for message in reversed(record.get("messages", [])):
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    return str(item.get("text", ""))
    raise ValueError("SFT record has no assistant text content")


def _pairwise_user_text(manifest: ManifestSample) -> str:
    candidate_b_messages = build_messages_from_sample(manifest, modality=Modality.B_STRUCT_ONLY)
    candidate_b_text = _first_user_text(candidate_b_messages)
    return (
        "Compare candidate A and candidate B for slide quality. Candidate A is the clean/reference "
        "rendering when present; candidate B is the inspected rendering. Use the shared render and "
        "element serialization below for candidate B. Output ONLY PairwiseResult JSON.\n\n"
        f"CANDIDATE_B_CONTRACT_VIEW:\n{candidate_b_text}"
    )


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue
        for item in message.get("content", []):
            if item.get("type") == "text":
                return str(item.get("text", ""))
    return ""


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
