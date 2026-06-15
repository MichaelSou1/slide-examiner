from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schemas import DefectLabel, ManifestSample


def answer_from_labels(labels: Iterable[DefectLabel]) -> dict:
    active_labels = [label for label in labels if label.type != "NO_DEFECT"]
    defects = [
        {
            "type": label.type,
            "present": True,
            "element_ids": list(label.target_element_ids),
            "severity": label.severity,
            "confidence": 1.0,
            "evidence": "synthetic injection label",
            "fix": "restore the corresponding clean slide property",
        }
        for label in active_labels
    ]
    return {"defects": defects, "overall_score": max(0.0, 1.0 - 0.2 * len(defects))}


def build_pointwise_record(sample: ManifestSample | dict) -> dict:
    manifest = ManifestSample.from_mapping(sample)
    image_path = manifest.image_path or manifest.metadata.get("defective_image_path") or ""
    user_text = (
        "Inspect this rendered slide for presentation defects. "
        "Return strict JSON with defects, element ids, severity, evidence, and fixes."
    )
    return {
        "sample_id": manifest.sample_id,
        "messages": [
            {"role": "user", "content": [{"type": "image", "image": image_path}, {"type": "text", "text": user_text}]},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps(answer_from_labels(manifest.labels), ensure_ascii=False)}],
            },
        ],
    }


def build_pairwise_record(sample: ManifestSample | dict) -> dict:
    manifest = ManifestSample.from_mapping(sample)
    pair = manifest.pair or {}
    clean_image = pair.get("clean_image_path", manifest.metadata.get("clean_image_path", ""))
    defective_image = pair.get("defective_image_path", manifest.image_path or "")
    answer = {
        "pairwise_winner": "tie" if not [label for label in manifest.labels if label.type != "NO_DEFECT"] else "clean",
        "defects": answer_from_labels(manifest.labels)["defects"],
        "overall_score": 0.0 if [label for label in manifest.labels if label.type != "NO_DEFECT"] else 1.0,
    }
    user_text = (
        "Compare candidate A and candidate B for slide quality. "
        "Return strict JSON with pairwise_winner and defects."
    )
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
            {"role": "assistant", "content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}]},
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
