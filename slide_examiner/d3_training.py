"""Training-data contracts and joint objectives for the D3 critic."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .d3_data import read_jsonl, sha256_file, write_jsonl
from .examiner_contract import (
    EvidenceSource,
    ExaminerAction,
    ExamLevel,
    Locator,
    Modality,
    PageExamResult,
    DeckExamResult,
    page_result_from_labels,
    deck_result_from_labels,
)

GENERIC_INSPECTION_INSTRUCTION = (
    "Inspect the supplied slide artifact for presentation-quality defects. First decide whether "
    "the available evidence is sufficient. Return exactly one JSON object with action, confidence, "
    "requested_context, evidence_source, has_defect, findings, and clean_dimensions. Choose ANSWER "
    "only when the evidence supports a finding or a clean decision; otherwise choose CALL_LINTER, "
    "REQUEST_REFERENCE, REQUEST_DECK, or DEFER. A non-ANSWER action must not contain a finding."
)

ACTIONS = tuple(action.value for action in ExaminerAction)
ACTION_TO_ID = {name: index for index, name in enumerate(ACTIONS)}
LOSS_NAMES = ("detect", "distill", "pair", "severity", "route", "select")


def relocate_path(value: str | None, repo: Path) -> Path | None:
    """Resolve frozen paths from the Mac/old GPU checkout into this checkout."""
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return path.resolve()
    for marker in ("/runs/", "/data/", "/release/"):
        if marker in value:
            candidate = repo / marker.strip("/") / value.split(marker, 1)[1]
            if candidate.exists():
                return candidate.resolve()
    candidate = repo / value
    return candidate.resolve() if candidate.exists() else None


def image_paths_for_sample(sample: dict[str, Any], repo: Path, availability: str) -> list[str]:
    pair = sample.get("pair") or {}
    metadata = sample.get("metadata") or {}
    defective = (sample.get("image_path") or pair.get("defective_image_path")
                 or metadata.get("defective_image_path"))
    if not defective and sample.get("slide"):
        defective = str(repo / "runs/part2/rendered" / sample["sample_id"] / "defective.png")
    paths: list[Path] = []
    resolved = relocate_path(defective, repo)
    if not resolved:
        rendered = repo / "runs/part2/rendered" / sample["sample_id"] / "defective.png"
        resolved = rendered.resolve() if rendered.exists() else None
    if resolved:
        paths.append(resolved)
    if availability == "reference_available":
        clean = pair.get("clean_image_path") or metadata.get("clean_image_path")
        if not clean and sample.get("slide"):
            clean = str(repo / "runs/part2/rendered" / sample["sample_id"] / "clean.png")
        clean_path = relocate_path(clean, repo)
        if not clean_path:
            rendered = repo / "runs/part2/rendered" / sample["sample_id"] / "clean.png"
            clean_path = rendered.resolve() if rendered.exists() else None
        if clean_path:
            paths.insert(0, clean_path)
    if availability == "deck_context_available":
        for value in metadata.get("page_image_paths", []):
            page = relocate_path(value, repo)
            if page and page not in paths:
                paths.append(page)
    return [str(path) for path in paths]


def _evidence_source(availability: str, is_deck: bool) -> EvidenceSource:
    return {
        "image_structure": EvidenceSource.STRUCTURE,
        "reference_available": EvidenceSource.REFERENCE,
        "deck_context_available": EvidenceSource.DECK_CONTEXT,
    }.get(availability, EvidenceSource.DECK_CONTEXT if is_deck else EvidenceSource.PIXELS)


def _requested_context(action: str) -> list[EvidenceSource]:
    return {
        "CALL_LINTER": [EvidenceSource.STRUCTURE],
        "REQUEST_REFERENCE": [EvidenceSource.REFERENCE],
        "REQUEST_DECK": [EvidenceSource.DECK_CONTEXT],
    }.get(action, [])


def _answer_for(sample: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    is_deck = bool(sample.get("deck"))
    result = deck_result_from_labels(sample) if is_deck else page_result_from_labels(sample)
    action = target["target_action"]
    data = result.model_dump(mode="json")
    availability = target["availability"]
    data.update({
        "action": action,
        "confidence": round(float(target.get("distillation_weight", 1.0)), 3),
        "requested_context": [item.value for item in _requested_context(action)],
        "evidence_source": (EvidenceSource.NONE.value if action != "ANSWER" else
                            _evidence_source(availability, is_deck).value),
    })
    teacher = target.get("target_finding") or {}
    teacher_locator = teacher.get("locator") or {}
    if action == "ANSWER" and target.get("target_kind") == "distill" and teacher.get("has_defect"):
        base = data["findings"][0]
        base["locator"] = Locator(
            level=ExamLevel.PAGE,
            page_id=data["page_id"],
            element_id=teacher_locator.get("element") or base["locator"].get("element_id"),
        ).model_dump(mode="json")
        region = teacher_locator.get("region", "unspecified region")
        base["evidence"] = (
            f"Teacher-localized rendered overflow at {region}: "
            f"{teacher_locator.get('element', 'named content element')}."
        )
    if action != "ANSWER":
        data.update(has_defect=False, findings=[], clean_dimensions=[])
    model = DeckExamResult if is_deck else PageExamResult
    return model.model_validate(data).model_dump(mode="json")


def _structure_text(sample: dict[str, Any], availability: str) -> str:
    payload: dict[str, Any] = {"availability": availability}
    if availability == "image_structure":
        payload["structure"] = sample.get("slide") or sample.get("deck") or sample.get("oracle")
    elif availability == "deck_context_available":
        payload["deck_context"] = sample.get("deck") or sample.get("oracle")
    elif availability == "reference_available":
        payload["reference_note"] = "The first image is the clean/reference candidate when two images are supplied."
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _task_for(target: dict[str, Any]) -> str:
    kind = target["target_kind"]
    if kind in {"pairwise", "clean_clean_pairwise"}:
        return "pair"
    if kind == "distill":
        return "distill"
    if kind == "route" or target["target_action"] != "ANSWER":
        return "route"
    return "detect"


def build_d3_training_records(repo: Path, *, include_splits: set[str] | None = None,
                              max_per_cell: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialise multimodal records without reading either final-test manifest."""
    include_splits = include_splits or {"train", "dev"}
    samples: dict[str, dict[str, Any]] = {}
    for source in (repo / "data/part2/manifest.jsonl",
                   repo / "release/part3/manifests/manifest_g7_rendered.jsonl"):
        for row in read_jsonl(source):
            samples[row["sample_id"]] = row
    # Clean-deck controls exist first as split records rather than Part-2 manifest rows.
    # Materialise contract-shaped samples from their immutable clean deck IR.
    for row in read_jsonl(repo / "data/part3/d3/split_manifest.jsonl"):
        if row["sample_id"] in samples or row.get("record_kind") != "clean_deck_negative":
            continue
        deck_path = relocate_path((row.get("pair") or {}).get("clean_deck_path"), repo)
        if not deck_path:
            continue
        deck = json.loads(deck_path.read_text())
        samples[row["sample_id"]] = {
            "sample_id": row["sample_id"], "slide": None, "deck": deck,
            "image_path": None, "labels": [], "oracle": deck,
            "pair": row.get("pair") or {},
            "metadata": {"split": row["split"], "clean_deck_path": str(deck_path)},
        }
    targets = read_jsonl(repo / "release/part3/d3/training_targets.jsonl")
    cell_counts: Counter[tuple[str, str, str, str]] = Counter()
    records: list[dict[str, Any]] = []
    skipped = Counter()
    for target in targets:
        if target["split"] not in include_splits or not target.get("included", True):
            continue
        sample = samples.get(target["sample_id"])
        if not sample:
            skipped["missing_sample"] += 1
            continue
        prefix = target["defect"].split("_", 1)[0]
        cell = (target["split"], prefix, target["availability"], target["target_action"])
        if max_per_cell is not None and cell_counts[cell] >= max_per_cell:
            continue
        images = image_paths_for_sample(sample, repo, target["availability"])
        if not images and target["availability"] in {"image_only", "reference_available"}:
            skipped["missing_image"] += 1
            continue
        output = _answer_for(sample, target)
        task = _task_for(target)
        content: list[dict[str, str]] = [{"type": "image", "image": path} for path in images]
        content.append({"type": "text", "text": GENERIC_INSPECTION_INSTRUCTION + "\nINPUT_CONTEXT="
                        + _structure_text(sample, target["availability"])})
        records.append({
            "record_id": hashlib.sha256(
                f"{target['sample_id']}|{target['availability']}|{task}".encode()).hexdigest()[:20],
            "sample_id": target["sample_id"], "split": target["split"], "defect": target["defect"],
            "availability": target["availability"], "task": task,
            "target_action": target["target_action"], "action_id": ACTION_TO_ID[target["target_action"]],
            "target_confidence": float(target.get("distillation_weight", 1.0)),
            "severity": float(next(iter(sample.get("labels") or [{}]), {}).get("severity", 0.0)),
            "severity_chain": f"{(sample.get('slide') or {}).get('slide_id', target['sample_id'])}|{target['defect']}",
            "weight": float(target.get("distillation_weight", 1.0)),
            "messages": [{"role": "user", "content": content},
                         {"role": "assistant", "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}]}],
            "images": images,
        })
        cell_counts[cell] += 1
    summary = {
        "records": len(records), "splits": dict(Counter(r["split"] for r in records)),
        "tasks": dict(Counter(r["task"] for r in records)),
        "actions": dict(Counter(r["target_action"] for r in records)),
        "defects": dict(Counter(r["defect"].split("_", 1)[0] for r in records)),
        "skipped": dict(skipped), "generic_instruction_sha256": hashlib.sha256(
            GENERIC_INSPECTION_INSTRUCTION.encode()).hexdigest(),
        "final_test_read": False,
    }
    return records, summary


def export_d3_training(repo: Path, out_dir: Path, *, max_per_cell: int | None = None) -> dict[str, Any]:
    records, summary = build_d3_training_records(repo, max_per_cell=max_per_cell)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "dev"):
        write_jsonl(out_dir / f"d3_{split}.jsonl", (r for r in records if r["split"] == split))
    # Class router is learned only from train action counts, with Laplace smoothing.
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in records:
        if row["split"] == "train":
            counts[row["defect"].split("_", 1)[0]][row["target_action"]] += 1
    class_router = {}
    for defect, counter in sorted(counts.items()):
        denom = sum(counter.values()) + len(ACTIONS)
        probs = {action: (counter[action] + 1) / denom for action in ACTIONS}
        class_router[defect] = {"counts": dict(counter), "probabilities": probs,
                                "prediction": max(probs, key=probs.get)}
    (out_dir / "class_router.json").write_text(json.dumps({
        "fit_split": "train", "estimator": "Laplace-smoothed categorical MLE",
        "manual_route_used": False, "routes": class_router}, ensure_ascii=False, indent=2))
    summary.update({"train_sha256": sha256_file(out_dir / "d3_train.jsonl"),
                    "dev_sha256": sha256_file(out_dir / "d3_dev.jsonl"),
                    "class_router": "class_router.json", "losses": list(LOSS_NAMES)})
    (out_dir / "export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


@dataclass
class LossWeights:
    detect: float = 1.0
    distill: float = 1.0
    pair: float = 1.0
    severity: float = 0.2
    route: float = 0.5
    select: float = 0.2

    def enabled(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in LOSS_NAMES}


def action_class_weights(rows: list[dict[str, Any]], mode: str = "sqrt-inverse") -> list[float]:
    """Return mean-normalised train-only weights for the route objective."""
    counts = Counter(int(row["action_id"]) for row in rows)
    if mode == "none":
        return [1.0] * len(ACTIONS)
    missing = [ACTIONS[index] for index in range(len(ACTIONS)) if not counts[index]]
    if missing:
        raise ValueError(f"training split is missing route actions: {missing}")
    exponent = 1.0 if mode == "inverse" else 0.5
    raw = [1.0 / (counts[index] ** exponent) for index in range(len(ACTIONS))]
    mean = sum(raw) / len(raw)
    return [value / mean for value in raw]
